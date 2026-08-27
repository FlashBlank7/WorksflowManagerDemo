"""completion：脚本内容、隐藏子命令、坏 shell 参数。"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from guanjia import completion
from guanjia import config as gconfig


class StubApi(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps([
            {"id": "app-1", "name": "GPU日报", "active_version": 3},
            {"id": "app-2", "name": "草稿", "active_version": None},
        ]).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CompletionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)

    def tearDown(self):
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def _capture(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = fn(*args)
        return result, out.getvalue()

    def test_bash_script(self):
        code, out = self._capture(completion.main, ["bash"])
        self.assertEqual(code, 0)
        self.assertIn("complete -F _guanjia_complete guanjia", out)
        for word in ("web", "today", "remote", "doctor", "run"):
            self.assertIn(word, out)

    def test_zsh_wraps_bashcompinit(self):
        code, out = self._capture(completion.main, ["zsh"])
        self.assertEqual(code, 0)
        self.assertIn("bashcompinit", out)
        self.assertIn("complete -F _guanjia_complete", out)

    def test_bad_shell(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(completion.main(["fish"]), 2)

    def test_profile_names(self):
        gconfig.save_login("http://a:1", "t", "", "one")
        gconfig.save_login("http://b:2", "t", "", "two")
        _, out = self._capture(completion.print_profile_names)
        self.assertEqual(sorted(out.split()), ["one", "two"])

    def test_wf_names_published_only(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            gconfig.save_login(f"http://127.0.0.1:{server.server_address[1]}", "tok", "")
            _, out = self._capture(completion.print_workflow_names)
            self.assertEqual(out.split(), ["GPU日报"])  # 未发布的「草稿」不出现
        finally:
            server.shutdown()
            server.server_close()

    def test_wf_names_silent_without_login(self):
        _, out = self._capture(completion.print_workflow_names)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
