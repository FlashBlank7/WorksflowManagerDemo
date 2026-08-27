"""工作流插件：生成（莉莉丝构建）与管理（列表/运行/历史）都在远端完成。"""

from __future__ import annotations

import time

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
