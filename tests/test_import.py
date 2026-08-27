"""import：op 序列、mandatory 测试跳过、发布被拒留草稿、CLI 出口。"""

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

SNAP = {
    "name": "GPU日报", "description": "d", "requirement": "每天8点",
    "workflow": {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"id": "e1"}]},
    "agents": {"g1": {"id": "g1"}},
    "tests": [{"id": "t1", "mandatory": True}],
}


class StubApi(BaseHTTPRequestHandler):
    ops: list = []
    publish_calls: int = 0
    reject_publish = False

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/applications/app-new/draft":
            self._json(200, {"revision": 0, "snapshot": {}})
        else:
            self._json(404, {"detail": self.path})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/applications":
            self._json(201, {"id": "app-new", "name": body["name"]})
        elif self.path == "/api/v1/applications/app-new/draft":
            StubApi.ops.append((body["op"], body["expected_revision"]))
            self._json(200, {"revision": len(StubApi.ops)})
        elif self.path == "/api/v1/applications/app-new/versions":
            StubApi.publish_calls += 1
            if StubApi.reject_publish:
                self._json(409, {"detail": {"message": "publish gate: 需验收证据"}})
            else:
                self._json(200, {"version": 1})
        else:
            self._json(404, {"detail": self.path})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)
        StubApi.ops = []
        StubApi.publish_calls = 0
        StubApi.reject_publish = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gconfig.save_login(f"http://127.0.0.1:{self.server.server_address[1]}", "tok", "t")
        self.remote = RemoteClient(f"http://127.0.0.1:{self.server.server_address[1]}", "tok")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_full_import_sequence(self):
        result = workflow.import_snapshot(self.remote, {"guanjia_export": 1, "snapshot": SNAP})
        self.assertEqual([o[0] for o in StubApi.ops],
                         ["set_metadata", "upsert_agent", "replace_workflow", "replace_tests"])
        self.assertEqual([o[1] for o in StubApi.ops], [0, 1, 2, 3])  # revision 跟踪
        self.assertTrue(result["published"])
        self.assertEqual(result["app_id"], "app-new")

    def test_tests_without_mandatory_skipped(self):
        snap = dict(SNAP, tests=[{"id": "t1", "mandatory": False}])
        result = workflow.import_snapshot(self.remote, snap)  # 裸快照也接受
        self.assertNotIn("replace_tests", [o[0] for o in StubApi.ops])
        self.assertTrue(result["skipped_tests"])

    def test_publish_rejected_keeps_draft(self):
        StubApi.reject_publish = True
        result = workflow.import_snapshot(self.remote, {"snapshot": SNAP})
        self.assertFalse(result["published"])
        self.assertIn("409", result["publish_error"])

    def test_bad_payload(self):
        with self.assertRaises(ValueError):
            workflow.import_snapshot(self.remote, {"snapshot": {"name": "x"}})

    def test_cli_import_file(self):
        path = os.path.join(self.tmp.name, "x.guanjia.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"guanjia_export": 1, "snapshot": SNAP}, f, ensure_ascii=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runcmd.import_main([path, "--name", "副本"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("已发布", out.getvalue())
        self.assertIn("副本", out.getvalue())

    def test_cli_no_publish(self):
        path = os.path.join(self.tmp.name, "x.guanjia.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"snapshot": SNAP}, f)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = runcmd.import_main([path, "--no-publish"])
        self.assertEqual(code, 0)
        self.assertEqual(StubApi.publish_calls, 0)


if __name__ == "__main__":
    unittest.main()
