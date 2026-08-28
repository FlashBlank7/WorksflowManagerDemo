"""工作流插件：生成（远端构建）与管理（列表/运行/历史）都在远端完成。"""

from __future__ import annotations

import json
import time
from datetime import datetime

from ..remote import RemoteClient, RemoteError


def list_workflows(remote: RemoteClient) -> list[dict]:
    apps = remote.request("GET", "/api/v1/applications")
    items = apps if isinstance(apps, list) else apps.get("applications", [])
    return [
        {
            "id": a["id"],
            "name": a.get("name", ""),
            "description": a.get("display_description") or a.get("description", ""),
            "version": a.get("active_version"),
            "published": bool(a.get("active_version")),
        }
        for a in items
    ]


def generate(remote: RemoteClient, requirement: str, thinking_enabled: bool, effort: str) -> dict:
    app = remote.request("POST", "/api/v1/applications", {
        "name": requirement[:24] or "新工作流",
        "requirement": requirement,
    })
    build = remote.request("POST", f"/api/v1/applications/{app['id']}/builds", {
        "requirement": requirement,
        "auto_publish": True,
        "max_turns": 36,
        "max_repair_cycles": 3,
        "max_elapsed_seconds": 1800,
        "thinking_enabled": thinking_enabled,
        "effort": effort,
    })
    return {"app_id": app["id"], "build_id": build["build_id"]}


def build_status(remote: RemoteClient, build_id: str) -> dict:
    build = remote.request("GET", f"/api/v1/builds/{build_id}")
    narration = ""
    try:
        transcript = remote.request("GET", f"/api/v1/builds/{build_id}/transcript")
        for record in reversed(transcript.get("records", [])):
            if record.get("text") and record.get("kind") not in ("owner", "event"):
                narration = record["text"][:160]
                break
    except Exception:
        pass
    state = build.get("team_state", {})
    return {
        "status": build.get("status"),
        "revision": state.get("revision"),
        "published_version": state.get("published_version"),
        "pending_question": state.get("pending_question"),
        "error": (build.get("error") or "")[:200],
        "narration": narration,
    }


class InputTypeError(ValueError):
    """输入值与声明类型不符——要让用户看见并改，不能静默丢键。"""


