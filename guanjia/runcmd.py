"""guanjia run：不进 REPL 直接跑一个已发布工作流——给脚本和 cron 的一次性出口。

    guanjia run GPU日报                    # 名字支持唯一子串匹配
    guanjia run 对账 month=2026-08 --json  # key=value 传输入，JSON 出结果
退出码：0 成功 · 1 失败/取消/未登录 · 2 参数或名字问题 · 3 超时仍在跑 · 4 等待人工输入。
"""

from __future__ import annotations


from .argparse_zh import ChineseArgumentParser
import json
import sys

from .config import load_config
from .plugins import workflow
from .remote import RemoteClient, RemoteError, next_step

MARKS = {"succeeded": "✓", "failed": "✕", "cancelled": "⊘", "paused": "⏸",
         "running": "…", "queued": "⋯"}
# 状态码是给机器看的。--json 那条路照给（脚本按它判），
# 人看的那一行换成中文——服务端今天把状态码从各个出口都堵掉了，
# 客户端这边还印着 `run run-0001 · succeeded`。
WORDS = {"succeeded": "跑成了", "failed": "没跑成", "cancelled": "取消了",
         "paused": "停下等人填", "running": "还在跑", "queued": "排队中"}
EXIT_CODES = {"succeeded": 0, "failed": 1, "cancelled": 1, "paused": 4}


def _say_no_match(wanted: str, matched: list, items: list) -> None:
    """名字对不上时，把候选列出来。

    原先只有 run 这么做，export 只回一句「找不到唯一匹配「X」」——
    同一件事两种待遇，而在 export 那条路上用户更需要提示：
    他多半正想不起来名字叫什么。
    """
    pool = matched or items
    head = "有歧义，匹配到多个" if matched else "找不到"
    print(f"{head}「{wanted}」，可选：", file=sys.stderr)
    for item in pool[:10]:
        state = "已发布" if item.get("published") else "未发布"
        print(f"  · {item['name']}（{state}）", file=sys.stderr)
    if len(pool) > 10:
        print(f"  …还有 {len(pool) - 10} 个，完整清单看 guanjia today", file=sys.stderr)


def _resolve(items: list[dict], needle: str):
    """精确 id/名字优先，其次唯一子串；返回 dict 或（歧义/空的）候选列表。"""
    for item in items:
        if item["id"] == needle or item["name"] == needle:
            return item
    hits = [item for item in items if needle.lower() in item["name"].lower()]
    return hits[0] if len(hits) == 1 else hits


