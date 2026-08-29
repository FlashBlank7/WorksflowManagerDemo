"""会话持久化：CLI 与 Web 共享的本地对话存储（~/.guanjia/sessions/）。

薄壳原则不破：存的只是对话文本与展示性动作行，能力仍在远端。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from .config import make_private, write_private

DIR = Path.home() / ".guanjia" / "sessions"


def _path(sid: str) -> Path:
    return DIR / f"{sid}.json"


def _tighten_dir() -> None:
    """会话目录收成 0700。**读的时候也收，不只是写的时候。**

    配置那边已经学过这一课：只在写的路径上收权限，
    这次改动之前就存在的文件永远收不到——用户只要不再新增会话，
    那些 0644 的对话记录就一直躺着给同机所有人看。
    会话比配置更容易只读不写（翻旧对话、`guanjia sessions` 列个清单）。

    目录是真正的那道门：0700 之后别人根本进不来，
    里面单个文件是什么权限都无所谓了。所以这一句最要紧。
    收不动就算了——读不到会话比权限松更糟。
    """
    try:
        if DIR.is_dir() and DIR.stat().st_mode & 0o077:
            DIR.chmod(0o700)
    except OSError:
        pass


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
    _tighten_dir()      # 会话目录里是对话内容，同机其他用户不该看得到
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
    _tighten_dir()
    make_private(path)      # 老版本建的会话文件是 0644，读到才有机会收
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def list_sessions() -> list[dict]:
    # 这里不用再收权限：下面每条都走 load，收在那儿了。
    # （第一版在这儿也写了一句 _tighten_dir()，变异验证显示它是等价变异——
    #  删掉一条测试都不红。看着像在把关、实际什么也没做的代码比没有更糟。）
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
