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
            # SSE 路径必须回 text/event-stream：契约会核对这一项，
            # 回 JSON 的后端等于"路由在但答的不是流"
            self.send_header(
                "Content-Type",
                "text/event-stream" if self.path.endswith("/events")
                else "application/json")
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
            # 需要 ID 的那批：先让取样拿得到 a，再让每条路径都在。
            # 原先 _complete() 只有上面三个，名字叫"完整"其实只覆盖三分之一——
            # 2026-08-29 补 ID 端点时它先红了，红得对。
            "/api/v1/applications/a/runs": [{"id": "a"}],
            "/api/v1/applications/a/builds": [{"id": "a"}],
            "/api/v1/applications/a": {"id": "a", "name": "甲"},
            "/api/v1/applications/a/draft": {},
            "/api/v1/applications/a/versions": [],
            "/api/v1/builds/a": {},
            "/api/v1/builds/a/transcript": {},
            "/api/v1/runs/a": {"status": "succeeded"},
            "/api/v1/runs/a/artifacts": [],
            "/api/v1/runs/a/events/list": [],
            # 这两个是 2026-08-29 加进契约表的：/health 和 SSE 实时流。
            # 名字叫 _complete 的夹具，表一长就得跟着长——
            # 不跟的话它会以"完整后端居然没过"的形式炸出来（红得对），
            # 但更糟的是反过来：表里删一条、夹具留一条，谁也不知道。
            "/health": {"status": "ok"},
            "/api/v1/runs/a/events": {},
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
