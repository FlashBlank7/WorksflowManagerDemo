"""guanjia run：名字解析、参数、结局与退出码（真 HTTP 桩）。"""

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
    fail_run = False

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/v1/applications":
            self._json(200, [
                {"id": "app-1", "name": "GPU日报", "active_version": 3},
                {"id": "app-2", "name": "对账草稿", "active_version": None},
            ])
        elif self.path == "/api/v1/runs/r1":
            if StubApi.fail_run:
                self._json(200, {"status": "failed",
                                 "state": {"outputs": {}, "error": "上游超时"}})
            else:
                self._json(200, {"status": "succeeded",
                                 "state": {"outputs": {"end": {"report": "卡0 94%"}},
                                           "error": None}})
        else:
            self._json(404, {"detail": "nope"})

    def do_POST(self):
        if self.path == "/api/v1/applications/app-1/runs":
            self._json(200, {"run_id": "r1"})
        else:
            self._json(404, {"detail": "nope"})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RunCmdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE",
                    "BENCH_SERVER", "BENCH_TOKEN"):
            os.environ.pop(key, None)
        StubApi.fail_run = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
        port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        gconfig.save_login(f"http://127.0.0.1:{port}", "tok", "tester")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runcmd.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_substring_match_success(self):
        code, out, _ = self._run(["GPU"])
        self.assertEqual(code, 0, out)
        # 2026-08-29 起人看的那行印中文状态（状态码只留给 --json）
        self.assertIn("跑成了", out)
        self.assertNotIn("succeeded", out)
        self.assertIn("卡0 94%", out)  # 嵌套 outputs 拍平

    def test_json_output(self):
        code, out, _ = self._run(["GPU日报", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["workflow"], "GPU日报")
        self.assertEqual(data["outputs"]["report"], "卡0 94%")

    def test_failed_run_exit_1(self):
        StubApi.fail_run = True
        code, out, _ = self._run(["GPU"])
        self.assertEqual(code, 1)
        self.assertIn("上游超时", out)

    def test_not_found_lists_candidates(self):
        code, _, err = self._run(["不存在"])
        self.assertEqual(code, 2)
        self.assertIn("GPU日报", err)

    def test_unpublished_refused(self):
        code, _, err = self._run(["对账草稿"])
        self.assertEqual(code, 1)
        self.assertIn("发布", err)

    def test_bad_pair(self):
        code, _, err = self._run(["GPU", "月份八月"])
        self.assertEqual(code, 2)
        self.assertIn("key=value", err)

    def test_no_token(self):
        gconfig.drop_profile("default")
        code, _, err = self._run(["GPU"])
        self.assertEqual(code, 1)
        self.assertIn("--login", err)


if __name__ == "__main__":
    unittest.main()


class NoMatchListsCandidatesTest(unittest.TestCase):
    """名字对不上时把候选列出来——run 和 export 要一样。

    回归背景（2026-08-29）：只有 run 会列，export 回一句
    「找不到唯一匹配「X」」就完了。而在 export 那条路上用户更需要提示：
    他多半正想不起来名字叫什么。
    """

    @staticmethod
    def _capture(wanted, matched, items):
        import io
        from contextlib import redirect_stderr

        from guanjia.runcmd import _say_no_match

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            _say_no_match(wanted, matched, items)
        return buffer.getvalue()

    ITEMS = [{"name": "词频统计", "published": True},
             {"name": "日报", "published": False}]

    def test_no_match_lists_everything(self):
        out = self._capture("蛤蟆", [], self.ITEMS)
        self.assertIn("找不到「蛤蟆」", out)
        self.assertIn("词频统计（已发布）", out)
        self.assertIn("日报（未发布）", out)

    def test_an_ambiguous_name_lists_only_the_matches(self):
        out = self._capture("统", [self.ITEMS[0]], self.ITEMS)
        self.assertIn("有歧义", out)
        self.assertIn("词频统计", out)
        self.assertNotIn("日报", out)

    def test_a_long_list_is_cut_with_a_hint(self):
        many = [{"name": f"工作流{i}", "published": True} for i in range(25)]
        out = self._capture("蛤蟆", [], many)
        self.assertIn("还有 15 个", out)
        self.assertIn("guanjia today", out)

    def test_an_empty_platform_does_not_crash(self):
        self.assertIn("找不到", self._capture("蛤蟆", [], []))
