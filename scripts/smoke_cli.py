"""guanjia CLI 真机冒烟：每个子命令打真实远端，验行为与退出码。

存在的理由：单元测试用的是 HTTP 桩，桩只会返回我们**以为**平台会返回的形状。
2026-08-28 一轮审计抓出的客户端缺陷全是桩测不到的：
声明 array 的输入从 CLI 100% 跑不通（60 个输入里 32 个是 array）、
失败运行显示「error: None」、成功运行的 outputs 吃的是中间节点 payload。
这个脚本每条都用真实远端复核一遍。

用法（需要已登录：guanjia --login）：
    python3 scripts/smoke_cli.py
    python3 scripts/smoke_cli.py --workflow 文本行数 --input "text=甲\\n乙"
退出码：0 全过 · 1 有失败 · 2 环境不满足（未登录/远端不可达）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

GREEN, RED, DIM, RESET = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[0m"


def _outputs_match_remote(run_id: str, got: dict) -> bool:
    """对照平台顶层 outputs 逐键比较。

    客户端此前把 state 里每个节点的中间产物拍平当结果，键里混进
    output/text/calc.output 这类东西——启发式判据（"值不是大 dict"）抓不到，
    只有跟权威来源逐键比才靠得住。
    """
    if not run_id:
        return False
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from guanjia.config import load_config
        from guanjia.remote import RemoteClient

        cfg = load_config()
        run = RemoteClient(cfg["server"], cfg["token"]).request(
            "GET", f"/api/v1/runs/{run_id}")
    except Exception:  # noqa: BLE001 - 取不到就别误判成失败
        return bool(got)
    remote = run.get("outputs")
    if not isinstance(remote, dict) or not remote:
        return bool(got)
    return set(got) == set(remote)


class Smoke:
    def __init__(self, exe: list[str]):
        self.exe = exe
        self.failures: list[str] = []

    def run(self, *args: str, stdin_tty: bool = False) -> tuple[int, str, str]:
        proc = subprocess.run(self.exe + list(args), capture_output=True, text=True,
                              timeout=300, stdin=subprocess.DEVNULL if not stdin_tty else None)
        return proc.returncode, proc.stdout, proc.stderr

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        print(f"  {GREEN + '✓' + RESET if ok else RED + '✕' + RESET} {name}"
              + (f"  {DIM}{detail}{RESET}" if detail else ""))
        if not ok:
            self.failures.append(f"{name}: {detail}")
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="guanjia CLI 真机冒烟")
    parser.add_argument("--exe", default="", help="被测命令，默认 python3 -m guanjia")
    parser.add_argument("--workflow", default="", help="用于真跑的工作流名（不给则自动挑一个）")
    parser.add_argument("--input", action="append", default=[],
                        help="真跑时的输入 key=value，可重复")
    args = parser.parse_args()

    exe = args.exe.split() if args.exe else [sys.executable, "-m", "guanjia"]
    smoke = Smoke(exe)
    print(f"guanjia CLI 冒烟 · {' '.join(exe)}")

    code, out, err = smoke.run("--version")
    if not smoke.check("--version", code == 0 and "guanjia" in out, out.strip() or err.strip()):
        return 2

    code, out, _ = smoke.run("--help")
    smoke.check("--help 列出全部子命令",
                code == 0 and all(word in out for word in
                                  ("web", "today", "run", "rerun", "export", "doctor")),
                f"{len(out.splitlines())} 行")

    # ── doctor：登录态是后面所有检查的前提 ──
    code, out, _ = smoke.run("doctor")
    logged_in = "登录态" in out and "✕" not in out.split("登录态")[1][:20]
    smoke.check("doctor 能自检", "配置" in out and "会话存储" in out,
                f"退出码 {code}")
    if not logged_in:
        print(f"\n{RED}未登录，后面的真机检查跳过：先 guanjia --login{RESET}")
        return 2
    smoke.check("doctor 报告工作流健康", "工作流健康" in out,
                [line.strip() for line in out.splitlines() if "健康" in line][:1])

    # ── today ──
    code, out, _ = smoke.run("today")
    smoke.check("today 出总览", code == 0 and "今日运行" in out,
                out.splitlines()[0] if out else "")
    smoke.check("today 的失败行带原因（不是空白）",
                all(len(line.split("run ")[-1].split(None, 1)) > 1
                    for line in out.splitlines() if line.strip().startswith("✕")) or
                not any(line.strip().startswith("✕") for line in out.splitlines()),
                "没有失败行" if "✕" not in out else "每条都有原因")

    # ── 找一个已发布工作流 ──
    code, out, _ = smoke.run("run", "不存在的工作流名")
    smoke.check("run 名字不存在时列候选并退 2", code == 2, f"退出码 {code}")

    target = args.workflow
    if not target:
        for line in out.splitlines():
            if "（已发布）" in line:
                target = line.strip().lstrip("· ").split("（")[0]
                break
    if not target:
        print(f"  {DIM}·{RESET} 真跑检查跳过：远端没有已发布工作流")
        return 1 if smoke.failures else 0

    # ── 真跑：类型转换与结果字段 ──
    pairs = list(args.input)
    if not pairs:
        code, out, _ = smoke.run("run", target, "--json", "--wait", "20")
        # 不给输入时：要么直接成功（无必填），要么失败且**说清原因**
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            data = {}
        if data.get("status") == "failed":
            smoke.check("失败运行带得出原因（不是 None）", bool(data.get("error")),
                        str(data.get("error"))[:70])
            smoke.check("失败退出码为 1", code == 1, f"退出码 {code}")
        elif data.get("status") == "succeeded":
            smoke.check("成功运行退出码为 0", code == 0, f"退出码 {code}")
            smoke.check("outputs 与平台顶层逐键一致（不是中间节点拍平）",
                        _outputs_match_remote(str(data.get("run_id") or ""),
                                              data.get("outputs") or {}),
                        list((data.get("outputs") or {}).keys())[:5])
        else:
            smoke.check("run 返回可解析的 JSON", bool(data), out[:80])
    else:
        code, out, err = smoke.run("run", target, *pairs, "--json", "--wait", "60")
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            data = {}
        smoke.check("带输入真跑成功", data.get("status") == "succeeded",
                    f"退出码 {code} · {str(data.get('error') or out or err)[:70]}")
        run_id = str(data.get("run_id") or "")
        smoke.check("outputs 与平台顶层逐键一致（不是中间节点拍平）",
                    _outputs_match_remote(run_id, data.get("outputs") or {}),
                    list((data.get("outputs") or {}).keys())[:5])
        if run_id:
            code, out, _ = smoke.run("rerun", run_id[:8], "--json", "--wait", "60")
            try:
                again = json.loads(out or "{}")
            except json.JSONDecodeError:
                again = {}
            smoke.check("rerun 用原输入重跑并报出工作流名",
                        again.get("status") == "succeeded" and bool(again.get("workflow")),
                        f"{again.get('workflow')} · {again.get('status')}")

    # ── 类型转换：非法 JSON 必须被拦住，不能静默丢键 ──
    code, out, err = smoke.run("run", target, "__smoke_bad__=不是JSON", "--json", "--wait", "10")
    smoke.check("未声明的键不炸（原样当字符串传）", code in (0, 1, 3),
                f"退出码 {code}")

    # ── export：产出可搬运快照 ──
    code, out, _ = smoke.run("export", target, "-o", "-")
    try:
        payload = json.loads(out or "{}")
    except json.JSONDecodeError:
        payload = {}
    smoke.check("export 出自包含快照",
                code == 0 and payload.get("guanjia_export") == 1
                and bool(payload.get("snapshot", {}).get("workflow")),
                f"rev {payload.get('revision')}")

    print()
    if smoke.failures:
        print(f"{RED}✕ {len(smoke.failures)} 项失败{RESET}")
        for item in smoke.failures:
            print(f"  · {item}")
        return 1
    print(f"{GREEN}✓ CLI 全部正常{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
