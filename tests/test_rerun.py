"""rerun：原输入透传、前缀解析、CLI 出口（真 HTTP 桩）。"""

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


class StubApi(BaseHTTPRequestHandler):
    posted_inputs: list[dict] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/applications":
            self._json(200, [{"id": "app-1", "name": "GPU日报", "active_version": 3}])
        elif self.path.startswith("/api/v1/applications/app-1/runs"):
            self._json(200, [{"id": "rfail0001aaaa", "status": "failed"},
                             {"id": "rok0002bbbb", "status": "succeeded"}])
        elif self.path == "/api/v1/applications/app-1":
            self._json(200, {"id": "app-1", "name": "改名后的工作流", "active_version": 3})
        elif self.path == "/api/v1/runs/rfail0001aaaa":
            self._json(200, {"id": "rfail0001aaaa", "application_id": "app-1",
                             "state": {"inputs": {"month": "2026-08"}}})
        elif self.path == "/api/v1/runs/r-new":
            self._json(200, {"status": "succeeded",
                             "state": {"outputs": {"end": {"report": "好了"}}, "error": None}})
        else:
            self._json(404, {"detail": self.path})

    def do_POST(self):
        if self.path == "/api/v1/applications/app-1/runs":
            length = int(self.headers.get("Content-Length") or 0)
            StubApi.posted_inputs.append(json.loads(self.rfile.read(length)).get("inputs"))
            self._json(200, {"run_id": "r-new"})
        else:
            self._json(404, {"detail": self.path})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RerunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)
        StubApi.posted_inputs = []
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

    def test_rerun_passes_original_inputs(self):
        result = workflow.rerun(self.remote, "rfail0001aaaa")
        self.assertEqual(StubApi.posted_inputs, [{"month": "2026-08"}])
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["inputs"], {"month": "2026-08"})

    def test_find_run_prefix(self):
        self.assertEqual(workflow.find_run(self.remote, "rfail"), "rfail0001aaaa")
        self.assertIsNone(workflow.find_run(self.remote, "r"))       # 歧义
        self.assertIsNone(workflow.find_run(self.remote, "zzz"))     # 无命中

    def test_cli_rerun_by_prefix(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runcmd.rerun_main(["rfail", "--json"])
        self.assertEqual(code, 0, err.getvalue())
        data = json.loads(out.getvalue())
        self.assertEqual(data["run_id"], "r-new")
        self.assertEqual(data["inputs"], {"month": "2026-08"})

    def test_cli_ambiguous_prefix(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = runcmd.rerun_main(["r"])
        self.assertEqual(code, 2)
        self.assertIn("没找到唯一", err.getvalue())

    def test_rerun_reports_workflow_name(self):
        """重跑要说清跑的是哪个工作流，名字取应用行当前名（非发布快照旧名）。"""
        result = workflow.rerun(self.remote, "rfail0001aaaa")
        self.assertEqual(result["workflow"], "改名后的工作流")

    def test_cli_rerun_prints_name(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runcmd.rerun_main(["rfail"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("改名后的工作流", out.getvalue())


if __name__ == "__main__":
    unittest.main()
