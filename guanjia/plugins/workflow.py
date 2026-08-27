"""工作流插件：生成（莉莉丝构建）与管理（列表/运行/历史）都在远端完成。"""

from __future__ import annotations

import json
import time
from datetime import datetime

from ..remote import RemoteClient


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


def input_schema(remote: RemoteClient, app_id: str) -> list[dict]:
    draft = remote.request("GET", f"/api/v1/applications/{app_id}/draft")
    for node in draft["snapshot"]["workflow"]["nodes"]:
        if node.get("type") == "start":
            return [
                {"name": i["name"], "label": i.get("label") or i["name"],
                 "type": i.get("type") or "string", "example": i.get("example", "")}
                for i in (node.get("config") or {}).get("inputs") or []
            ]
    return []


def run(remote: RemoteClient, app_id: str, inputs: dict, wait_seconds: float = 45.0) -> dict:
    created = remote.request("POST", f"/api/v1/applications/{app_id}/runs", {"inputs": inputs})
    run_id = created["run_id"]
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        current = remote.request("GET", f"/api/v1/runs/{run_id}")
        if current["status"] in ("succeeded", "failed"):
            outputs = {}
            for value in (current["state"].get("outputs") or {}).values():
                if isinstance(value, dict):
                    outputs.update(value)
            return {"run_id": run_id, "status": current["status"],
                    "outputs": outputs, "error": current["state"].get("error")}
        time.sleep(1.5)
    return {"run_id": run_id, "status": "running", "outputs": {}, "error": None}


def run_history(remote: RemoteClient, app_id: str, limit: int = 10) -> list[dict]:
    """最近运行：状态/时间/错误或首个输出摘要，给详情页一眼看。"""
    runs = remote.request("GET", f"/api/v1/applications/{app_id}/runs?limit={int(limit)}")
    items = []
    for r in runs if isinstance(runs, list) else []:
        state = r.get("state") or {}
        outputs = {}
        for value in (state.get("outputs") or {}).values():
            if isinstance(value, dict):
                outputs.update(value)
        brief = ""
        for key, value in outputs.items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            brief = f"{key} = {text[:80]}"
            break
        items.append({
            "id": r.get("id"),
            "status": r.get("status"),
            "at": str(r.get("created_at") or "")[:19].replace("T", " "),
            "error": str(state.get("error") or r.get("error") or "")[:120],
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
    result = run(remote, app_id, inputs, wait_seconds=wait_seconds)
    result["application_id"] = app_id
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
