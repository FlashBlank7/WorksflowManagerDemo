"""本地壳的 HTTP 路由：网页端所有功能的必经之路。

此前 25 条路由零测试——今天修的一堆缺陷（错误字段、类型转换、老远端降级）
全都从这里过。这里起一个真的本地壳，打一个真的桩远端，逐条走。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from guanjia import app as shell
from guanjia import config as gconfig
from guanjia import sessions
from guanjia.remote import RemoteClient

APP = {"id": "app-1", "name": "文本统计", "active_version": 2,
       "description": "数行数", "display_description": "数行数"}


class StubRemote(BaseHTTPRequestHandler):
    """桩远端：只回答本地壳会问的那些端点。"""

    fail_paths: set = set()          # 这些路径返回 404，用来测老远端降级
    seen: list = []
    stream_broken: bool = False      # 让流式端点直接 500，测本地壳的错误呈现
    stream_chunks: list = [
        'event: delta\ndata: {"type":"delta","text":"正在"}\n\n',
        ': keep-alive\n\n',
        'event: delta\ndata: {"type":"delta","text":"查询…"}\n\n',
        'event: action\ndata: {"type":"action","tool":"list_workflows",'
        '"summary":"1 个工作流"}\n\n',
        'event: final\ndata: {"type":"final","text":"共 1 个工作流。"}\n\n',
    ]

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        StubRemote.seen.append(("GET", self.path))
        path = urllib.parse.unquote(self.path.split("?")[0])
        if path in StubRemote.fail_paths:
            return self._json(404, {"detail": "not found"})
        table = {
            "/api/v1/me": {"user": {"name": "u", "role": "admin"}},
            "/api/v1/applications": [APP],
            "/api/v1/applications/app-1/draft": {
                "revision": 3,
                "snapshot": {"name": "文本统计", "requirement": "数行数",
                             "workflow": {"nodes": [
                                 {"id": "s", "type": "start", "config": {"inputs": [
                                     {"name": "text", "label": "文本", "type": "string",
                                      "example": "第一行\n第二行"}]}}]},
                             "agents": {}, "tests": []}},
            "/api/v1/applications/app-1/runs": [
                {"id": "run-ok", "status": "succeeded", "created_at": "2026-08-28T01:00:00",
                 "outputs": {"line_count": 2}, "state": {"inputs": {"text": "a\nb"}}},
                {"id": "run-bad", "status": "failed", "created_at": "2026-08-28T00:00:00",
                 "error": "node calc failed: 除以零", "outputs": {},
                 "state": {"inputs": {"text": "x"}}}],
            "/api/v1/runs/run-ok": {
                "id": "run-ok", "status": "succeeded", "outputs": {"line_count": 2},
                "state": {"inputs": {"text": "a\nb"}}, "application_id": "app-1"},
            "/api/v1/runs/run-new": {
                "id": "run-new", "status": "succeeded", "outputs": {"line_count": 9},
                "state": {}, "application_id": "app-1"},
            "/api/v1/runs/run-ok/events/list": {
                "run_id": "run-ok", "total": 2, "truncated": False,
                "events": [{"id": 1, "type": "workflow.started", "at": "2026-08-28T01:00:00",
                            "data": {}},
                           {"id": 2, "type": "workflow.completed", "at": "2026-08-28T01:00:05",
                            "data": {}}]},
            "/api/v1/runs/run-ok/artifacts": [{"name": "报表.csv", "size": 2048}],
            "/api/v1/overview": {"date_utc": "2026-08-28",
                                 "runs_today": {"total": 3, "succeeded": 2, "failed": 1,
                                                "running": 0},
                                 "builds_active": 0, "schedules": [], "recent_failures": [],
                                 "published_workflows": 1, "week": []},
            "/api/v1/health-report": {"days": 7, "counts": {"broken": 0, "stale": 0, "ok": 1},
                                      "items": []},
            "/api/v1/scheduler/health": {"running": True, "alive": True, "tick_count": 5,
                                         "seconds_since_tick": 3.0},
            "/api/v1/builds/b-1": {"status": "published", "team_state": {
                "revision": 4, "published_version": 1, "pending_question": None},
                "error": ""},
            "/api/v1/builds/b-1/transcript": {"records": []},
            "/api/v1/applications/app-1": APP,
            "/api/v1/applications/app-2/draft": {"revision": 0, "snapshot": {}},
        }
        if path == "/api/v1/runs/run-ok/artifacts/报表.csv":
            body = "名称,数量\n甲,1\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path in table:
            return self._json(200, table[path])
        self._json(404, {"detail": path})

    def do_POST(self):
        StubRemote.seen.append(("POST", self.path))
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/applications/app-1/runs":
            return self._json(200, {"run_id": "run-new", "inputs": body.get("inputs")})
        if self.path == "/api/v1/applications":
            return self._json(201, {"id": "app-2", "name": body.get("name")})
        if self.path == "/api/v1/applications/app-2/draft":
            return self._json(200, {"revision": int(body.get("expected_revision", 0)) + 1})
        if self.path == "/api/v1/applications/app-2/versions":
            return self._json(200, {"version": 1})
        if self.path == "/api/v1/applications/app-2/builds":
            return self._json(202, {"build_id": "b-1"})
        if self.path == "/api/v1/builds/b-1/resume":
            return self._json(200, {"status": "queued"})
        if self.path == "/api/v1/assistant/agent":
            return self._json(200, {"text": "好的", "actions": []})
        if self.path == "/api/v1/assistant/agent/stream":
            if StubRemote.stream_broken:
                return self._json(500, {"detail": "上游炸了"})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in StubRemote.stream_chunks:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
            return
        self._json(404, {"detail": self.path})


class WebRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)
        cls.old_dir = sessions.DIR
        sessions.DIR = os.path.join(cls.tmp.name, "sess")
        from pathlib import Path
        sessions.DIR = Path(cls.tmp.name) / "sess"

        cls.remote_server = ThreadingHTTPServer(("127.0.0.1", 0), StubRemote)
        cls.remote_port = cls.remote_server.server_address[1]
        threading.Thread(target=cls.remote_server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.remote_port}"
        gconfig.save_login(base, "tok", "u")

        shell.Handler.remote = RemoteClient(base, "tok")
        cls.shell_server = ThreadingHTTPServer(("127.0.0.1", 0), shell.Handler)
        cls.port = cls.shell_server.server_address[1]
        threading.Thread(target=cls.shell_server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.shell_server.shutdown()
        cls.shell_server.server_close()
        cls.remote_server.shutdown()
        cls.remote_server.server_close()
        sessions.DIR = cls.old_dir
        if cls.old_home is not None:
            os.environ["HOME"] = cls.old_home
        cls.tmp.cleanup()

    def get(self, path):
        # 请求行只能是 ascii：中文路径要按浏览器的做法先转义
        safe = urllib.parse.quote(path, safe="/?=&")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{safe}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def post(self, path, body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def json_get(self, path):
        status, raw, _ = self.get(path)
        return status, json.loads(raw)

    # ── 静态资源与首页 ──
    def test_index_and_assets(self):
        status, body, _ = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"lg-prof", body)          # 登录页档案下拉
        for path, needle in (("/static/app.js", b"loadHealth"),
                             ("/static/style.css", b".hl-row")):
            status, body, _ = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(needle, body)

    # ── bootstrap ──
    def test_bootstrap_reports_connected_user_and_profiles(self):
        status, data = self.json_get("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(data["connected"])
        self.assertEqual(data["user"]["name"], "u")
        self.assertEqual(len(data["workflows"]), 1)
        self.assertIn("profiles", data)
        for profile in data["profiles"]:
            self.assertNotIn("token", profile)   # 令牌绝不能给前端

    # ── 工作流相关 ──
    def test_inputs_history_events_artifacts(self):
        status, schema = self.json_get("/api/workflow/inputs/app-1")
        self.assertEqual(status, 200)
        self.assertEqual(schema[0]["name"], "text")
        self.assertIn("\n", schema[0]["example"])    # 多行示例原样传到前端

        status, history = self.json_get("/api/workflow/history/app-1")
        self.assertEqual(status, 200)
        failed = [item for item in history if item["status"] == "failed"][0]
        self.assertIn("除以零", failed["error"])     # 失败原因取顶层 error

        status, rows = self.json_get("/api/workflow/runevents/run-ok")
        self.assertEqual([row["type"] for row in rows],
                         ["workflow.started", "workflow.completed"])

        status, arts = self.json_get("/api/workflow/artifacts/run-ok")
        self.assertEqual(arts[0]["name"], "报表.csv")

    def test_artifact_download_is_binary_passthrough(self):
        status, body, headers = self.get("/api/workflow/artifact/run-ok/报表.csv")
        self.assertEqual(status, 200)
        self.assertIn("名称".encode("utf-8"), body)
        self.assertEqual(headers.get("Content-Type"), "text/csv")

    def test_run_and_rerun(self):
        status, result = self.post("/api/workflow/run",
                                   {"app_id": "app-1", "inputs": {"text": "a\nb"}})
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["outputs"], {"line_count": 9})   # 顶层 outputs

        status, again = self.post("/api/workflow/rerun", {"run_id": "run-ok"})
        self.assertEqual(status, 200)
        self.assertEqual(again["workflow"], "文本统计")           # 带回当前名

    def test_export_and_import(self):
        status, payload = self.json_get("/api/workflow/export/app-1")
        self.assertEqual(payload["guanjia_export"], 1)
        self.assertEqual(payload["revision"], 3)

        status, result = self.post("/api/workflow/import",
                                   {"payload": payload, "name": "副本", "publish": False})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["name"], "副本")
        self.assertEqual(result["app_id"], "app-2")

    def test_generate_and_build_status(self):
        status, result = self.post("/api/workflow/generate",
                                   {"requirement": "做一个统计文本行数的工作流"})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["build_id"], "b-1")
        status, build = self.json_get(f"/api/workflow/build/{result['build_id']}")
        self.assertEqual(build["status"], "published")
        self.assertEqual(build["published_version"], 1)

    # ── 统筹与平台状态 ──
    def test_overview_health_scheduler(self):
        status, data = self.json_get("/api/overview")
        self.assertEqual(data["runs_today"]["total"], 3)
        status, health = self.json_get("/api/health")
        self.assertEqual(health["counts"]["ok"], 1)
        status, sched = self.json_get("/api/scheduler")
        self.assertTrue(sched["alive"])

    def test_old_remote_degrades_instead_of_erroring(self):
        """老远端没有体检/调度器端点时，页面要照常而不是报错。"""
        StubRemote.fail_paths = {"/api/v1/health-report", "/api/v1/scheduler/health"}
        try:
            status, health = self.json_get("/api/health")
            self.assertEqual(status, 200)
            self.assertTrue(health.get("unsupported"))
            self.assertEqual(health["items"], [])
            status, sched = self.json_get("/api/scheduler")
            self.assertEqual(status, 200)
            self.assertTrue(sched.get("unsupported"))
        finally:
            StubRemote.fail_paths = set()

    # ── 会话 ──
    def test_sessions_roundtrip(self):
        status, result = self.post("/api/sessions/save",
                                   {"id": "s1", "messages": [
                                       {"role": "user", "text": "你好"},
                                       {"kind": "answerbox", "build_id": "b-1"}]})
        self.assertEqual(status, 200, result)
        status, listed = self.json_get("/api/sessions")
        self.assertEqual([item["id"] for item in listed], ["s1"])
        status, one = self.json_get("/api/sessions/s1")
        self.assertEqual(len(one["messages"]), 1)      # answerbox 不落盘

    # ── 对话流式：招牌路径 ──
    def _stream(self, messages):
        """像浏览器那样逐事件读回来。"""
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/chat/stream", method="POST",
            data=json.dumps({"messages": messages}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        events = []
        with urllib.request.urlopen(request, timeout=30) as response:
            self.assertEqual(response.headers.get("Content-Type"), "text/event-stream")
            for raw in response:
                line = raw.decode("utf-8").strip()
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    def test_chat_stream_passes_events_through(self):
        events = self._stream([{"role": "user", "text": "有哪些工作流"}])
        self.assertEqual([e["type"] for e in events],
                         ["delta", "delta", "action", "final"])
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "delta"),
                         "正在查询…")
        self.assertEqual(events[2]["tool"], "list_workflows")
        self.assertEqual(events[3]["text"], "共 1 个工作流。")

    def test_chat_stream_reports_upstream_error_inside_the_stream(self):
        """上游炸了也要走流内呈现——不能让浏览器那头卡住或拿到半截 HTTP 错误。"""
        StubRemote.stream_broken = True
        try:
            events = self._stream([{"role": "user", "text": "随便"}])
        finally:
            StubRemote.stream_broken = False
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("500", events[0]["text"])

    def test_chat_stream_survives_keepalive_and_unicode(self):
        """keep-alive 注释行要被跳过；中文不能被转义成 \\uXXXX 丢给前端。"""
        original = StubRemote.stream_chunks
        StubRemote.stream_chunks = [
            ': keep-alive\n\n',
            'event: final\ndata: {"type":"final","text":"门店合计：甲店 1200 元"}\n\n',
        ]
        try:
            events = self._stream([{"role": "user", "text": "对账"}])
        finally:
            StubRemote.stream_chunks = original
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["text"], "门店合计：甲店 1200 元")

    def test_chat_fallback_uses_agent_endpoint(self):
        """流式失败时的回退也要走带工具的智能体端点（此前打的是无工具的旧端点）。"""
        before = len(StubRemote.seen)
        status, data = self.post("/api/chat", {"messages": [{"role": "user", "text": "hi"}]})
        self.assertEqual(status, 200)
        self.assertEqual(data["text"], "好的")
        called = [path for method, path in StubRemote.seen[before:] if method == "POST"]
        self.assertIn("/api/v1/assistant/agent", called)
        self.assertNotIn("/api/v1/assistant/chat", called)

    # ── 未知路由 ──
    def test_unknown_route_is_404(self):
        status, data = self.json_get("/api/什么都不是")
        self.assertEqual(status, 404)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()


class AccessKeyTest(unittest.TestCase):
    """非回环绑定时的访问密钥。

    网页壳本身没有登录——绑到 0.0.0.0 等于把平台账号给同网段所有人。
    所以非回环绑定强制要一把随机钥匙；回环仍然零摩擦。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_home = os.environ.get("HOME")
        os.environ["HOME"] = cls.tmp.name
        cls.old_key = shell.Handler.access_key
        shell.Handler.access_key = "secret-key-123"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), shell.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shell.Handler.access_key = cls.old_key
        if cls.old_home is not None:
            os.environ["HOME"] = cls.old_home
        cls.tmp.cleanup()

    def _raw(self, path, headers=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_no_key_is_rejected(self):
        status, body, _ = self._raw("/")
        self.assertEqual(status, 401)
        self.assertIn("访问密钥".encode("utf-8"), body)

    def test_wrong_key_is_rejected(self):
        status, _, _ = self._raw("/?k=wrong-guess")
        self.assertEqual(status, 401)

    def test_api_routes_are_protected_too(self):
        """不能只挡首页——API 才是能动账号的地方。"""
        status, _, _ = self._raw("/api/bootstrap")
        self.assertEqual(status, 401)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/chat", method="POST",
            data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertEqual(status, 401)

    def test_right_key_opens_index_and_sets_cookie(self):
        status, body, headers = self._raw("/?k=secret-key-123")
        self.assertEqual(status, 200)
        self.assertIn(b"lg-prof", body)                 # 首页真的出来了
        self.assertIn("guanjia_key=secret-key-123", headers.get("Set-Cookie", ""))

    def test_non_ascii_key_is_rejected_not_reset(self):
        """compare_digest 对非 ASCII 字符串抛 TypeError——它在鉴权路径上，
        抛出去就是连接被重置（curl 52），而不是干净的 401。"""
        status, _, _ = self._raw("/?k=%E4%B8%AD%E6%96%87")
        self.assertEqual(status, 401)

    def test_non_ascii_cookie_is_rejected_not_reset(self):
        """urllib 自己不肯发非 ASCII 头，所以裸 socket 发——要测的是服务端会不会断连。"""
        import socket

        raw = ('GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n'
               'Cookie: guanjia_key="\u4e2d\u6587"\r\nConnection: close\r\n\r\n')
        with socket.create_connection(("127.0.0.1", self.port), timeout=20) as sock:
            sock.sendall(raw.encode("utf-8"))
            head = sock.recv(64).decode("latin-1")
        self.assertIn("401", head.splitlines()[0])   # 不是连接被重置

    def test_cookie_works_for_later_requests(self):
        status, body, _ = self._raw(
            "/static/app.js", headers={"Cookie": "guanjia_key=secret-key-123"})
        self.assertEqual(status, 200)
        self.assertIn(b"loadHealth", body)

    def test_loopback_default_has_no_key(self):
        """默认（回环）不该有任何摩擦。"""
        self.assertEqual(shell.Handler.__dict__.get("access_key", ""), "secret-key-123")
        # 类属性被本用例改过；默认值应为空串
        import inspect
        source = inspect.getsource(shell.Handler)
        self.assertIn('access_key: str = ""', source)


class RemoteHintTest(unittest.TestCase):
    """远程机器上要告诉人家怎么连——用户真被这个坑过。"""

    def test_hint_only_on_ssh(self):
        old = {k: os.environ.get(k) for k in ("SSH_CONNECTION", "SSH_TTY")}
        try:
            for key in old:
                os.environ.pop(key, None)
            self.assertEqual(shell._remote_hint(7800), [])
            os.environ["SSH_CONNECTION"] = "1.2.3.4 5 6.7.8.9 22"
            lines = shell._remote_hint(7800)
            self.assertTrue(any("ssh -L 7800:127.0.0.1:7800" in line for line in lines))
            self.assertTrue(any("Add Port" in line for line in lines))
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class WebStartupTest(unittest.TestCase):
    """启动路径：先能服务再印地址，别让人看着一个能点的链接后面跟着栈。"""

    def test_ipv6_needs_its_own_address_family(self):
        """ThreadingHTTPServer 默认只认 IPv4，而 --host 白名单里写着 ::1。"""
        import socket

        server = shell._make_server("::1", 0)
        try:
            self.assertEqual(server.address_family, socket.AF_INET6)
        finally:
            server.server_close()
        server = shell._make_server("127.0.0.1", 0)
        try:
            self.assertEqual(server.address_family, socket.AF_INET)
        finally:
            server.server_close()

    def test_bind_failure_raises_before_anything_is_printed(self):
        """端口被占时 _make_server 抛 OSError，调用方据此在印地址前退出。"""
        taken = shell._make_server("127.0.0.1", 0)
        try:
            port = taken.server_address[1]
            with self.assertRaises(OSError):
                shell._make_server("127.0.0.1", port)
        finally:
            taken.server_close()