def main(argv: list[str]) -> int:
    parser = ChineseArgumentParser(prog="guanjia run", description="直接运行一个已发布工作流")
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
        print(f"{error}\n{next_step(error)}", file=sys.stderr)
        return 1

    if not args.name.strip():
        # 空名字会被当成「匹配所有」，报出「有歧义，匹配到多个「」」——
        # 用户看了完全不知道自己做错了什么
        print("要给出工作流名字，比如：guanjia run 词频统计 text=…", file=sys.stderr)
        print("不记得名字就先看一眼：guanjia today", file=sys.stderr)
        return 2

    target = _resolve(items, args.name)
    if isinstance(target, list):
        _say_no_match(args.name, target, items)
        return 2
    if not target["published"]:
        print(f"「{target['name']}」还没有发布版本——先在对话里把它搭完。", file=sys.stderr)
        return 1

    # 声明的类型表要**无条件**取：命令行给的永远是字符串，array/object 必须转，
    # 否则声明了 array 的工作流从这个出口 100% 跑不通（真机 60 个输入里 32 个是 array）
    schema: list[dict] = []
    try:
        schema = workflow.input_schema(remote, target["id"])
    except RemoteError:
        pass
    types = {field["name"]: field.get("type") for field in schema}

    inputs: dict = {}
    for pair in args.pairs:
        if "=" not in pair:
            print(f"输入参数要写成 key=value，收到：{pair}", file=sys.stderr)
            return 2
        key, value = pair.split("=", 1)
        try:
            inputs[key] = workflow.coerce_input(value, types.get(key))
        except workflow.InputTypeError as error:
            print(f"输入 {key} 不对：{error}", file=sys.stderr)
            return 2

    if not args.json and sys.stdin.isatty():  # 交互场景补齐缺失输入
        for field in schema:
            if field["name"] in inputs:
                continue
            example = field.get("example")
            hint = f"（如 {json.dumps(example, ensure_ascii=False)[:60]}）" if example else ""
            value = input(f"  {field['label']} [{field.get('type') or 'string'}]{hint}: ").strip()
            if not value:
                continue
            try:
                inputs[field["name"]] = workflow.coerce_input(value, field.get("type"))
            except workflow.InputTypeError as error:
                print(f"输入 {field['name']} 不对：{error}", file=sys.stderr)
                return 2

    missing = [field for field in schema
               if field.get("required", True)
               and str(inputs.get(field["name"], "")).strip() == ""]
    if missing:
        # 别发这个请求：服务端会建一条运行记录、在 start 节点失败，
        # 那条失败永久留在历史里，还会让体检以为工作流坏了。
        names = "、".join(field["name"] for field in missing)
        print(f"还缺必填输入：{names}", file=sys.stderr)
        for field in missing:
            example = field.get("example")
            hint = f"，例如 {json.dumps(example, ensure_ascii=False)[:40]}" if example else ""
            print(f"  {field['name']}（{field.get('type') or 'string'}）"
                  f"{hint}", file=sys.stderr)
        print(f"照这样补上：guanjia run {target['name']} "
              + " ".join(f"{field['name']}=…" for field in missing), file=sys.stderr)
        return 2

    if args.follow:
        return _follow(remote, target, inputs)

    result = workflow.run(remote, target["id"], inputs, wait_seconds=args.wait)

    if args.json:
        print(json.dumps({"workflow": target["name"], **result}, ensure_ascii=False))
    else:
        mark = MARKS.get(result["status"], "?")
        # 没见过的状态宁可只印符号，也不把英文码抬出去
        word = WORDS.get(result["status"], "情况不明")
        print(f"{mark} {target['name']} · {word} · run {result['run_id']}")
        for key, value in (result["outputs"] or {}).items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            print(f"  {key} = {text[:500]}")
        if result.get("error"):
            print(f"  错误：{str(result['error'])[:300]}")
        if result["status"] == "running":
            print(f"  超过 --wait {args.wait:.0f}s 还在跑；稍后可在 REPL 问「run {result['run_id']} 结果如何」")
        if result["status"] == "paused":
            node = result.get("waiting_node_id") or "?"
            print(f"  等人工输入（节点 {node}）：到网页壳里填表，或在 guanjia 对话里回答")
    return EXIT_CODES.get(result["status"], 3)


def _follow(remote: RemoteClient, target: dict, inputs: dict) -> int:
    """--follow：创建后直播事件流，terminal 后补一段 outputs。"""
    run_id = workflow.start_run(remote, target["id"], inputs)
    print(f"▶ {target['name']} · run {run_id}（Ctrl+C 只停跟随，运行继续）")
    status = "running"
    deltas = 0
    try:
        for row in workflow.follow_run(remote, run_id):
            if row["type"].endswith(".delta"):  # 模型逐 token 事件：聚合成一行进度
                deltas += 1
                print(f"\r  …… 模型输出中（{deltas} 段）", end="", flush=True)
                continue
            if deltas:
                print()
                deltas = 0
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
    except (RemoteError, OSError) as error:
        # 老远端没有事件直播端点、或直播中途断了——run 已经建好了，
        # 别把它丢在半路，落回轮询等结果
        print(f"  （这个远端不支持事件直播或直播中断：{error}；改为等待结果）")
        final = workflow.wait_for(remote, run_id, wait_seconds=180.0)
        status = final["status"]
    outputs: dict = {}
    error = ""
    final: dict = {}
    try:
        final = remote.request("GET", f"/api/v1/runs/{run_id}")
        outputs = workflow._result_outputs(final)
        error = workflow._result_error(final)
        # 运行记录的 status 才是权威；事件推导出的 completed/failed 只是兜底词汇
        status = str(final.get("status") or {"completed": "succeeded"}.get(status, status))
    except RemoteError:
        status = {"completed": "succeeded"}.get(status, status)
    mark = MARKS.get(status, "…")
    print(f"{mark} {status}")
    for key, value in outputs.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        print(f"  {key} = {text[:500]}")
    if error:
        print(f"  错误：{error[:300]}")
    if status == "paused":
        node = (final.get("state") or {}).get("waiting_node_id") or "?"
        print(f"  等人工输入（节点 {node}）")
    return EXIT_CODES.get(status, 3)


