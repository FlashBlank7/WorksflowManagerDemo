"""远端平台客户端：guanjia 与世界的唯一通道（urllib，零依赖）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class RemoteError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"remote {status}: {detail[:200]}")
        self.status = status


class RemoteClient:
    def __init__(self, server: str, token: str, timeout: float = 120.0):
        self.server = server.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None) -> Any:
        request = urllib.request.Request(
            f"{self.server}{path}",
            method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RemoteError(error.code, error.read().decode("utf-8", errors="replace")) from error

    def stream(self, path: str, body: dict):
        """SSE 流：逐事件产出 dict。远端不支持时抛 RemoteError 由调用方回退。"""

        request = urllib.request.Request(
            f"{self.server}{path}", method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            raise RemoteError(error.code, error.read().decode("utf-8", errors="replace")) from error
        with response:
            for raw in response:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("data: "):
                    yield json.loads(line[6:])

    def health(self) -> dict:
        return self.request("GET", "/health")
