"""后端契约自查：guanjia doctor --contract。

guanjia 只经 HTTP 跟后端说话，理论上换谁来实现都行——但"理论上"没法验证。
这里把 README 那张接口表变成能跑的探测：少了哪个、少了会怎样，一目了然。

想自己实现后端的人照着跑一遍就知道还差什么；
用户看不到某一块信息时，也能立刻分辨是"后端没这个接口"还是"真的没数据"。

只探测只读接口。会改动数据的接口（建应用、发起运行、开构建）一律不碰——
自查工具在别人的生产库上制造副作用是不可接受的，宁可如实说"没验"。
"""

from __future__ import annotations

import urllib.error

from .remote import RemoteClient, RemoteError, RemoteUnreachable

from .palette import paint, seq

# 上色与否由 palette 统一判（NO_COLOR / 非终端 一律不上色）
OK = paint("32", "✓")
BAD = paint("31", "✕")
WARN = paint("33", "!")
DIM = seq("2")
NORM = seq("0")

# (路径, 必需?, 少了会怎样, 响应里必须有的字段)
#
# 字段清单是从客户端**实际读取的地方**倒推来的，不是拍脑袋列的。
# "a.b" 表示嵌套；"[].x" 表示「响应是数组，每个元素要有 x」。
READ_ENDPOINTS = (
    # /health 一直没在表里，而 guanjia 拿它判"后端在不在"。
    # 少了它 doctor 的可达性那一行会走进 RemoteError 分支（当成"有路由"），
    # 契约检查又根本不问——两边都不报，实现方却少了一个必需接口。
    ("/health", True, "guanjia 判断不了后端在不在（doctor 的可达性一节）",
     ()),
    ("/api/v1/me", True, "认不出你是谁，登录态无从判断",
     ("user.name",)),
    ("/api/v1/applications", True, "列不出工作流——guanjia 基本没法用",
     ("[].id", "[].name")),
    ("/api/v1/overview", True, "today 统筹总览整块消失",
     ("runs_today.total", "runs_today.succeeded", "runs_today.failed",
      "published_workflows", "builds_active", "schedules", "recent_failures")),
    ("/api/v1/health-report", False, "体检一节不显示",
     ("counts", "items")),
    ("/api/v1/scheduler/health", False, "调度器死活显示为「未知（远端版本较旧）」",
     ("alive", "seconds_since_tick")),
    ("/api/v1/applications-archived", False, "看不了收起来的工作流", ()),
    ("/api/v1/applications-archivable", False, "「收拾列表」给不出建议", ()),
)

# 需要一个真实 ID 才能探的只读接口。以前一个都没查，而结尾却敢说
# "只读接口全齐"——客户端实际调 23 个端点，契约只提到 13 个。
# 后果是具体的：examples/minimal_backend.py 自己就实现了 draft 和 versions、
# 没实现 builds/transcript/artifacts/events，而契约检查照样全绿。
# 照着这份清单实现后端的人，检查通过之后 `guanjia show`、`guanjia logs` 才炸。
#
# 探法：先从列表接口拿一个真实 ID 再拼路径。仍然全是 GET，没有副作用。
ID_ENDPOINTS = (
    # 必需与否是照着调用点判的，不是照着"听起来重不重要"：
    # 这个接口客户端只在 rerun 里读一次工作流名，还包在
    # try/except RemoteError: pass 里——缺了只是重跑时名字空着。
    # 初稿我按直觉标了"必需"，查调用点才发现标错了。
    ("/api/v1/applications/{id}", "app", False,
     "重跑时显示不出工作流名字", ("id", "name")),
    ("/api/v1/applications/{id}/draft", "app", False,
     "看不了草稿结构", ()),
    ("/api/v1/applications/{id}/versions", "app", False,
     "列不出历史版本，回滚无从谈起", ()),
    ("/api/v1/applications/{id}/runs?limit=5", "app", True,
     "查不了某个工作流的运行记录", ()),
    ("/api/v1/builds/{id}", "build", False,
     "看不了搭建进度", ()),
    ("/api/v1/builds/{id}/transcript", "build", False,
     "看不了搭建过程，出问题无从判断卡在哪", ()),
    # 这个是真必需：跑工作流之后轮询结果就靠它，没兜底。
    ("/api/v1/runs/{id}", "run", True,
     "跑完了拿不到结果——run 会一直显示「还在跑」", ("status",)),
    ("/api/v1/runs/{id}/artifacts", "run", False,
     "下载不了运行产物", ()),
    ("/api/v1/runs/{id}/events/list?limit=20", "run", False,
     "看不了运行的流水账", ()),
)


