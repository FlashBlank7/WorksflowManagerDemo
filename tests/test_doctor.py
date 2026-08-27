"""doctor 自诊断：真 HTTP 桩验证三种典型局面。"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from guanjia import doctor, sessions
from guanjia import config as gconfig


class StubApi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True})
        elif self.path == "/api/v1/me":
            if self.headers.get("Authorization") == "Bearer good":
                self._json(200, {"user": {"name": "tester", "role": "admin"}})
            else:
                self._json(401, {"detail": "invalid API token"})
        else:
            self._json(404, {"detail": "nope"})

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE",
                    "BENCH_SERVER", "BENCH_TOKEN"):
            os.environ.pop(key, None)
        self.old_dir = sessions.DIR
        sessions.DIR = Path(self.tmp.name) / "sessions"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        sessions.DIR = self.old_dir
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def _run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.run()
        return code, out.getvalue()

    def test_all_green(self):
        gconfig.save_login(f"http://127.0.0.1:{self.port}", "good", "tester")
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("tester", out)
        self.assertIn("一切正常", out)

    def test_stale_token(self):
        gconfig.save_login(f"http://127.0.0.1:{self.port}", "stale", "tester")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("令牌已失效", out)
        self.assertIn("guanjia --login", out)

    def test_unreachable(self):
        # 占一个端口再关掉 → connection refused
        dead = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        dead_port = dead.server_address[1]
        dead.server_close()
        gconfig.save_login(f"http://127.0.0.1:{dead_port}", "good", "tester")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("连不上", out)


if __name__ == "__main__":
    unittest.main()
