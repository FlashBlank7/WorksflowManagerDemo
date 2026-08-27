"""export：快照载荷、CLI 落盘与 stdout。"""

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


class StubApi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/applications":
            self._json(200, [{"id": "app-1", "name": "GPU日报", "active_version": 3}])
        elif self.path == "/api/v1/applications/app-1/draft":
            self._json(200, {"revision": 54, "snapshot": {
                "name": "GPU日报", "requirement": "每天8点",
                "workflow": {"nodes": [{"id": "a"}, {"id": "b"}]},
                "agents": {}, "tests": []}})
        else:
            self._json(404, {"detail": self.path})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = self.tmp.name
        os.chdir(self.tmp.name)
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gconfig.save_login(f"http://127.0.0.1:{self.server.server_address[1]}", "tok", "t")

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.server.shutdown()
        self.server.server_close()
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_export_writes_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runcmd.export_main(["GPU"])
        self.assertEqual(code, 0, out.getvalue())
        path = os.path.join(self.tmp.name, "GPU日报.guanjia.json")
        self.assertTrue(os.path.isfile(path))
        data = json.loads(open(path, encoding="utf-8").read())
        self.assertEqual(data["guanjia_export"], 1)
        self.assertEqual(data["revision"], 54)
        self.assertEqual(len(data["snapshot"]["workflow"]["nodes"]), 2)
        self.assertIn("2 节点", out.getvalue())

    def test_export_stdout(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = runcmd.export_main(["GPU日报", "-o", "-"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["snapshot"]["name"], "GPU日报")

    def test_export_not_found(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = runcmd.export_main(["不存在"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