# SSE 流式接口。**它们是 GET、没有副作用，本该被探，却一条都没在表里。**
#
# 2026-08-29 把"客户端源码里真会请求的路径"和"契约表里列的"对了一遍，
# 才发现 /api/v1/runs/{id}/events 从来没被检查过——
# 而结论那句写的是「只读接口全齐——guanjia 能完整发挥」。
# 一个只实现了 events/list、没实现 events 的后端会通过契约检查，
# 然后 `guanjia run --follow` 和 REPL 里的搭建跟踪当场不动。
# 这跟上一次的毛病是同一个：**结论说的比检查到的多**。
#
# 探法：开连接、看状态码、立刻关掉，一个事件都不读——
# 流是无限的，读下去这个检查就永远不返回。
STREAM_ENDPOINTS = (
    ("/api/v1/runs/{id}/events", "run", False,
     "run --follow 和 REPL 的搭建跟踪看不到实时进度（会退回轮询）"),
)


def missing_fields(payload, required: tuple) -> list[str]:
    """回「响应里少了哪些字段」。空表示形状没问题。

    只查「有没有」，不查类型：类型错了后面自然会炸，
    而漏字段是照着清单实现的人最容易犯、又最难自己发现的。
    """
    gaps = []
    for path in required:
        if path.startswith("[]."):
            key = path[3:]
            if not isinstance(payload, list):
                gaps.append(f"{path}（响应本身应该是数组）")
            elif payload and not isinstance(payload[0], dict):
                gaps.append(f"{path}（数组元素应该是对象）")
            elif payload and key not in payload[0]:
                gaps.append(path)
            continue
        node = payload
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                gaps.append(path)
                break
    return gaps

# 有副作用，绝不自动探测；列出来是给实现方看的清单
WRITE_ENDPOINTS = (
    ("POST /api/v1/applications/{id}/archive", "收起 / 拿回工作流"),
    ("POST /api/v1/assistant/agent/stream", "管家对话（流式）"),
    ("POST /api/v1/auth/register", "注册"),
    ("POST /api/v1/auth/login", "登录"),
    ("POST /api/v1/assistant/agent", "对话管家（招牌功能，必需）"),
    ("POST /api/v1/applications/{id}/runs", "跑一个工作流"),
    ("POST /api/v1/applications/{id}/builds", "生成工作流"),
    ("POST /api/v1/builds/{id}/resume", "续跑构建"),
)


def _probe(client: RemoteClient, path: str,
           required: tuple = ()) -> tuple[str, str]:
    """回 (状态, 说明)。状态取 ok / shape / missing / error / unreachable。"""
    try:
        payload = client.request("GET", path)
        gaps = missing_fields(payload, required)
        if gaps:
            return "shape", "少了字段：" + "、".join(gaps)
        return "ok", ""
    except RemoteUnreachable as error:
        return "unreachable", str(error)
    except RemoteError as error:
        if error.status in (404, 405):
            return "missing", f"HTTP {error.status}"
        if error.status in (401, 403):
            # 路由是在的，只是没权限——对契约而言算实现了
            return "ok", f"HTTP {error.status}（有路由，权限不足）"
        return "error", f"HTTP {error.status}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return "unreachable", str(error)


def _probe_stream(client: RemoteClient, path: str) -> tuple[str, str]:
    """探一个 SSE 端点：开连接、看状态、立刻关掉。

    走 client.probe_stream 而不是自己拼 urllib：探测逻辑一旦直接摸
    client.server，测试里的桩就得长得跟真客户端一模一样——
    那是"夹具与真值分家"的另一种写法。
    """
    try:
        code, kind = client.probe_stream(path)
    except urllib.error.HTTPError as error:
        if error.code in (404, 405):
            return "missing", f"HTTP {error.code}"
        if error.code in (401, 403):
            return "ok", f"HTTP {error.code}（有路由，权限不足）"
        return "error", f"HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return "unreachable", str(getattr(error, "reason", error))
    except AttributeError:
        # 老客户端/桩没有这个方法：如实说没验，别假装验过
        return "unsampled", "这个客户端不支持探流式接口"
    if code != 200:
        return "error", f"HTTP {code}"
    if kind and kind != "text/event-stream":
        # 路由在，但答的不是流——客户端会一直等不到事件
        return "shape", f"Content-Type 是 {kind}，不是 text/event-stream"
    return "ok", ""


