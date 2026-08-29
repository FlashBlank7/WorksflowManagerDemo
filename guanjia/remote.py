"""远端平台客户端：guanjia 与世界的唯一通道（urllib，零依赖）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _readable(body: str) -> str:
    """后端回的正文里，把给人看的那句取出来。

    FastAPI 的错误正文是 {"detail": "..."}。原先整串 JSON 直接印给用户：

        remote 500: {"detail":"internal boom"}

    平台那边客户端会打到的报错今天已经全部中文化了，
    这里把 detail 取出来，用户看到的就是那句中文，而不是一坨 JSON。
    """
    stripped = body.strip()
    if not (stripped.startswith("{") and "detail" in stripped):
        return body
    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return body
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return body


class RemoteError(RuntimeError):
    def __init__(self, status: int, detail: str):
        # status 0 是"压根没收到 HTTP 响应"的内部记号，不是状态码。
        # 印成 "remote 0:" 只会让人以为是个错误代码去搜。
        #
        # 200 同理：正文不是 JSON 时也走这里，而"remote 200"看着像成功，
        # 只会让人更糊涂——那一支的 detail 已经把话说清楚了，不用前缀。
        #
        # 其余状态码留着，但换成中文：出问题时它是有用的线索，
        # 只是不该以 "remote 500:" 这种开发者写法出现在用户面前。
        prefix = f"后端返回 {status}：" if status and status != 200 else ""
        super().__init__(f"{prefix}{_readable(detail)[:200]}")
        self.status = status


class RemoteUnreachable(RemoteError):
    """连不上/超时——和"服务器答了但答的是错误码"不是一回事。

    此前这类异常直接裸奔到用户面前（六个入口全是 traceback），
    而各处写好的"远端不可达"提示语反倒成了死代码。
    """

    def __init__(self, server: str, reason: object):
        super().__init__(0, f"连不上 {server}：{reason}")


class RemoteAddressInvalid(RemoteUnreachable):
    """服务器地址本身就不成立——还没轮到"连得上连不上"。

    2026-08-29 实测：`guanjia doctor --server 'http://[bad'` 打出

        出了意料之外的问题：Invalid IPv6 URL
        哪里不对可以自查：guanjia doctor

    两句都不对：地址写错是**最平常**的用户失误，不是"意料之外"；
    而它给出的下一步是"运行 guanjia doctor"——用户刚运行的就是它，
    这是个死圈。原因是 urllib.request.Request(...) 在 try 外面，
    它抛的 ValueError（unknown url type / Invalid IPv6 URL）
    不在捕获的那几类里。

    做成 RemoteUnreachable 的子类：各处已经写好的
    `except RemoteUnreachable` 一个都不用改就能接住它。
    """

    def __init__(self, server: str, reason: object):
        RemoteError.__init__(
            self, 0,
            f"服务器地址不对：{server or '（空）'}（{reason}）。"
            f"要写成 http://主机:端口 这样的形式")


def next_step(error: RemoteError, *, has_token: bool = True) -> str:
    """把一个远端错误翻成"所以你该做什么"。

    按原因分岔：连不上的人再怎么登录也没用，令牌过期的人不需要重新部署。
    各入口共用这一份，省得措辞各写各的、还都不分原因。

    has_token 区分"从来没登录过"和"登录过但令牌失效了"。
    少了这个区分，全新用户第一次敲 `guanjia today` 会被告知
    「登录态失效了，重新登录」——他一次都还没登录过，
    这句话既说不通，也没告诉他第一步该干什么。
    """
    if isinstance(error, RemoteAddressInvalid):
        # 地址写歪的人不需要"确认后端启动了"——他需要改地址。
        # 分岔的意义就在这儿：给连不上的人的那三条对他一条都不适用。
        return ("改一下服务器地址：\n"
                "  guanjia remote                     # 看当前档案里写的是什么\n"
                "  guanjia remote add <名字> <地址>   # 换一个，形如 http://127.0.0.1:8000\n"
                "  或者这一次直接带上 --server http://主机:端口")
    if isinstance(error, RemoteUnreachable):
        return ("连不上后端。guanjia 是薄客户端，得有一个工作流平台在跑：\n"
                "  · 已经部署过：确认它启动了、地址端口没写错（guanjia remote）\n"
                "  · 还没有后端：见项目主页「后端」一节\n"
                "  · 想看完整自查：guanjia doctor")
    if error.status in (401, 403) and not has_token:
        # 一次都没登录过的人，不管远端回 401 还是 403，缺的都是同一步。
        # （这一条本来就有测试钉着；我拆 401/403 时差点把它拆散了，
        #   给 403 单写了一句短的，first_run 那条测试当场变红——测试是对的。）
        return ("还没登录过。第一次用先做这一步：\n"
                "  guanjia --login        # 填服务器地址、注册令牌、给自己起个用户名\n"
                "不知道服务器地址或注册令牌？找部署这套平台的人要。")
    if error.status == 401:
        return "登录态失效了，重新登录：guanjia --login"
    if error.status == 403:
        # 403 和 401 是两件事，原来合在一起说"重新登录"。
        # 平台的 403 是「这一步只有管理员能做——找这套平台的管理员帮忙」，
        # 也就是**登录是好的，权限不够**。让他再登一次同一个账号，
        # 只会撞同一堵墙——建议给错方向比不给更糟。
        # 具体原因平台已经写在 detail 里、调用方会连着一起印，
        # 所以这里不重复，只说清"不是登录的问题"。
        return ("登录是好的，是这个账号没这个权限——"
                "重新登录同一个账号也没用。看上面那句是谁能做。")
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
        # Request(...) 也要在 try 里面：地址写歪时它抛的是 ValueError
        # （Invalid IPv6 URL / unknown url type），而它原先在 try **外面**，
        # 于是这个最平常的用户失误一路裸奔到顶层，被印成
        # 「出了意料之外的问题：Invalid IPv6 URL」。
        try:
            request = urllib.request.Request(
                f"{self.server}{path}",
                method=method,
                data=json.dumps(body).encode("utf-8") if body is not None else None,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            raise RemoteError(error.code, error.read().decode("utf-8", errors="replace")) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # HTTPError 是 URLError 的子类，所以这一支必须排在它后面
            raise RemoteUnreachable(self.server, getattr(error, "reason", error)) from error
        except ValueError as error:
            raise RemoteAddressInvalid(self.server, error) from error
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            # 200 但正文不是 JSON：多半是地址指错了（指到别的服务或反代的错误页）
            raise RemoteError(
                200, f"返回的不是 JSON（对面可能不是 guanjia 平台）：{text[:120]}") from error

    def probe_stream(self, path: str) -> tuple[int, str]:
        """开一个 SSE 连接，看一眼状态和 Content-Type 就挂断，一个事件都不读。

        契约自查要用。不能借 request()——它把整个响应体读完再解析 JSON，
        而 SSE 是不结束的流：那样检查会挂到超时，再把一个活得好好的接口
        报成"连不上"。也不能借 stream()——它是生成器，一读就等事件。

        放在 RemoteClient 上而不是写在 contract.py 里，是为了让假客户端
        也能替换掉它：探测逻辑一旦直接摸 self.server，测试里的桩就得
        长得跟真客户端一模一样，那是另一种夹具与真值分家。
        """
        request = urllib.request.Request(
            f"{self.server}{path}", method="GET",
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "text/event-stream"})
        response = urllib.request.urlopen(request, timeout=self.timeout)
        try:
            return response.status, (
                response.headers.get("Content-Type") or "").split(";")[0].strip()
        finally:
            response.close()

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