def rerun_main(argv: list[str]) -> int:
    """guanjia rerun <run id 或前缀>：用原输入重跑一次失败/成功的运行。"""
    parser = ChineseArgumentParser(prog="guanjia rerun", description="用原输入重跑一次运行")
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
        print(f"{error}\n{next_step(error)}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        mark = MARKS.get(result["status"], "?")
        label = f"{result.get('workflow') or '工作流'} · " if result.get("workflow") else ""
        word = WORDS.get(result["status"], "情况不明")
        print(f"{mark} {label}重跑 {run_id[:8]} → {word} · run {result['run_id']}")
        for key, value in (result["outputs"] or {}).items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            print(f"  {key} = {text[:500]}")
        if result.get("error"):
            print(f"  错误：{str(result['error'])[:300]}")
    return EXIT_CODES.get(result["status"], 3)


def export_main(argv: list[str]) -> int:
    """guanjia export <工作流> [-o 文件|-]：导出可搬运的快照 JSON。"""
    parser = ChineseArgumentParser(prog="guanjia export", description="导出工作流快照 JSON")
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
        print(f"{error}\n{next_step(error)}", file=sys.stderr)
        return 1
    if isinstance(target, list):
        _say_no_match(args.name, target, workflow.list_workflows(remote))
        return 2
    try:
        payload = workflow.export_snapshot(remote, target["id"])
    except RemoteError as error:
        print(f"导出失败：{error}\n{next_step(error)}", file=sys.stderr)
        return 1
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
        return 0
    safe = "".join(c for c in target["name"] if c not in '\\/:*?"<>|') or "workflow"
    out = args.out or f"{safe}.guanjia.json"
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as error:
        print(f"写不了 {out}：{error}", file=sys.stderr)
        return 2
    nodes = len(payload["snapshot"]["workflow"].get("nodes", []))
    print(f"✓ 已导出「{target['name']}」→ {out}（{nodes} 节点，rev {payload.get('revision')}）")
    return 0


def import_main(argv: list[str]) -> int:
    """guanjia import <文件> [--name 新名] [--no-publish]：导入快照为新工作流。"""
    parser = ChineseArgumentParser(prog="guanjia import", description="导入工作流快照 JSON")
    parser.add_argument("file", help="guanjia export 产出的 .guanjia.json（- 读标准输入）")
    parser.add_argument("--name", default=None, help="导入后的名字（默认用快照里的）")
    parser.add_argument("--no-publish", action="store_true", help="只留草稿，不发布")
    args = parser.parse_args(argv)

    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        payload = json.loads(text)
    except OSError as error:
        print(f"读不了文件：{error}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print("文件不是 UTF-8 文本——快照要用 guanjia export 产出的 .guanjia.json",
              file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"不是合法 JSON：{error}", file=sys.stderr)
        return 2

    cfg = load_config()
    if not cfg["token"]:
        print("未登录：先 guanjia --login", file=sys.stderr)
        return 1
    remote = RemoteClient(cfg["server"], cfg["token"])
    try:
        result = workflow.import_snapshot(remote, payload, name=args.name,
                                          publish=not args.no_publish)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    except RemoteError as error:
        print(f"导入失败：{error}", file=sys.stderr)
        # 壳是先建的：告诉用户那半截东西清没清掉，别让他自己去列表里找
        if getattr(error, "guanjia_import_cleaned", None) is True:
            print("（这次导入建了一半的空壳已经替你收起来了，列表里不会多出东西）",
                  file=sys.stderr)
        elif getattr(error, "guanjia_import_cleaned", None) is False:
            app_id = getattr(error, "guanjia_import_app_id", "")
            print(f"（没能收起建了一半的空壳 {app_id[:8]}，可能要手动收一下）",
                  file=sys.stderr)
        print(next_step(error), file=sys.stderr)
        return 1

    state = "已发布" if result["published"] else "草稿（未发布）"
    print(f"✓ 导入「{result['name']}」→ {result['app_id'][:8]} · rev {result['revision']} · {state}")
    if result["skipped_tests"]:
        print("  测试用例未带 mandatory 标记，已跳过（对话里可以让它补验收）")
    if result["publish_error"]:
        print(f"  发布被拒：{result['publish_error']}")
        print("  草稿已留好——对话里说「把它跑过验收再发布」即可")
    return 0 if (result["published"] or not result["publish_error"]) else 1
