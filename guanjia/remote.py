"""远端平台客户端：guanjia 与世界的唯一通道（urllib，零依赖）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class RemoteError(RuntimeError):
    def __init__(self, status: int, detail: str):
        # status 0 是"压根没收到 HTTP 响应"的内部记号，不是状态码。
        # 印成 "remote 0:" 只会让人以为是个错误代码去搜。
        prefix = f"remote {status}: " if status else ""
        super().__init__(f"{prefix}{detail[:200]}")
        self.status = status


class RemoteUnreachable(RemoteError):
    """连不上/超时——和"服务器答了但答的是错误码"不是一回事。

    此前这类异常直接裸奔到用户面前（六个入口全是 traceback），
    而各处写好的"远端不可达"提示语反倒成了死代码。
    """

    def __init__(self, server: str, reason: object):
        super().__init__(0, f"连不上 {server}：{reason}")


def next_step(error: RemoteError) -> str:
    """把一个远端错误翻成"所以你该做什么"。

    按原因分岔：连不上的人再怎么登录也没用，令牌过期的人不需要重新部署。
    各入口共用这一份，省得措辞各写各的、还都不分原因。
    """
    if isinstance(error, RemoteUnreachable):
        return ("连不上后端。guanjia 是薄客户端，得有一个工作流平台在跑：\n"
                "  · 已经部署过：确认它启动了、地址端口没写错（guanjia remote）\n"
                "  · 还没有后端：见项目主页「后端」一节\n"
                "  · 想看完整自查：guanjia doctor")
    if error.status in (401, 403):
        return "登录态失效了，重新登录：guanjia --login"
    if error.status == 404:
        return "远端没有这个接口——多半是后端版本较旧，或地址指错了地方。"
    if error.status >= 500:
        return "后端自己出错了，稍后再试；持续如此就去看后端日志。"
    return "哪里不对可以自查：guanjia doctor"


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
