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


class RemoteUnreachable(RemoteError):
    """连不上/超时——和"服务器答了但答的是错误码"不是一回事。

    此前这类异常直接裸奔到用户面前（六个入口全是 traceback），
    而各处写好的"远端不可达"提示语反倒成了死代码。
    """

    def __init__(self, server: str, reason: object):
        super().__init__(0, f"连不上 {server}：{reason}")


def _lines(response, server: str):
    """逐行读 SSE：中途断连要变成 RemoteUnreachable，别让 http.client 的异常裸奔。"""
    try:
        for raw in response:
            yield raw
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RemoteUnreachable(server, getattr(error, "reason", error)) from error
    except Exception as error:  # noqa: BLE001 - http.client.IncompleteRead 等
        raise RemoteUnreachable(server, error) from error


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
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            raise RemoteError(error.code, error.read().decode("utf-8", errors="replace")) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # HTTPError 是 URLError 的子类，所以这一支必须排在它后面
            raise RemoteUnreachable(self.server, getattr(error, "reason", error)) from error
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            # 200 但正文不是 JSON：多半是地址指错了（指到别的服务或反代的错误页）
            raise RemoteError(
                200, f"返回的不是 JSON（对面可能不是 guanjia 平台）：{text[:120]}") from error

    def stream(self, path: str, body: dict | None = None):
        """SSE 流：逐事件产出 dict；body=None 走 GET（如运行事件直播）。
        带 event:/id: 行的流会把类型放进 _event、序号放进 _id（不覆盖数据本身的键）。
        远端不支持时抛 RemoteError 由调用方回退。"""

        request = urllib.request.Request(
            f"{self.server}{path}", method="GET" if body is None else "POST",
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            raise RemoteError(error.code, error.read().decode("utf-8", errors="replace")) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteUnreachable(self.server, getattr(error, "reason", error)) from error
        with response:
            etype = eid = None
            for raw in _lines(response, self.server):
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("event: "):
                    etype = line[7:]
                elif line.startswith("id: "):
                    eid = line[4:]
                elif line.startswith("data: "):
                    try:
                        payload = json.loads(line[6:])
                    except json.JSONDecodeError:
                        etype = eid = None   # 畸形行跳过，别打死整条流
                        continue
                    if isinstance(payload, dict):
                        if etype is not None:
                            payload.setdefault("_event", etype)
                        if eid is not None:
                            payload.setdefault("_id", eid)
                    yield payload
                    etype = eid = None

    def health(self) -> dict:
        return self.request("GET", "/health")