def coerce_input(raw: str, declared_type: str | None) -> object:
    """命令行拿到的永远是字符串，按工作流声明的类型转成真实值。

    真机上 60 个声明输入里 32 个 type=array —— 不转换的话这些工作流从
    `guanjia run` / cron 出口 100% 跑不通，报错还指向下游节点让人摸不着头脑。
    网页壳 app.js 的 coerceInput() 是同一套规则，改这里记得同步改那边。
    """
    kind = str(declared_type or "string").lower()
    if kind in ("array", "object", "any", "json"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise InputTypeError(f"要填 {kind} 类型的 JSON：{error}") from error
    if kind in ("number", "float"):
        try:
            return float(raw)
        except ValueError as error:
            raise InputTypeError("要填数字") from error
    if kind in ("integer", "int"):
        try:
            return int(raw)
        except ValueError as error:
            raise InputTypeError("要填整数") from error
    if kind in ("boolean", "bool"):
        return raw.strip().lower() in ("true", "1", "yes", "y", "是", "on")
    return raw


def input_schema(remote: RemoteClient, app_id: str) -> list[dict]:
    draft = remote.request("GET", f"/api/v1/applications/{app_id}/draft")
    for node in draft["snapshot"]["workflow"]["nodes"]:
        if node.get("type") == "start":
            return [
                {"name": i["name"], "label": i.get("label") or i["name"],
                 "type": i.get("type") or "string", "example": i.get("example", ""),
                 # 缺了必填项就别发请求——服务端会建一条注定失败的运行记录
                 "required": bool(i.get("required", True))}
                for i in (node.get("config") or {}).get("inputs") or []
            ]
    return []


TERMINAL_STATUSES = ("succeeded", "failed", "paused", "cancelled")


def _result_outputs(run: dict) -> dict:
    """运行结果的权威来源是顶层 outputs；老远端没有时才退回 state 里逐节点拍平。

    拍平是兜底路径：那里装的是每个节点的中间态，键会互相覆盖，
    展示出来常常是「某个中间节点的 payload」而不是工作流声明的业务结果。
    """
    outputs = run.get("outputs")
    if isinstance(outputs, dict) and outputs:
        return outputs
    flat: dict = {}
    state = run.get("state") or {}
    for node_id, value in (state.get("outputs") or {}).items():
        if not isinstance(value, dict):
            continue
        for key, item in value.items():
            flat[f"{node_id}.{key}" if key in flat else key] = item
    return flat


def _result_error(run: dict) -> str:
    """错误权威来源是顶层 error；state 里没有 error 字段（平台模型压根没定义）。"""
    return str(run.get("error") or (run.get("state") or {}).get("error") or "")


def wait_for(remote: RemoteClient, run_id: str, wait_seconds: float = 45.0) -> dict:
    """等一个已创建的运行出结果。run() 与 --follow 的降级路径共用。"""
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        current = remote.request("GET", f"/api/v1/runs/{run_id}")
        if current["status"] in TERMINAL_STATUSES:
            result = {"run_id": run_id, "status": current["status"],
                      "outputs": _result_outputs(current), "error": _result_error(current),
                      "by": str(current.get("triggered_by") or "")}
            if current["status"] == "paused":
                result["waiting_node_id"] = (current.get("state") or {}).get("waiting_node_id")
            return result
        time.sleep(1.5)
    return {"run_id": run_id, "status": "running", "outputs": {}, "error": None, "by": ""}


def run(remote: RemoteClient, app_id: str, inputs: dict, wait_seconds: float = 45.0) -> dict:
    created = remote.request("POST", f"/api/v1/applications/{app_id}/runs", {"inputs": inputs})
    run_id = created["run_id"]
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        current = remote.request("GET", f"/api/v1/runs/{run_id}")
        if current["status"] in TERMINAL_STATUSES:
            result = {"run_id": run_id, "status": current["status"],
                      "outputs": _result_outputs(current), "error": _result_error(current),
                      "by": str(current.get("triggered_by") or "")}
            if current["status"] == "paused":
                result["waiting_node_id"] = (current.get("state") or {}).get("waiting_node_id")
            return result
        time.sleep(1.5)
    return {"run_id": run_id, "status": "running", "outputs": {}, "error": None}


def run_history(remote: RemoteClient, app_id: str, limit: int = 10) -> list[dict]:
    """最近运行：状态/时间/错误或首个输出摘要，给详情页一眼看。"""
    runs = remote.request("GET", f"/api/v1/applications/{app_id}/runs?limit={int(limit)}")
    items = []
    for r in runs if isinstance(runs, list) else []:
        outputs = _result_outputs(r)
        brief = ""
        for key, value in outputs.items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            brief = f"{key} = {text[:80]}"
            break
        items.append({
            "id": r.get("id"),
            "status": r.get("status"),
            # 谁触发的：空串是定时/系统触发或老数据
            "by": str(r.get("triggered_by") or ""),
            "at": str(r.get("created_at") or "")[:19].replace("T", " "),
            "error": _result_error(r)[:120],
            "brief": brief,
        })
    return items


def _map_events(payload: dict) -> list[dict]:
    """事件 → 时间线行：时刻/类型/标题/附注（节点耗时、错误截断）。纯函数便于测试。"""
    rows: list[dict] = []
    started: dict[str, str] = {}
    for event in payload.get("events", []):
        data = event.get("data") or {}
        at = str(event.get("at") or "")
        etype = str(event.get("type") or "")
        node = str(data.get("node_id") or "")
        label = str(data.get("title") or node or etype)[:60]
        extra = ""
        if etype == "node.started" and node:
            started[node] = at
        if etype == "node.completed" and node in started:
            try:
                delta = (datetime.fromisoformat(at)
                         - datetime.fromisoformat(started[node])).total_seconds()
                extra = f"{delta:.1f}s"
            except ValueError:
                pass
        error = data.get("error")
        if error:
            extra = (extra + " · " if extra else "") + str(error)[:160]
        rows.append({"at": at[11:19], "type": etype, "label": label, "extra": extra})
    return rows


def run_events(remote: RemoteClient, run_id: str) -> list[dict]:
    return _map_events(remote.request("GET", f"/api/v1/runs/{run_id}/events/list?limit=500"))


def rerun(remote: RemoteClient, run_id: str, wait_seconds: float = 45.0) -> dict:
    """用原输入重跑：读旧 run 的 application_id 与 state.inputs，建新 run。"""
    old = remote.request("GET", f"/api/v1/runs/{run_id}")
    app_id = str(old.get("application_id") or "")
    inputs = (old.get("state") or {}).get("inputs") or {}
    workflow_name = ""
    try:  # 名字取应用行的当前名——发布版快照里可能是改名前的旧名
        app = remote.request("GET", f"/api/v1/applications/{app_id}")
        workflow_name = str(app.get("name") or "")
    except RemoteError:
        pass
    result = run(remote, app_id, inputs, wait_seconds=wait_seconds)
    result["application_id"] = app_id
    result["workflow"] = workflow_name
    result["inputs"] = inputs
    return result


def find_run(remote: RemoteClient, prefix: str) -> str | None:
    """按 id 前缀在各应用近期运行里找唯一命中；找不到或歧义返回 None。"""
    hits: set[str] = set()
    for app in list_workflows(remote):
        try:
            runs = remote.request("GET", f"/api/v1/applications/{app['id']}/runs?limit=30")
        except Exception:  # noqa: BLE001 - 单应用查询失败不拦整体
            continue
        for r in runs if isinstance(runs, list) else []:
            rid = str(r.get("id") or "")
            if rid.startswith(prefix):
                hits.add(rid)
    return hits.pop() if len(hits) == 1 else None


def start_run(remote: RemoteClient, app_id: str, inputs: dict) -> str:
    """只创建不等待，返回 run_id（--follow 用）。"""
    return remote.request("POST", f"/api/v1/applications/{app_id}/runs",
                          {"inputs": inputs})["run_id"]


TERMINAL_EVENTS = ("workflow.completed", "workflow.failed",
                   "workflow.cancelled", "workflow.paused")


def follow_run(remote: RemoteClient, run_id: str):
    """直播一个运行的事件（时间线行），terminal 事件后自然收尾。"""
    t0 = time.time()
    for event in remote.stream(f"/api/v1/runs/{run_id}/events"):
        if not isinstance(event, dict):
            continue
        etype = str(event.get("_event") or event.get("type") or "")
        node = str(event.get("node_id") or "")
        yield {
            "elapsed": time.time() - t0,
            "type": etype,
            "label": str(event.get("title") or node or "")[:60],
            "error": str(event.get("error") or "")[:160],
        }
        if etype in TERMINAL_EVENTS:
            return


def export_snapshot(remote: RemoteClient, app_id: str) -> dict:
    """导出：draft 快照（含 workflow/agents/tests/requirement），可搬运的自包含 JSON。"""
    draft = remote.request("GET", f"/api/v1/applications/{app_id}/draft")
    return {
        "guanjia_export": 1,
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "revision": draft.get("revision"),
        "snapshot": draft["snapshot"],
    }


def import_snapshot(remote: RemoteClient, payload: dict,
                    name: str | None = None, publish: bool = True) -> dict:
    """导入：建壳 → 元数据/agents → replace_workflow 整片（远端全图校验）→
    replace_tests（需含 mandatory 用例才发）→ 尝试发布。
    返回 {app_id, name, revision, published, publish_error, skipped_tests}。"""
    if not isinstance(payload, dict):
        # 典型来源：guanjia export X -o - | jq '.snapshot.workflow.nodes' | guanjia import -
        raise ValueError("不是有效的导出文件：顶层应该是一个对象")
    snap = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    if not isinstance(snap.get("workflow"), dict):
        raise ValueError("不是有效的导出文件：缺 snapshot.workflow")
    app_name = name or str(snap.get("name") or "导入的工作流")
    created_meta = {"description": str(snap.get("description") or ""),
                    "requirement": str(snap.get("requirement") or "")}
    app = remote.request("POST", "/api/v1/applications",
                         {"name": app_name, **created_meta})
    app_id = app["id"]
    revision = remote.request("GET", f"/api/v1/applications/{app_id}/draft")["revision"]
    seq = 0

    def op(op_name: str, data: dict):
        nonlocal revision, seq
        seq += 1
        result = remote.request("POST", f"/api/v1/applications/{app_id}/draft", {
            "expected_revision": revision, "idempotency_key": f"import-{seq}",
            "op": op_name, "data": data,
        })
        revision = result["revision"]

    # 只补建壳时没带上的元数据。建壳已经把 description/requirement 写进去了，
    # 再原样发一次是空操作，远端会 422「draft operation would not change the
    # workflow」——整个导入就断在这里，导出的工作流搬不过去。
    try:
        # 只补建壳时没带上的元数据。建壳已经把 description/requirement 写进去了，
        # 再原样发一次是空操作，远端会 422「draft operation would not change the
        # workflow」——整个导入就断在这里，导出的工作流搬不过去。
        meta = {key: snap[key] for key in ("description", "requirement")
                if snap.get(key) and snap[key] != created_meta.get(key)}
        if meta:
            op("set_metadata", meta)
        for agent in (snap.get("agents") or {}).values():
            op("upsert_agent", {"agent": agent})
        op("replace_workflow", {"workflow": snap["workflow"]})
        tests = snap.get("tests") or []
        skipped_tests = False
        if tests:
            if any(t.get("mandatory") for t in tests):
                op("replace_tests", {"tests": tests})
            else:
                skipped_tests = True  # 远端要求至少一条 mandatory
    except Exception:
        # 壳是先建的：中途失败就把它收起来，别在列表里留一具空壳。
        # 真机上一次失败的导入就这么留下了一个同名草稿，
        # 下次按名字找它时变成「有歧义，匹配到多个」。
        try:
            remote.request("POST", f"/api/v1/applications/{app_id}/archive",
                           {"archived": True})
        except Exception:  # noqa: BLE001 - 老远端没有归档接口，收不掉就算了
            pass
        raise
    published = False
    publish_error = ""
    if publish:
        try:
            remote.request("POST", f"/api/v1/applications/{app_id}/versions",
                           {"acknowledge_warnings": True})
            published = True
        except RemoteError as error:
            publish_error = str(error)[:300]
    return {"app_id": app_id, "name": app_name, "revision": revision,
            "published": published, "publish_error": publish_error,
            "skipped_tests": skipped_tests}


def run_artifacts(remote: RemoteClient, run_id: str) -> list[dict]:
    """一次运行落盘的产物文件（name/size），没有则空表。"""
    return remote.request("GET", f"/api/v1/runs/{run_id}/artifacts")
