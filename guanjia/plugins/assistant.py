"""助手插件：一般任务全部转发远端 /api/v1/assistant/chat。"""

from __future__ import annotations

from ..remote import RemoteClient


def chat(remote: RemoteClient, messages: list[dict]) -> dict:
    return remote.request("POST", "/api/v1/assistant/chat", {"messages": messages[-20:]})
