"""契约不只要查「接口在不在」，还要查「返回的形状对不对」。

回归背景（2026-08-28）：写第一个第三方后端时，doctor --contract 全绿，
`guanjia run` 却抛 KeyError——清单只查了路由在不在，没查返回什么。
照着清单实现的人最容易栽在这里，而这恰恰是最难自己发现的。

字段清单从客户端**实际读取处**倒推，不是拍脑袋列的。
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from unittest.mock import patch

from guanjia.contract import READ_ENDPOINTS, missing_fields, run


class MissingFieldsTest(unittest.TestCase):
    def test_flat_field(self):
        self.assertEqual(missing_fields({"a": 1}, ("a",)), [])
        self.assertEqual(missing_fields({}, ("a",)), ["a"])

    def test_nested_field(self):
        payload = {"runs_today": {"total": 1}}
        self.assertEqual(missing_fields(payload, ("runs_today.total",)), [])
        self.assertEqual(missing_fields(payload, ("runs_today.failed",)),
                         ["runs_today.failed"])

    def test_array_element_field(self):
        self.assertEqual(missing_fields([{"id": "a"}], ("[].id",)), [])
        self.assertEqual(missing_fields([{"title": "a"}], ("[].id",)), ["[].id"])

    def test_object_where_an_array_was_promised(self):
        gaps = missing_fields({"id": "a"}, ("[].id",))
        self.assertEqual(len(gaps), 1)
        self.assertIn("应该是数组", gaps[0])

    def test_empty_array_is_not_a_gap(self):
        # 没有数据不等于形状不对
        self.assertEqual(missing_fields([], ("[].id",)), [])

    def test_falsy_values_still_count_as_present(self):
        # 0 / "" / [] 都是合法值，不该被当成缺字段
        self.assertEqual(missing_fields({"builds_active": 0}, ("builds_active",)), [])
        self.assertEqual(missing_fields({"schedules": []}, ("schedules",)), [])


def _server(payloads: dict) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            body = json.dumps(payloads.get(path, {})).encode()
            self.send_response(200 if path in payloads else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


class ShapeCheckEndToEndTest(unittest.TestCase):
    def _run(self, payloads):
        httpd, base = _server(payloads)
        try:
            out = StringIO()
            with patch("sys.stdout", out):
                code = run({"server": base, "token": "t"})
            return code, out.getvalue()
        finally:
            httpd.shutdown()

    def _complete(self):
        return {
            "/api/v1/me": {"user": {"name": "demo"}},
            "/api/v1/applications": [{"id": "a", "name": "甲"}],
            "/api/v1/overview": {
                "runs_today": {"total": 0, "succeeded": 0, "failed": 0},
                "published_workflows": 1, "builds_active": 0,
                "schedules": [], "recent_failures": []},
        }

    def test_complete_shapes_pass(self):
        code, text = self._run(self._complete())
        self.assertEqual(code, 0)
        self.assertNotIn("少了字段", text)

    def test_a_renamed_field_is_caught(self):
        payloads = self._complete()
        payloads["/api/v1/applications"] = [{"id": "a", "title": "甲"}]
        _, text = self._run(payloads)
        self.assertIn("[].name", text)
        self.assertIn("响应缺字段", text)

    def test_a_missing_nested_field_is_caught(self):
        payloads = self._complete()
        payloads["/api/v1/overview"]["runs_today"].pop("failed")
        _, text = self._run(payloads)
        self.assertIn("runs_today.failed", text)

    def test_every_endpoint_row_declares_its_fields(self):
        # 加接口时容易忘了写字段清单，那这道门就成了摆设
        for row in READ_ENDPOINTS:
            self.assertEqual(len(row), 4, row[0])
            self.assertIsInstance(row[3], tuple, row[0])
