"""会话持久化：CLI 与 Web 共享的本地对话存储（~/.guanjia/sessions/）。

薄壳原则不破：存的只是对话文本与展示性动作行，能力仍在远端。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

DIR = Path.home() / ".guanjia" / "sessions"


def _path(sid: str) -> Path:
    return DIR / f"{sid}.json"


def new_session() -> str:
    return uuid4().hex[:8]


def save(sid: str, messages: list[dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    first_user = next((m for m in messages if m.get("role") == "user" and m.get("text")), None)
    _path(sid).write_text(json.dumps({
        "id": sid,
        "title": (first_user["text"][:24] if first_user else "新对话"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "messages": [m for m in messages if m.get("kind") != "answerbox"][-200:],
    }, ensure_ascii=False), encoding="utf-8")


def load(sid: str) -> dict | None:
    path = _path(sid)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_sessions() -> list[dict]:
    if not DIR.is_dir():
        return []
    items = []
    for path in DIR.glob("*.json"):
        data = load(path.stem)
        if data:
            items.append({"id": data["id"], "title": data.get("title", ""),
                          "updated_at": data.get("updated_at", "")})
    return sorted(items, key=lambda item: item["updated_at"], reverse=True)


def latest_id() -> str | None:
    items = list_sessions()
    return items[0]["id"] if items else None
