"""run --follow：SSE 解析（event:/id: 行）、terminal 收尾、CLI 出口。"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from guanjia import config as gconfig
from guanjia import runcmd
from guanjia.plugins import workflow
from guanjia.remote import RemoteClient

SSE = (
    "id: 1\n"
    "event: workflow.started\n"
    'data: {"application_id":"app-1"}\n'
    "\n"
    ": keep-alive\n"
    "\n"
    "id: 2\n"
    "event: node.completed\n"
    'data: {"node_id":"fetch","title":"取数"}\n'
    "\n"
    "id: 3\n"
    "event: workflow.completed\n"
    'data: {"outputs":{}}\n'
    "\n"
)


class StubApi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/runs/r-new/events":
            body = SSE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/v1/applications":
            self._json(200, [{"id": "app-1", "name": "GPU日报", "active_version": 3}])
        elif self.path == "/api/v1/runs/r-new":
            self._json(200, {"status": "succeeded",
                             "state": {"outputs": {"end": {"report": "OK"}}, "error": None}})
        else:
            self._json(404, {"detail": self.path})

    def do_POST(self):
        if self.path == "/api/v1/applications/app-1/runs":
            self._json(200, {"run_id": "r-new"})
        else:
            self._json(404, {"detail": self.path})

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FollowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gconfig.save_login(f"http://127.0.0.1:{self.port}", "tok", "tester")
        self.remote = RemoteClient(f"http://127.0.0.1:{self.port}", "tok")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_stream_attaches_event_type(self):
        events = list(self.remote.stream("/api/v1/runs/r-new/events"))
        self.assertEqual([e["_event"] for e in events],
                         ["workflow.started", "node.completed", "workflow.completed"])
        self.assertEqual(events[1]["title"], "取数")

    def test_follow_run_stops_at_terminal(self):
        rows = list(workflow.follow_run(self.remote, "r-new"))
        self.assertEqual(rows[-1]["type"], "workflow.completed")
        self.assertEqual(rows[1]["label"], "取数")
        self.assertEqual(len(rows), 3)

    def test_cli_follow(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runcmd.main(["GPU", "--follow"])
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("workflow.completed", text)
        self.assertIn("report = OK", text)
        self.assertIn("✓ succeeded", text)  # 收尾以 run 的真实状态为准，不用事件词汇


if __name__ == "__main__":
    unittest.main()
