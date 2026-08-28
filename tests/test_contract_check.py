"""契约自查得真的查得出「少了什么」，不然它只是个会说 ✓ 的摆设。

用一个可配置的假后端：让它只认某些路径，其余一律 404，
看自查能不能分辨「必需缺失」「可选缺失」「全齐」。
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from unittest.mock import patch

from guanjia.contract import READ_ENDPOINTS, run

ALL_PATHS = [path for path, _, _ in READ_ENDPOINTS]
REQUIRED = [path for path, required, _ in READ_ENDPOINTS if required]
OPTIONAL = [path for path, required, _ in READ_ENDPOINTS if not required]


def _server(known: set[str]) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 的约定
            known_path = self.path in known
            self.send_response(200 if known_path else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": known_path}).encode())

        def log_message(self, *_args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


class ContractCheckTest(unittest.TestCase):
    def _run(self, known):
        httpd, base = _server(set(known))
        try:
            out = StringIO()
            with patch("sys.stdout", out):
                code = run({"server": base, "token": "t"})
            return code, out.getvalue()
        finally:
            httpd.shutdown()

    def test_complete_backend_passes(self):
        code, text = self._run(ALL_PATHS)
        self.assertEqual(code, 0)
        self.assertIn("全齐", text)

    def test_missing_required_endpoint_fails(self):
        code, text = self._run([p for p in ALL_PATHS if p != "/api/v1/overview"])
        self.assertEqual(code, 1, "少了必需接口却报通过，等于没查")
        self.assertIn("/api/v1/overview", text)
        self.assertIn("必需", text)

    def test_missing_optional_endpoint_warns_but_passes(self):
        code, text = self._run(REQUIRED)
        self.assertEqual(code, 0, "可选接口缺失不该判死")
        self.assertIn("静默降级", text)
        for path in OPTIONAL:
            self.assertIn(path, text)

    def test_every_optional_gap_explains_what_is_lost(self):
        # 只说「缺了」没用，得说清少了会怎样
        _, text = self._run(REQUIRED)
        for _, required, consequence in READ_ENDPOINTS:
            if not required:
                self.assertIn(consequence, text)

    def test_unreachable_backend_stops_early(self):
        out = StringIO()
        with patch("sys.stdout", out):
            result = run({"server": "http://127.0.0.1:9", "token": "t"})
        self.assertEqual(result, 1)
        self.assertIn("连不上后端", out.getvalue())

    def test_side_effecting_endpoints_are_listed_not_probed(self):
        # 探测别人的生产库不能有副作用；没验的要如实说没验
        _, text = self._run(ALL_PATHS)
        self.assertIn("不自动探测", text)
        self.assertIn("POST /api/v1/assistant/agent", text)
