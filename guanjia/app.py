"""guanjia 本地壳：localhost 单页界面，一切能力经插件转发远端。

用法：guanjia web [--port 7800] [--open|--app]
--open 用默认浏览器打开；--app 以独立窗口打开（chromium 系 --app=URL，零依赖桌面壳）。
首次打开进入连接页：填远端地址 + 个人令牌（管理员在平台上用
POST /api/v1/users 为每人签发），保存于 ~/.bench.json。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from importlib import resources

from . import sessions
from .config import list_profiles, load_config, save_login, use_profile
from .plugins import PLUGINS, assistant, workflow
from .remote import RemoteClient, RemoteError


def _profiles_meta() -> dict:
    """给前端的档案元数据——绝不带令牌。"""
    active, profiles = list_profiles()
    return {"profile": active, "profiles": [
        {"name": name, "server": prof.get("server", ""), "user": prof.get("user", "")}
        for name, prof in profiles.items()]}


class Handler(BaseHTTPRequestHandler):
    remote: RemoteClient | None = None
    # 网页壳本身不做登录：它假设"能连到这个端口的人就是你"。
    # 绑到回环之外时这个假设不成立——同网段任何人都能用你的平台账号，
    # 所以非回环绑定强制要一把随机钥匙（回环仍然零摩擦）。
    access_key: str = ""

    def log_message(self, *args) -> None:
        pass

    def _proxy_artifact(self, rest: str) -> None:
        """二进制透传：/<run_id>/<产物路径> → 远端下载端点（带令牌）。"""
        import urllib.error
        import urllib.request

        run_id, _, art_path = rest.partition("/")
        remote = self._need_remote()
        request = urllib.request.Request(
            f"{remote.server}/api/v1/runs/{run_id}/artifacts/{art_path}",
            headers={"Authorization": f"Bearer {remote.token}"})
        try:
            with urllib.request.urlopen(request, timeout=120) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header("Content-Type",
                                 resp.headers.get("Content-Type") or "application/octet-stream")
                disposition = resp.headers.get("Content-Disposition")
                if disposition:
                    self.send_header("Content-Disposition", disposition)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as error:
            self._json({"error": f"remote {error.code}"}, error.code)

    def _json(self, data, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _need_remote(self) -> RemoteClient:
        if self.remote is None or not self.remote.token:
            raise RemoteError(401, "未配置远端连接")
        return self.remote

    def _asset(self, name: str, content_type: str) -> None:
        body = resources.files("guanjia").joinpath("web", name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._maybe_set_cookie()   # 带 ?k= 打开首页后记住，后续请求不用再带
        self.end_headers()
        self.wfile.write(body)

    def _key_ok(self) -> bool:
        """非回环绑定时校验访问密钥：URL 上带 ?k=，之后靠 Cookie 记住。

        这个函数在鉴权路径上——任何意外都必须变成"不通过"，
        而不是异常逃逸导致连接重置（那样客户端只看到 curl 52 号错误）。
        """
        if not Handler.access_key:
            return True
        try:
            return self._check_key()
        except Exception:  # noqa: BLE001 - 鉴权出意外一律判不通过
            return False

    def _check_key(self) -> bool:
        from http.cookies import SimpleCookie
        from urllib.parse import parse_qs, urlparse

        given = parse_qs(urlparse(self.path).query).get("k", [""])[0]
        # 记下"这次是从 URL 带钥匙来的"——路由稍后会把查询串剥掉，
        # 种 Cookie 时就看不到它了
        self._key_from_url = bool(given)
        if not given:
            raw = self.headers.get("Cookie") or ""
            try:
                given = SimpleCookie(raw).get("guanjia_key")
                given = given.value if given else ""
            except Exception:  # noqa: BLE001 - 坏 Cookie 当没有
                given = ""
        import hmac

        # 按字节比：compare_digest 对非 ASCII 字符串直接抛 TypeError，
        # 而它在鉴权路径上——抛出去就是连接被重置，而不是干净的 401
        return hmac.compare_digest(given.encode("utf-8"),
                                   Handler.access_key.encode("utf-8"))

    def _deny(self) -> None:
        body = ("访问密钥不对。启动 guanjia web 的那台机器上，"
                "终端里印着带 ?k=... 的完整地址，用那个打开。").encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _maybe_set_cookie(self) -> None:
        if Handler.access_key and getattr(self, "_key_from_url", False):
            self.send_header("Set-Cookie",
                             f"guanjia_key={Handler.access_key}; Path=/; SameSite=Strict")

    def do_GET(self) -> None:
        if not self._key_ok():
            return self._deny()
        # 路由只看路径：带访问密钥时地址是 /?k=xxx，不去掉查询串就匹配不上首页
        self.path = self.path.split("?")[0] or "/"
        try:
            if self.path == "/":
                self._asset("index.html", "text/html; charset=utf-8")
            elif self.path == "/static/style.css":
                self._asset("style.css", "text/css; charset=utf-8")
            elif self.path == "/static/app.js":
                self._asset("app.js", "text/javascript; charset=utf-8")
            elif self.path == "/api/bootstrap":
                if self.remote is None or not self.remote.token:
                    self._json({"configured": False, "plugins": PLUGINS, **_profiles_meta()})
                    return
                try:
                    me = self.remote.request("GET", "/api/v1/me")["user"]
                    self._json({
                        "configured": True, "connected": True,
                        "server": self.remote.server, "user": me, "plugins": PLUGINS,
                        "workflows": workflow.list_workflows(self.remote),
                        **_profiles_meta(),
                    })
                except Exception as error:
                    self._json({"configured": True, "connected": False,
                                "server": self.remote.server, "detail": str(error)[:150],
                                "plugins": PLUGINS, "workflows": [], **_profiles_meta()})
            elif self.path == "/api/sessions":
                self._json(sessions.list_sessions())
            elif self.path.startswith("/api/sessions/"):
                data = sessions.load(self.path.rsplit("/", 1)[1])
                self._json(data or {"error": "not found"}, 200 if data else 404)
            elif self.path.startswith("/api/workflow/archivable"):
                days = self.path.split("days=")[-1] if "days=" in self.path else "3"
                try:
                    self._json(self._need_remote().request(
                        "GET", f"/api/v1/applications-archivable?days_idle={int(days)}"))
                except RemoteError as error:      # 老远端没有归档能力
                    if error.status == 404:
                        self._json({"total": 0, "items": [], "unsupported": True})
                    else:
                        raise
            elif self.path == "/api/scheduler":
                try:
                    self._json(self._need_remote().request(
                        "GET", "/api/v1/scheduler/health"))
                except RemoteError as error:  # 老远端没有这个端点
                    if error.status == 404:
                        self._json({"unsupported": True})
                    else:
                        raise
            elif self.path == "/api/health":
                try:
                    self._json(self._need_remote().request("GET", "/api/v1/health-report"))
                except RemoteError as error:  # 老远端没这个端点：给空体检，页面照常
                    if error.status == 404:
                        self._json({"days": 7, "counts": {}, "items": [], "unsupported": True})
                    else:
                        raise
            elif self.path == "/api/overview":
                self._json(self._need_remote().request("GET", "/api/v1/overview"))
            elif self.path.startswith("/api/workflow/build/"):
                self._json(workflow.build_status(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/inputs/"):
                self._json(workflow.input_schema(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/history/"):
                self._json(workflow.run_history(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/runevents/"):
                self._json(workflow.run_events(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/export/"):
                self._json(workflow.export_snapshot(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/artifacts/"):
                self._json(workflow.run_artifacts(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/artifact/"):
                self._proxy_artifact(self.path[len("/api/workflow/artifact/"):])
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        if not self._key_ok():
            return self._deny()
        try:
            body = self._body()
            if self.path == "/api/config":
                server = str(body.get("server") or "").rstrip("/")
                mode = str(body.get("mode") or "login")
                if mode == "use":  # 免密切换：档案里的令牌还有效就直接用
                    pname = str(body.get("profile") or "")
                    try:
                        prof = use_profile(pname)
                    except KeyError:
                        self._json({"error": f"没有档案「{pname}」"}, 400)
                        return
                    client = RemoteClient(prof.get("server", ""), prof.get("token", ""))
                    try:
                        user = client.request("GET", "/api/v1/me")["user"]
                    except Exception:  # noqa: BLE001 - 统一退回密码登录
                        self._json({"error": "令牌已失效，输入密码重新登录即可"}, 401)
                        return
                    Handler.remote = client
                    self._json({"ok": True, "user": user})
                    return
                anon = RemoteClient(server, "")
                if mode == "register":
                    result = anon.request("POST", "/api/v1/auth/register", {
                        "register_token": str(body.get("register_token") or ""),
                        "name": str(body.get("name") or ""),
                        "password": str(body.get("password") or ""),
                    })
                else:
                    result = anon.request("POST", "/api/v1/auth/login", {
                        "name": str(body.get("name") or ""),
                        "password": str(body.get("password") or ""),
                    })
                token = result["token"]  # 只存会话令牌，密码不落盘
                save_login(server, token, str((result.get("user") or {}).get("name") or ""),
                           str(body.get("profile") or "") or None)
                Handler.remote = RemoteClient(server, token)
                self._json({"ok": True, "user": result["user"]})
            elif self.path == "/api/chat/stream":
                remote = self._need_remote()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    for event in remote.stream("/api/v1/assistant/agent/stream",
                                               {"messages": body.get("messages") or []}):
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                except Exception as error:  # noqa: BLE001 - 错误走流内呈现
                    payload = json.dumps({"type": "error", "text": str(error)[:200]}, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                return
            elif self.path == "/api/chat":
                self._json(assistant.chat(self._need_remote(), body.get("messages") or []))
            elif self.path == "/api/workflow/generate":
                self._json(workflow.generate(
                    self._need_remote(),
                    str(body.get("requirement") or ""),
                    bool(body.get("thinking_enabled", False)),
                    str(body.get("effort") or "low"),
                ))
            elif self.path == "/api/sessions/save":
                sessions.save(str(body["id"]), body.get("messages") or [])
                self._json({"ok": True})
            elif self.path == "/api/workflow/answer":
                self._json(self._need_remote().request(
                    "POST", f"/api/v1/builds/{body['build_id']}/resume",
                    {"message": str(body.get("message") or "")}))
            elif self.path == "/api/workflow/run":
                self._json(workflow.run(self._need_remote(), body["app_id"], body.get("inputs") or {}))
            elif self.path == "/api/workflow/rerun":
                self._json(workflow.rerun(self._need_remote(), str(body.get("run_id") or "")))
            elif self.path == "/api/workflow/archive":
                app_id = str(body.get("app_id") or "")
                archived = bool(body.get("archived", True))
                self._json(self._need_remote().request(
                    "POST",
                    f"/api/v1/applications/{app_id}/archive?archived="
                    f"{'true' if archived else 'false'}"))
            elif self.path == "/api/workflow/import":
                self._json(workflow.import_snapshot(
                    self._need_remote(), body.get("payload") or {},
                    name=str(body.get("name") or "") or None,
                    publish=bool(body.get("publish", True))))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 401 if error.status == 401 else 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def _make_server(host: str, port: int) -> ThreadingHTTPServer:
    """按地址族建服务：ThreadingHTTPServer 默认只认 IPv4，
    而 --host 的白名单里写着 ::1——不选族的话那个值必然崩。"""
    import socket

    if ":" in host:
        class _V6(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        return _V6((host, port), Handler)
    return ThreadingHTTPServer((host, port), Handler)


def _remote_hint(port: int) -> list[str]:
    """在远程机器上跑时，印出本机该敲的转发命令。

    真实摩擦：用户 SSH 到服务器跑 guanjia web，它只印一个 127.0.0.1 的地址，
    然后在自己电脑上怎么也打不开——而答案（端口转发）它一个字没提。
    """
    import socket

    if not os.getenv("SSH_CONNECTION") and not os.getenv("SSH_TTY"):
        return []
    host = socket.gethostname() or "服务器"
    return [
        f"  {'─' * 56}",
        "  看起来你在远程机器上。在自己电脑的终端里跑这句，再打开上面的地址：",
        f"    ssh -L {port}:127.0.0.1:{port} {host}",
        "  （VSCode 用户：端口面板 Add Port 填 " f"{port}" " 也行）",
    ]


def _launch(url: str, app_mode: bool) -> None:
    """零依赖桌面壳：chromium 系 --app 独立窗口，找不到退回默认浏览器。"""
    if app_mode:
        import shutil
        import subprocess
        for exe in ("chromium", "chromium-browser", "google-chrome",
                    "google-chrome-stable", "microsoft-edge", "brave-browser"):
            path = shutil.which(exe)
            if path:
                try:
                    subprocess.Popen([path, f"--app={url}"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except OSError:
                    pass
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 - 无显示环境下静默，服务本身照常
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="guanjia — 本地工作台（远端服务客户端）")
    parser.add_argument("--server", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--port", type=int, default=7800)
    parser.add_argument("--host", default="127.0.0.1",
                        help="绑定地址。默认只有本机能连；填 0.0.0.0 可让局域网访问，"
                             "但会自动要求访问密钥（网页壳本身没有登录）")
    parser.add_argument("--open", action="store_true", help="启动后用默认浏览器打开")
    parser.add_argument("--app", action="store_true", help="启动后以独立窗口打开（chromium 系）")
    args = parser.parse_args()
    cfg = load_config(args.server, args.token)
    if cfg["token"]:
        Handler.remote = RemoteClient(cfg["server"], cfg["token"])
    host = args.host.strip() or "127.0.0.1"
    loopback = host in ("127.0.0.1", "localhost", "::1")

    # 先把服务起起来再印任何东西——此前是"先印地址、再 bind 失败"，
    # 用户看到一个能点的地址后面跟着一段栈，还以为服务在跑
    try:
        server = _make_server(host, args.port)
    except OSError as error:
        print(f"起不来：{host}:{args.port} 绑定失败 —— {error}", file=sys.stderr)
        import errno as _errno

        if getattr(error, "errno", None) == _errno.EADDRINUSE:
            print(f"  换个端口：guanjia web --port {args.port + 1}", file=sys.stderr)
            print("  或先关掉已经在跑的那个 guanjia web", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - gaierror 等地址解析问题
        print(f"起不来：地址 {host} 解析不了 —— {error}", file=sys.stderr)
        sys.exit(1)

    if not loopback:
        import secrets

        Handler.access_key = secrets.token_urlsafe(12)
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    # IPv6 地址在 URL 里要加方括号，否则拼出来的是不可粘贴的 http://::1:7800
    shown = f"[{shown_host}]" if ":" in shown_host else shown_host
    url = f"http://{shown}:{args.port}"
    if Handler.access_key:
        url += f"/?k={Handler.access_key}"

    print(f"guanjia: {url}")
    if not loopback:
        print("  ⚠ 已对外开放：网页壳没有登录，凭这个地址就能用你的平台账号。")
        print("    密钥只在这次启动有效；换成 SSH 端口转发更稳妥。")
    for line in _remote_hint(args.port):
        print(line)
    if args.open or args.app:
        # bind 成功之后再拉浏览器：否则崩了也会把用户送到一个死地址
        timer = threading.Timer(0.6, _launch, args=(url, args.app))
        timer.daemon = True
        timer.start()
    server.serve_forever()





if __name__ == "__main__":
    main()
