"""网页壳收到畸形请求时，不能 500，更不能把 Python 异常原文发出去。

回归背景（2026-08-29 自查）：
    body 不是 JSON  → 500 "Expecting value: line 1 column 1 (char 0)"
    body 是数组      → 500 "'list' object has no attribute 'get'"
    地址填错         → 500 "unknown url type: 'xxxx…'"

两个毛病叠在一起：调用方发错东西却报 5xx（意味着服务端自己坏了），
以及把 AttributeError 的原文抛给调用方——既看不懂也没意义。
最后那条最要紧：在网页登录框里把地址写错，是最常见的一步。
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from guanjia import app as webapp


def _serve() -> tuple[ThreadingHTTPServer, str]:
    httpd = webapp._make_server("127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _post(base: str, path: str, raw: bytes):
    req = urllib.request.Request(base + path, data=raw, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class WebBadRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.httpd, self.base = _serve()
        self.addCleanup(self.httpd.shutdown)
        self.addCleanup(self.httpd.server_close)

    def test_non_json_body_is_a_client_error(self):
        status, body = _post(self.base, "/api/config", b"not json at all")
        self.assertEqual(status, 400)
        self.assertIn("不是合法的 JSON", body["error"])

    def test_array_body_names_what_was_expected(self):
        status, body = _post(self.base, "/api/config", json.dumps([1, 2]).encode())
        self.assertEqual(status, 400)
        self.assertIn("JSON 对象", body["error"])
        self.assertIn("list", body["error"])

    def test_bad_server_address_says_so(self):
        status, body = _post(self.base, "/api/config",
                             json.dumps({"server": "不是个地址"}).encode())
        self.assertEqual(status, 400)
        self.assertIn("http://", body["error"])

    def test_no_python_exception_text_reaches_the_caller(self):
        # 这几种输入原本都会把异常原文当响应发出去
        for raw in (b"{", b"[]", b'"just a string"', b"123",
                    json.dumps({"server": "x" * 5000}).encode()):
            status, body = _post(self.base, "/api/config", raw)
            self.assertLess(status, 500, f"{raw[:20]!r} → {status}")
            for leak in ("Traceback", "object has no attribute",
                         "Expecting value", "unknown url type"):
                self.assertNotIn(leak, body.get("error", ""), f"{raw[:20]!r}")


class LoopbackNeedsAKeyTooTest(unittest.TestCase):
    """回环也要钥匙——「能连到这个端口的人就是你」在多用户主机上不成立。

    2026-08-29：原来的判断是「绑到回环之外才要钥匙」。可 127.0.0.1:7800
    对同机**每一个**账号都开着，而网页壳背后是你的平台令牌——
    别人打开就能以你的身份跑工作流、看全部数据。
    这台开发机上就有另外两个用户在跑东西；同一天刚因为一样的理由
    把 .env 和库文件从 0644 收成了 0600。

    代价很小：钥匙第一次访问后种进 Cookie，书签照样能用。
    确定独占一台机器的人可以 --no-key，但那要他自己说。

    这里**真的跑一遍 main()**（把 serve_forever 换掉），不重建一份参数表：
    重建的那份和真的那份迟早分家，而分家之后它还会报绿。
    今天已经为这个毛病改过冒烟脚本的内部词清单。
    """

    def _run_main(self, argv):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        webapp.Handler.access_key = ""
        served = {}

        class FakeServer:
            def serve_forever(self):
                served["ok"] = True

        out = io.StringIO()
        with patch.object(webapp, "_make_server", lambda h, p: FakeServer()), \
             patch.object(webapp, "load_config",
                          lambda *a, **k: {"server": "http://x", "token": "",
                                           "user": "", "profile": "default"}), \
             patch.object(webapp.sys, "argv", ["guanjia-web", *argv]), \
             redirect_stdout(out):
            webapp.main()
        self.assertTrue(served.get("ok"), "服务没起来，这条测试等于没测")
        return webapp.Handler.access_key, out.getvalue()

    def tearDown(self):
        webapp.Handler.access_key = ""

    def test_a_key_is_required_by_default_even_on_loopback(self):
        key, printed = self._run_main([])
        self.assertTrue(key, "回环启动没要钥匙——同机别人就能用你的平台账号")
        self.assertIn(f"?k={key}", printed, "地址里得带着钥匙，否则用户打不开")

    def test_no_key_is_opt_in_and_says_what_it_costs(self):
        key, printed = self._run_main(["--no-key"])
        self.assertEqual(key, "")
        self.assertIn("同机任何账号", printed, "关掉了就得说清代价")

    def test_going_public_still_gets_a_key_and_a_warning(self):
        key, printed = self._run_main(["--host", "0.0.0.0"])
        self.assertTrue(key)
        self.assertIn("已对外开放", printed)


class NoRemoteConfiguredIsACleanRefusal(unittest.TestCase):
    """还没登录就开网页壳——每个要远端的接口都得干净地回 401。

    变异验证（2026-08-30，全量 664 条）：把 `_need_remote` 里那句
    `raise RemoteError(401, "未配置远端连接")` 去掉，一条都没红。
    去掉之后它返回 None，下游 `.request(...)` 抛 AttributeError——
    用户看到的是 500 和一段 traceback，而真相只是"还没配远端"。
    **能说清的事不该变成 500。**
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        self.addCleanup(lambda: os.environ.__setitem__("HOME", self.old_home)
                        if self.old_home is not None else None)
        self.old_remote = webapp.Handler.remote
        webapp.Handler.remote = None          # 就是"还没配"的样子
        self.addCleanup(lambda: setattr(webapp.Handler, "remote", self.old_remote))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _get(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_a_remote_backed_route_says_401_not_502(self):
        """原来 GET 一律回 502，而同样的原因走 POST 回的是 401。

        502 说的是"上游坏了"，跟"你还没登录"是两回事——
        写脚本的人按 502 会去查后端，其实只要登录一下。
        """
        status, body = self._get("/api/workflow/archived")
        self.assertEqual(status, 401, body[:200])

    def test_get_and_post_agree_on_the_status(self):
        """同一个原因在两个出口上不该长得不一样。"""
        get_status, _ = self._get("/api/workflow/archived")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/workflow/run", method="POST",
            data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                post_status = response.status
        except urllib.error.HTTPError as error:
            post_status = error.code
        self.assertEqual(get_status, post_status)

    def test_the_reason_is_readable(self):
        _, body = self._get("/api/workflow/archived")
        self.assertIn("未配置远端连接".encode("utf-8"), body)

    def test_the_static_page_still_loads(self):
        """反向：没配远端不等于整个壳都打不开——登录页正是要在这时候出现。"""
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"lg-prof", body)
