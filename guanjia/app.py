"""guanjia 本地壳：localhost 单页界面，一切能力经插件转发远端。

用法：guanjia web [--port 7800]
首次打开进入连接页：填远端地址 + 个人令牌（管理员在平台上用
POST /api/v1/users 为每人签发），保存于 ~/.bench.json。
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from importlib import resources

from .config import load_config
from .plugins import PLUGINS, assistant, workflow
from .remote import RemoteClient, RemoteError


class Handler(BaseHTTPRequestHandler):
    remote: RemoteClient | None = None

    def log_message(self, *args) -> None:
        pass

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
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            if self.path == "/":
                self._asset("index.html", "text/html; charset=utf-8")
            elif self.path == "/static/style.css":
                self._asset("style.css", "text/css; charset=utf-8")
            elif self.path == "/static/app.js":
                self._asset("app.js", "text/javascript; charset=utf-8")
            elif self.path == "/api/bootstrap":
                if self.remote is None or not self.remote.token:
                    self._json({"configured": False, "plugins": PLUGINS})
                    return
                try:
                    me = self.remote.request("GET", "/api/v1/me")["user"]
                    self._json({
                        "configured": True, "connected": True,
                        "server": self.remote.server, "user": me, "plugins": PLUGINS,
                        "workflows": workflow.list_workflows(self.remote),
                    })
                except Exception as error:
                    self._json({"configured": True, "connected": False,
                                "server": self.remote.server, "detail": str(error)[:150],
                                "plugins": PLUGINS, "workflows": []})
            elif self.path == "/api/overview":
                self._json(self._need_remote().request("GET", "/api/v1/overview"))
            elif self.path.startswith("/api/workflow/build/"):
                self._json(workflow.build_status(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/inputs/"):
                self._json(workflow.input_schema(self._need_remote(), self.path.rsplit("/", 1)[1]))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/api/config":
                server = str(body.get("server") or "").rstrip("/")
                mode = str(body.get("mode") or "login")
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
                (Path.home() / ".guanjia.json").write_text(
                    json.dumps({"server": server, "token": token}, ensure_ascii=False), encoding="utf-8"
                )
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
            elif self.path == "/api/workflow/answer":
                self._json(self._need_remote().request(
                    "POST", f"/api/v1/builds/{body['build_id']}/resume",
                    {"message": str(body.get("message") or "")}))
            elif self.path == "/api/workflow/run":
                self._json(workflow.run(self._need_remote(), body["app_id"], body.get("inputs") or {}))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 401 if error.status == 401 else 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="guanjia — 本地工作台（远端服务客户端）")
    parser.add_argument("--server", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--port", type=int, default=7800)
    args = parser.parse_args()
    cfg = load_config(args.server, args.token)
    if cfg["token"]:
        Handler.remote = RemoteClient(cfg["server"], cfg["token"])
    print(f"guanjia: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()





if __name__ == "__main__":
    main()
