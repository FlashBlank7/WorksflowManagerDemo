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

from guanjia.contract import ID_ENDPOINTS, STREAM_ENDPOINTS, READ_ENDPOINTS, run

# 取样用的假 ID。ID_ENDPOINTS 那批要先从列表接口拿到一个真 ID 才能探，
# 所以假后端必须让 /applications、/{id}/runs、/{id}/builds 回带 id 的数组。
SAMPLE = "s1"


def _resolve(template: str) -> str:
    return template.replace("{id}", SAMPLE)


# 流式那张表也要喂进去。加了新表却不加这里的话，
# "完整后端"这个夹具就不再完整了——而它整个存在的意义就是完整。
ALL_PATHS = ([row[0] for row in READ_ENDPOINTS]
             + [_resolve(row[0]) for row in ID_ENDPOINTS]
             + [_resolve(row[0]) for row in STREAM_ENDPOINTS]
             + [f"/api/v1/applications/{SAMPLE}/runs?limit=1",
                f"/api/v1/applications/{SAMPLE}/builds"])
REQUIRED = ([row[0] for row in READ_ENDPOINTS if row[1]]
            + [_resolve(row[0]) for row in ID_ENDPOINTS if row[2]]
            + [_resolve(row[0]) for row in STREAM_ENDPOINTS if row[2]]
            + [f"/api/v1/applications/{SAMPLE}/runs?limit=1",
               f"/api/v1/applications/{SAMPLE}/builds"])
OPTIONAL = ([row[0] for row in READ_ENDPOINTS if not row[1]]
            + [_resolve(row[0]) for row in ID_ENDPOINTS if not row[2]]
            + [_resolve(row[0]) for row in STREAM_ENDPOINTS if not row[2]])
# 「喂给假后端的路径」和「输出里该出现的名字」不是一回事：
# 前者要把 {id} 换成真 ID 才能被访问，后者打的是模板原样。
OPTIONAL_LABELS = ([row[0] for row in READ_ENDPOINTS if not row[1]]
                   + [row[0] for row in ID_ENDPOINTS if not row[2]]
                   + [row[0] for row in STREAM_ENDPOINTS if not row[2]])


def _shaped(path: str):
    """按契约表里登记的必填字段，现生成一个形状正好的载荷。

    写死一份"完整响应"会跟表分家——那正是这套测试反复修的毛病。
    """
    required: tuple = ()
    for row in READ_ENDPOINTS:
        if row[0] == path:
            required = row[3]
    for row in ID_ENDPOINTS:
        if _resolve(row[0]) == path:
            required = row[4]
    if not required:
        return {"ok": True}
    if any(field.startswith("[].") for field in required):
        item = {}
        for field in required:
            item[field[3:]] = "x"
        return [item]
    payload: dict = {}
    for field in required:
        target = payload
        parts = field.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = "x"
    return payload


def _server(known: set[str]) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler 的约定
            known_path = self.path in known
            self.send_response(200 if known_path else 404)
            # 流式端点必须回 text/event-stream：契约检查会核对这一项，
            # 回 JSON 的后端等于"路由在但答的不是流"，客户端会一直等不到事件
            streaming = self.path.endswith("/events")
            self.send_header(
                "Content-Type",
                "text/event-stream" if streaming and known_path else "application/json")
            self.end_headers()
            # 列表接口要回带 id 的数组，否则取样拿不到 ID，
            # ID_ENDPOINTS 那批会全部报"没验"——那测的就不是"接口在不在"了。
            # 形状也要对。原先除了几个列表接口一律回 {"ok": true}，
            # 于是"完整后端"这个夹具其实有六个接口形状是错的——
            # 只是当时结论不看形状，照样打"全齐"。结论一改成
            # "形状不对就不说能完整发挥"，这个夹具立刻现原形。
            # 载荷按契约表里的必填字段现生成，表一长它自己就跟着长。
            body = ([{"id": SAMPLE, "name": "甲"}]
                    if known_path and (self.path.endswith("/runs?limit=1")
                                       or self.path.endswith("/builds")
                                       or self.path == "/api/v1/applications")
                    else _shaped(self.path) if known_path
                    else {"ok": False})
            self.wfile.write(json.dumps(body).encode())

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
        # 只给必需的那些；可选的一律 404
        code, text = self._run(REQUIRED)
        self.assertEqual(code, 0, "可选接口缺失不该判死")
        self.assertIn("静默降级", text)
        for label in OPTIONAL_LABELS:
            self.assertIn(label, text)

    def test_every_optional_gap_explains_what_is_lost(self):
        # 只说「缺了」没用，得说清少了会怎样
        _, text = self._run(REQUIRED)
        for row in READ_ENDPOINTS:
            if not row[1]:
                self.assertIn(row[2], text)

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
