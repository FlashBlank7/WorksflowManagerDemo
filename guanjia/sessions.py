"""会话持久化：CLI 与 Web 共享的本地对话存储（~/.guanjia/sessions/）。

薄壳原则不破：存的只是对话文本与展示性动作行，能力仍在远端。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from .config import write_private

DIR = Path.home() / ".guanjia" / "sessions"


def _path(sid: str) -> Path:
    return DIR / f"{sid}.json"


def new_session() -> str:
    return uuid4().hex[:8]


def save(sid: str, messages: list[dict]) -> bool:
    """存盘失败返回 False 而不是抛——HOME 只读/磁盘满时，
    招牌 REPL 不该在回答刚出来之后崩掉并把整段对话带走。"""
    try:
        return _save(sid, messages)
    except OSError:
        return False


def _save(sid: str, messages: list[dict]) -> bool:
    DIR.mkdir(parents=True, exist_ok=True)
    try:  # 会话目录里是对话内容，同机其他用户不该看得到
        DIR.chmod(0o700)
    except OSError:
        pass
    first_user = next((m for m in messages if m.get("role") == "user" and m.get("text")), None)
    # 和存令牌走同一份实现：一出生就 0600，写完换名过去。
    # 这里原来是 write_text 之后再 chmod——而 write_text 先截断，
    # 存到一半被中断（网页壳被 Ctrl-C、机器掉电）留下半截 json，
    # load 捕 JSONDecodeError 之后返回 None，**整段对话就这么没了**，
    # 而且丢的不只是这一轮：截断先发生，上一次存好的内容也一起没。
    write_private(_path(sid), json.dumps({
        "id": sid,
        "title": (first_user["text"][:24] if first_user else "新对话"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "messages": [m for m in messages if m.get("kind") != "answerbox"][-200:],
    }, ensure_ascii=False))
    return True


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
