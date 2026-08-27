"""guanjia run：不进 REPL 直接跑一个已发布工作流——给脚本和 cron 的一次性出口。

    guanjia run GPU日报                    # 名字支持唯一子串匹配
    guanjia run 对账 month=2026-08 --json  # key=value 传输入，JSON 出结果
退出码：0 成功 · 1 失败/未登录 · 2 参数或名字问题 · 3 超时仍在跑。
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .plugins import workflow
from .remote import RemoteClient, RemoteError


def _resolve(items: list[dict], needle: str):
    """精确 id/名字优先，其次唯一子串；返回 dict 或（歧义/空的）候选列表。"""
    for item in items:
        if item["id"] == needle or item["name"] == needle:
            return item
    hits = [item for item in items if needle.lower() in item["name"].lower()]
    return hits[0] if len(hits) == 1 else hits


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="guanjia run", description="直接运行一个已发布工作流")
    parser.add_argument("name", help="工作流名字（支持唯一子串）或 id")
    parser.add_argument("pairs", nargs="*", help="输入参数 key=value")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--wait", type=float, default=120.0, help="最长等待秒数（默认 120）")
    parser.add_argument("--follow", action="store_true", help="实时滚动事件直到结束")
    args = parser.parse_args(argv)

    cfg = load_config()
    if not cfg["token"]:
        print("未登录：先 guanjia --login（guanjia doctor 可自查）", file=sys.stderr)
        return 1
    remote = RemoteClient(cfg["server"], cfg["token"])
    try:
        items = workflow.list_workflows(remote)
    except RemoteError as error:
        print(f"远端不可达或登录失效：{error}（guanjia doctor 可自查）", file=sys.stderr)
        return 1

    target = _resolve(items, args.name)
    if isinstance(target, list):
        pool = target or items
        head = "有歧义，匹配到多个" if target else "找不到"
        print(f"{head}「{args.name}」，可选：", file=sys.stderr)
        for item in pool[:10]:
            state = "已发布" if item["published"] else "未发布"
            print(f"  · {item['name']}（{state}）", file=sys.stderr)
        return 2
    if not target["published"]:
        print(f"「{target['name']}」还没有发布版本——在对话里让莉莉丝先完成构建。", file=sys.stderr)
        return 1

    inputs: dict = {}
    for pair in args.pairs:
        if "=" not in pair:
            print(f"输入参数要写成 key=value，收到：{pair}", file=sys.stderr)
            return 2
        key, value = pair.split("=", 1)
        inputs[key] = value

    if not args.json and sys.stdin.isatty():  # 交互场景补齐缺失输入
        try:
            for field in workflow.input_schema(remote, target["id"]):
                if field["name"] not in inputs:
                    hint = f"（如 {field['example']}）" if field.get("example") else ""
                    value = input(f"  {field['label']}{hint}: ").strip()
                    if value:
                        inputs[field["name"]] = value
        except RemoteError:
            pass  # 拿不到输入表就按已给参数直跑

    if args.follow:
        return _follow(remote, target, inputs)

    result = workflow.run(remote, target["id"], inputs, wait_seconds=args.wait)

    if args.json:
        print(json.dumps({"workflow": target["name"], **result}, ensure_ascii=False))
    else:
        mark = {"succeeded": "✓", "failed": "✕", "running": "…"}.get(result["status"], "?")
        print(f"{mark} {target['name']} · run {result['run_id']} · {result['status']}")
        for key, value in (result["outputs"] or {}).items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            print(f"  {key} = {text[:500]}")
        if result.get("error"):
            print(f"  错误：{str(result['error'])[:300]}")
        if result["status"] == "running":
            print(f"  超过 --wait {args.wait:.0f}s 还在跑；稍后可在 REPL 问「run {result['run_id']} 结果如何」")
    return {"succeeded": 0, "failed": 1}.get(result["status"], 3)


def _follow(remote: RemoteClient, target: dict, inputs: dict) -> int:
    """--follow：创建后直播事件流，terminal 后补一段 outputs。"""
    run_id = workflow.start_run(remote, target["id"], inputs)
    print(f"▶ {target['name']} · run {run_id}（Ctrl+C 只停跟随，运行继续）")
    status = "running"
    try:
        for row in workflow.follow_run(remote, run_id):
            mark = "✕" if ("failed" in row["type"] or row["error"]) else "·"
            line = f"  {row['elapsed']:6.1f}s {mark} {row['type']:<20} {row['label']}"
            if row["error"]:
                line += f"  {row['error']}"
            print(line, flush=True)
            if row["type"] in workflow.TERMINAL_EVENTS:
                status = row["type"].rsplit(".", 1)[-1]
    except KeyboardInterrupt:
        print("  （已停止跟随，运行仍在远端继续）")
        return 3
    outputs: dict = {}
    error = ""
    try:
        final = remote.request("GET", f"/api/v1/runs/{run_id}")
        for value in ((final.get("state") or {}).get("outputs") or {}).values():
            if isinstance(value, dict):
                outputs.update(value)
        error = str((final.get("state") or {}).get("error") or "")
    except RemoteError:
        pass
    mark = {"completed": "✓", "failed": "✕"}.get(status, "…")
    print(f"{mark} {status}")
    for key, value in outputs.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        print(f"  {key} = {text[:500]}")
    if error:
        print(f"  错误：{error[:300]}")
    return 0 if status == "completed" else (1 if status == "failed" else 3)


def rerun_main(argv: list[str]) -> int:
    """guanjia rerun <run id 或前缀>：用原输入重跑一次失败/成功的运行。"""
    parser = argparse.ArgumentParser(prog="guanjia rerun", description="用原输入重跑一次运行")
    parser.add_argument("run_id", help="run id（today/时间线里的前缀即可）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--wait", type=float, default=120.0)
    args = parser.parse_args(argv)

    cfg = load_config()
    if not cfg["token"]:
        print("未登录：先 guanjia --login", file=sys.stderr)
        return 1
    remote = RemoteClient(cfg["server"], cfg["token"])
    run_id = args.run_id
    try:
        if len(run_id) < 32:
            full = workflow.find_run(remote, run_id)
            if not full:
                print(f"按前缀「{run_id}」没找到唯一运行（近期 30 条/应用内检索）", file=sys.stderr)
                return 2
            run_id = full
        result = workflow.rerun(remote, run_id, wait_seconds=args.wait)
    except RemoteError as error:
        print(f"远端错误：{error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        mark = {"succeeded": "✓", "failed": "✕", "running": "…"}.get(result["status"], "?")
        print(f"{mark} 重跑 {run_id[:8]} → run {result['run_id']} · {result['status']}")
        for key, value in (result["outputs"] or {}).items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            print(f"  {key} = {text[:500]}")
        if result.get("error"):
            print(f"  错误：{str(result['error'])[:300]}")
    return {"succeeded": 0, "failed": 1}.get(result["status"], 3)


def export_main(argv: list[str]) -> int:
    """guanjia export <工作流> [-o 文件|-]：导出可搬运的快照 JSON。"""
    parser = argparse.ArgumentParser(prog="guanjia export", description="导出工作流快照 JSON")
    parser.add_argument("name", help="工作流名字（唯一子串）或 id")
    parser.add_argument("-o", "--out", default=None, help="输出文件；- 表示标准输出")
    args = parser.parse_args(argv)

    cfg = load_config()
    if not cfg["token"]:
        print("未登录：先 guanjia --login", file=sys.stderr)
        return 1
    remote = RemoteClient(cfg["server"], cfg["token"])
    try:
        target = _resolve(workflow.list_workflows(remote), args.name)
    except RemoteError as error:
        print(f"远端不可达或登录失效：{error}", file=sys.stderr)
        return 1
    if isinstance(target, list):
        print(f"找不到唯一匹配「{args.name}」", file=sys.stderr)
        return 2
    try:
        payload = workflow.export_snapshot(remote, target["id"])
    except RemoteError as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
        return 0
    safe = "".join(c for c in target["name"] if c not in '\\/:*?"<>|') or "workflow"
    out = args.out or f"{safe}.guanjia.json"
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    nodes = len(payload["snapshot"]["workflow"].get("nodes", []))
    print(f"✓ 已导出「{target['name']}」→ {out}（{nodes} 节点，rev {payload.get('revision')}）")
    return 0