def _sample_ids(client: RemoteClient) -> dict[str, str | None]:
    """从列表接口各取一个真实 ID，用来探那些需要 ID 的只读接口。

    取不到就返回 None，对应的探测跳过并如实说"没验"——
    空库上探不了不是后端的错，但也不能假装验过了。
    """
    def first_id(path: str) -> str | None:
        try:
            rows = client.request("GET", path)
        except Exception:      # noqa: BLE001 - 探测工具不该因为取样失败就崩
            return None
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("builds") or rows.get("runs") or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            # id / run_id / build_id 都认——客户端对这几个键本来就是宽容的
            # （见 plugins/workflow._run_id_of）。探测器比客户端还严的话，
            # 会把"后端其实能用"误报成"库里没样本"。
            for key in ("id", "run_id", "build_id"):
                value = rows[0].get(key)
                if value:
                    return str(value)
        return None

    ids: dict[str, str | None] = {"app": None, "build": None, "run": None}
    # 构建和运行都挂在应用下面，没有全局列表接口——
    # 初稿在这里凭印象写了 /api/v1/builds?limit=1 和 /api/v1/runs?limit=1，
    # 两个都是 404，于是 5 个接口全报"库里没样本"，
    # 而真机上明明有 75 个构建、124 次运行。
    # 教训还是那个：探测器自己也得验，不然它报的"没验"可能是它自己找错了地方。
    ids["app"] = first_id("/api/v1/applications")
    if ids["app"]:
        ids["run"] = first_id(f"/api/v1/applications/{ids['app']}/runs?limit=1")
        ids["build"] = first_id(f"/api/v1/applications/{ids['app']}/builds")
    return ids


