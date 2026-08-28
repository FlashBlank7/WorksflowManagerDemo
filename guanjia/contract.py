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

OK = "\x1b[32m✓\x1b[0m"
BAD = "\x1b[31m✕\x1b[0m"
WARN = "\x1b[33m!\x1b[0m"
DIM = "\x1b[2m"
NORM = "\x1b[0m"

# (路径, 必需?, 少了会怎样, 响应里必须有的字段)
#
# 字段清单是从客户端**实际读取的地方**倒推来的，不是拍脑袋列的。
# "a.b" 表示嵌套；"[].x" 表示「响应是数组，每个元素要有 x」。
READ_ENDPOINTS = (
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
    if missing_required:
        print(f"{BAD} 缺 {len(missing_required)} 个必需接口：{'、'.join(missing_required)}")
        print("  guanjia 装不上这样的后端；先把它们实现了。")
        return 1
    if degraded:
        print(f"{WARN} 必需接口齐了；{len(degraded)} 个可选接口缺失，"
              f"相应功能会静默降级：{'、'.join(degraded)}")
        return 0
    print(f"{OK} 只读接口全齐——guanjia 能完整发挥。")
    return 0
