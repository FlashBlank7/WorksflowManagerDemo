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
                self._json(401, {"detail": "令牌不对或已失效——重新登录一次"})
        # 这两个端点原来桩里没有，于是 test_all_green 那条**在两个部件
        # 没查成的情况下断言「一切正常」**——正是 doctor 自己反复警告的事。
        # 现在 doctor 会如实说"没验"，所以桩得把它们答上，
        # 「全绿」才真的是全绿。没查成的局面单开一条测（见下面那个类）。
        elif self.path == "/api/v1/scheduler/health":
            self._json(200, {"alive": True, "seconds_since_tick": 3, "last_error": ""})
        elif self.path == "/api/v1/health-report":
            self._json(200, {"days": 7, "counts": {"ok": 2},
                             "items": [], "never_ran": []})
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


class HalfCheckedApi(StubApi):
    """能连上、能登录，但体检和调度器两个端点答不了。"""

    def do_GET(self):
        if self.path in ("/api/v1/scheduler/health", "/api/v1/health-report"):
            self._json(500, {"detail": "boom"})
        else:
            StubApi.do_GET(self)


class DoctorDoesNotClaimWhatItDidNotCheck(unittest.TestCase):
    """**没查成 ≠ 查过没事。**

    原来体检那一段是光秃秃一个 `except: pass`：端点一答不了
    （网络抖一下、后端 500、没登录），整段无声跳过，
    最后照样打「一切正常」。而 doctor 自己的注释写着：
    "诊断工具最不该做的事，就是在没查过某个部件的情况下宣布全好"。
    调度器那一段一直是对的，就这一段漏了。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE",
                    "BENCH_SERVER", "BENCH_TOKEN"):
            os.environ.pop(key, None)
        self.old_dir = sessions.DIR
        sessions.DIR = Path(self.tmp.name) / "sessions"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), HalfCheckedApi)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gconfig.save_login(f"http://127.0.0.1:{self.port}", "good", "tester")

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

    def test_it_does_not_say_everything_is_fine(self):
        _, out = self._run()
        self.assertNotIn("一切正常", out)

    def test_it_names_what_it_could_not_check(self):
        """结论那一行要把**每一项**都点名。

        第一版只断言这几个词出现在整段输出里——而"工作流健康：没验（…）"
        那一行本来就会印，于是即使漏记一项、结论里只剩另一项，
        这条照样绿（变异验证抓到的）。断言要落在结论那一行上。
        """
        _, out = self._run()
        line = next(l for l in out.splitlines() if "没查成" in l)
        self.assertIn("工作流健康", line, line)
        self.assertIn("调度器", line, line)

    def test_it_says_why_it_could_not(self):
        """只说"没验"还不够——是没登录、是旧版本、还是后端出错，
        三种局面下一步完全不同。"""
        _, out = self._run()
        self.assertIn("500", out)

    def test_it_is_not_an_error(self):
        """老远端确实没有这些接口，那不是用户的错——退出码仍是 0。"""
        code, _ = self._run()
        self.assertEqual(code, 0)
