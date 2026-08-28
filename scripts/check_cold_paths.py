"""冷门环境自检：把"这台机器上永远走不到的分支"逐个真跑一遍。

存在的理由（2026-08-28）：`_remote_hint()` 用了 `os.getenv` 而文件没导入 os——
回环启动走不到那段，线上一直没炸；只要用户在 SSH 会话里跑 `guanjia web` 就 NameError。
这类缺陷单测抓不到（测试环境恰好是"正常"的那一种），只能真的把环境掰成别的样子再跑。

用法：
    python3 scripts/check_cold_paths.py          # 不需要登录也能跑大部分
退出码：0 全过 · 1 有异常。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

GREEN, RED, DIM, RESET = "\x1b[32m", "\x1b[31m", "\x1b[2m", "\x1b[0m"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Cold:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def run(self, name: str, args: list[str], *, env: dict | None = None,
            stdin_closed: bool = True, expect_codes=(0, 1, 2, 3, 4),
            timeout: int = 90) -> str:
        """跑一条命令，只要不是崩溃（traceback / 非预期退出码）就算过。"""
        full_env = {**os.environ, **(env or {})}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "guanjia", *args], cwd=ROOT, env=full_env,
                capture_output=True, text=True, timeout=timeout,
                stdin=subprocess.DEVNULL if stdin_closed else None)
        except subprocess.TimeoutExpired:
            self._fail(name, f"超时 {timeout}s")
            return ""
        output = (proc.stdout or "") + (proc.stderr or "")
        if "Traceback (most recent call last)" in output:
            first = next((line for line in output.splitlines()
                          if line.strip().startswith(("NameError", "AttributeError",
                                                      "TypeError", "ImportError",
                                                      "UnboundLocalError", "KeyError"))),
                         output.strip().splitlines()[-1] if output.strip() else "?")
            self._fail(name, f"崩了：{first[:110]}")
            return output
        if proc.returncode not in expect_codes:
            self._fail(name, f"退出码 {proc.returncode}：{output.strip()[:110]}")
            return output
        print(f"  {GREEN}✓{RESET} {name}  {DIM}退出码 {proc.returncode}{RESET}")
        return output

    def serve(self, name: str, args: list[str], *, env: dict | None = None,
              wait: float = 3.0) -> str:
        """web 是常驻服务：起起来、读输出、确认没崩，然后杀掉。

        用 run() 等它退出只会超时——那不是缺陷，是我一开始检查方式错了。
        """
        import signal
        import time

        full_env = {**os.environ, **(env or {})}
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "guanjia", *args], cwd=ROOT, env=full_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, start_new_session=True)
        time.sleep(wait)
        alive = proc.poll() is None
        if alive:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            output = proc.communicate(timeout=10)[0] or ""
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            output = proc.communicate()[0] or ""
        if "Traceback (most recent call last)" in output:
            line = next((l for l in output.splitlines()
                         if l.strip().startswith(("NameError", "AttributeError",
                                                  "TypeError", "ImportError"))),
                        output.strip().splitlines()[-1] if output.strip() else "?")
            self._fail(name, f"崩了：{line[:110]}")
            return output
        if not alive:
            self._fail(name, f"没起来就退了：{output.strip()[:110]}")
            return output
        print(f"  {GREEN}✓{RESET} {name}  {DIM}起得来、没崩{RESET}")
        return output

    def _fail(self, name: str, detail: str) -> None:
        print(f"  {RED}✕{RESET} {name}  {DIM}{detail}{RESET}")
        self.failures.append(f"{name}: {detail}")


def main() -> int:
    cold = Cold()
    print("冷门环境自检")

    with tempfile.TemporaryDirectory() as empty_home:
        blank = {"HOME": empty_home, "GUANJIA_SERVER": "", "GUANJIA_TOKEN": "",
                 "GUANJIA_PROFILE": ""}

        print(f"\n{DIM}— 全新用户（空 HOME，没有配置）—{RESET}")
        cold.run("--help", ["--help"], env=blank)
        cold.run("--version", ["--version"], env=blank)
        cold.run("doctor", ["doctor"], env=blank)
        cold.run("today", ["today"], env=blank)
        cold.run("remote 列表", ["remote"], env=blank)
        cold.run("remote use 不存在", ["remote", "use", "nope"], env=blank)
        cold.run("remote rm 不存在", ["remote", "rm", "nope"], env=blank)
        cold.run("run 未登录", ["run", "随便"], env=blank)
        cold.run("rerun 未登录", ["rerun", "abc"], env=blank)
        cold.run("export 未登录", ["export", "随便"], env=blank)
        cold.run("completion bash", ["completion", "bash"], env=blank)
        cold.run("completion 未知 shell", ["completion", "fish"], env=blank)
        cold.run("隐藏子命令 _wf-names", ["_wf-names"], env=blank)
        cold.run("隐藏子命令 _profile-names", ["_profile-names"], env=blank)

        print(f"\n{DIM}— SSH 会话（提示分支）—{RESET}")
        ssh_env = {**blank, "SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}
        out = cold.serve("web 启动提示", ["web", "--port", "7899"], env=ssh_env)
        if out and "ssh -L" not in out:
            cold._fail("web 在 SSH 下应提示端口转发", "输出里没有 ssh -L")
        elif out:
            print(f"    {DIM}{[l.strip() for l in out.splitlines() if 'ssh -L' in l][:1]}{RESET}")

        print(f"\n{DIM}— 非回环绑定（访问密钥）—{RESET}")
        out = cold.serve("web --host 0.0.0.0", ["web", "--port", "7898",
                                                "--host", "0.0.0.0"], env=blank)
        if out and "?k=" not in out:
            cold._fail("非回环绑定应生成访问密钥", "输出里没有 ?k=")

        print(f"\n{DIM}— 没有 readline（补全与历史）—{RESET}")
        no_readline = {**blank, "PYTHONPATH": os.path.join(ROOT, "scripts", "_stubs")}
        stub_dir = os.path.join(ROOT, "scripts", "_stubs")
        os.makedirs(stub_dir, exist_ok=True)
        stub = os.path.join(stub_dir, "readline.py")
        with open(stub, "w", encoding="utf-8") as handle:
            handle.write("raise ImportError('no readline on this platform')\n")
        try:
            cold.run("REPL 导入（无 readline）", ["--version"], env=no_readline)
            cold.run("doctor（无 readline）", ["doctor"], env=no_readline)
        finally:
            os.remove(stub)
            try:
                os.rmdir(stub_dir)
            except OSError:
                pass

        print(f"\n{DIM}— 无浏览器 / 无显示（--open / --app）—{RESET}")
        headless = {**blank, "PATH": "/usr/bin:/bin", "DISPLAY": "", "BROWSER": ""}
        cold.serve("web --open", ["web", "--port", "7897", "--open"], env=headless)
        cold.serve("web --app", ["web", "--port", "7896", "--app"], env=headless)

        print(f"\n{DIM}— 参数边界 —{RESET}")
        cold.run("run 空名字", ["run", ""], env=blank)
        cold.run("run 参数没有等号", ["run", "x", "没有等号"], env=blank)
        cold.run("import 不存在的文件", ["import", "/nope.json"], env=blank)
        cold.run("import 从 stdin 读到空", ["import", "-"], env=blank)

    print()
    if cold.failures:
        print(f"{RED}✕ {len(cold.failures)} 项异常{RESET}")
        for item in cold.failures:
            print(f"  · {item}")
        return 1
    print(f"{GREEN}✓ 冷门路径都没炸{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