def run(cfg: dict) -> int:
    """逐条探测并打印。回 0 表示必需接口齐全。"""
    client = RemoteClient(cfg["server"], cfg["token"], timeout=8.0)
    print(f"后端契约自查 {DIM}{cfg['server']}{NORM}")

    missing_required: list[str] = []
    degraded: list[str] = []
    shape_gaps: list[str] = []
    for path, required, consequence, fields in READ_ENDPOINTS:
        state, note = _probe(client, path, fields)
        if state == "unreachable":
            print(f"{BAD} 连不上后端：{note}")
            return 1
        tail = f"  {DIM}{note}{NORM}" if note else ""
        if state == "ok":
            print(f"{OK} {path}{tail}")
        elif state == "shape":
            # 路由在，形状不对——照清单实现的人最容易栽在这里
            shape_gaps.append(f"{path}：{note}")
            print(f"{WARN} {path}  {DIM}{note}{NORM}")
        elif state == "missing":
            mark, bucket = (BAD, missing_required) if required else (WARN, degraded)
            bucket.append(path)
            label = "必需" if required else "可选"
            print(f"{mark} {path}  {DIM}{label}·缺失 → {consequence}{NORM}")
        else:
            print(f"{WARN} {path}  {DIM}答了但不正常（{note}）{NORM}")

    ids = _sample_ids(client)
    unsampled: list[str] = []
    for template, kind, required, consequence, fields in ID_ENDPOINTS:
        sample = ids.get(kind)
        if not sample:
            unsampled.append(template)
            print(f"{WARN} {template}  {DIM}没验：库里没有可用的{kind}做样本{NORM}")
            continue
        path = template.replace("{id}", str(sample))
        state, note = _probe(client, path, fields)
        shown = template
        tail = f"  {DIM}{note}{NORM}" if note else ""
        if state == "ok":
            print(f"{OK} {shown}{tail}")
        elif state == "shape":
            shape_gaps.append(f"{shown}：{note}")
            print(f"{WARN} {shown}  {DIM}{note}{NORM}")
        elif state == "missing":
            mark, bucket = (BAD, missing_required) if required else (WARN, degraded)
            bucket.append(shown)
            label = "必需" if required else "可选"
            print(f"{mark} {shown}  {DIM}{label}·缺失 → {consequence}{NORM}")
        else:
            print(f"{WARN} {shown}  {DIM}答了但不正常（{note}）{NORM}")

    for template, kind, required, consequence in STREAM_ENDPOINTS:
        sample = ids.get(kind)
        if not sample:
            unsampled.append(template)
            print(f"{WARN} {template}  {DIM}没验：库里没有可用的{kind}做样本{NORM}")
            continue
        state, note = _probe_stream(client, template.replace("{id}", str(sample)))
        if state == "unsampled":
            unsampled.append(template)
            print(f"{WARN} {template}  {DIM}没验：{note}{NORM}")
            continue
        if state == "ok":
            print(f"{OK} {template}  {DIM}{note or '实时流'}{NORM}")
        elif state == "shape":
            shape_gaps.append(f"{template}：{note}")
            print(f"{WARN} {template}  {DIM}{note}{NORM}")
        elif state == "missing":
            mark, bucket = (BAD, missing_required) if required else (WARN, degraded)
            bucket.append(template)
            print(f"{mark} {template}  "
                  f"{DIM}{'必需' if required else '可选'}·缺失 → {consequence}{NORM}")
        else:
            print(f"{WARN} {template}  {DIM}答了但不正常（{note}）{NORM}")

    print(f"\n{DIM}以下接口有副作用，不自动探测——自己实现后端的话别漏了：{NORM}")
    for name, purpose in WRITE_ENDPOINTS:
        print(f"  {DIM}· {name}  {purpose}{NORM}")

    print()
    if shape_gaps:
        print(f"{WARN} {len(shape_gaps)} 个接口在，但响应缺字段——"
              f"guanjia 读到一半会出错：")
        for gap in shape_gaps:
            print(f"  · {gap}")
        print()
    # 「没验」要在每一条结论里都说，不能只在全绿那条说。
    # 原先 degraded 分支直接 return 了，于是「必需接口齐了」这句话后面
    # 跟着 5 个根本没探过的接口，一个字不提——
    # 和这次修的主问题是同一个毛病，只是换了个分支。
    def note_unsampled() -> None:
        if unsampled:
            print(f"{DIM}  另有 {len(unsampled)} 个没验（库里没样本）："
                  f"{'、'.join(unsampled)}{NORM}")

    if missing_required:
        print(f"{BAD} 缺 {len(missing_required)} 个必需接口：{'、'.join(missing_required)}")
        print("  guanjia 装不上这样的后端；先把它们实现了。")
        note_unsampled()
        return 1
    if degraded:
        print(f"{WARN} 必需接口齐了；{len(degraded)} 个可选接口缺失，"
              f"相应功能会静默降级：{'、'.join(degraded)}")
        note_unsampled()
        return 0
    # 流式那张表也要计入——加了新表却不改这行的话，
    # 这个数会比实际查过的少，而这句话的全部意义就是数清楚查了几个。
    checked = (len(READ_ENDPOINTS) + len(ID_ENDPOINTS) + len(STREAM_ENDPOINTS)
               - len(unsampled))
    if shape_gaps:
        # 路由都在，但响应形状不对——**这时候不能说「能完整发挥」**。
        # 上面刚列完「guanjia 读到一半会出错」，结论却接一句「全齐」，
        # 读的人只会记住最后那句。同一个毛病这次换在结论和正文之间：
        # 结论说的比检查到的多。
        print(f"{WARN} {checked} 个只读接口路由都在，但上面 {len(shape_gaps)} 个"
              f"响应形状不对——先把字段补齐，否则 guanjia 会读到一半出错。")
        note_unsampled()
        return 0
    if unsampled:
        print(f"{WARN} 查过的 {checked} 个只读接口都齐了；")
        note_unsampled()
        return 0
    # 说"全齐"之前先数清楚查了几个。原先这句话是无条件打的，
    # 而当时表里只有 7 个端点、客户端实际调 23 个——
    # 照着检查结果实现后端的人会以为验完了。
    print(f"{OK} {checked} 个只读接口全齐——guanjia 能完整发挥。")
    return 0
