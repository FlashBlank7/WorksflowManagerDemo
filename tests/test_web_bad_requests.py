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
