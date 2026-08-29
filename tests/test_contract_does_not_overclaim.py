"""契约自查的结论不能比它实际查过的东西强。

回归背景（2026-08-29）：结尾无条件打「只读接口全齐——guanjia 能完整发挥」，
而表里只有 7 个端点，客户端实际调 23 个。11 个既没查、也没登记进
「有副作用不探测」那张清单——其中 9 个是 GET。

后果不是抽象的：examples/minimal_backend.py 自己就实现了 draft 和 versions、
没实现 builds/transcript/artifacts/events，而检查照样给「全齐」。
照着这份清单实现后端的人，检查通过之后 `guanjia rerun`、`guanjia logs` 才炸——
而这个工具存在的全部意义就是提前告诉他还差什么。
"""
import io
import re
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from guanjia import contract


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class FakeClient:
    """按路径给假响应；没登记的路径回 404，模拟"后端没实现"。"""

    def __init__(self, routes: dict):
        self.routes = routes
        self.seen: list[str] = []

    def probe_stream(self, path):
        """假客户端也得会探流——不然契约会把它报成"没验"，
        而这个夹具声称自己是个完整后端。桩缺一个方法，
        就等于悄悄把一整类检查从"查过了"降级成"没查"。"""
        self.seen.append(path)
        for pattern, payload in self.routes.items():
            if re.fullmatch(pattern, path):
                if isinstance(payload, Exception):
                    raise payload
                return 200, "text/event-stream"
        raise contract.RemoteError(404, "Not Found")

    def request(self, method, path, *args, **kwargs):
        self.seen.append(path)
        for pattern, payload in self.routes.items():
            if re.fullmatch(pattern, path):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise contract.RemoteError(404, "Not Found")


FULL = {
    r"/health": {"status": "ok"},
    r"/api/v1/me": {"user": {"name": "demo"}},
    r"/api/v1/applications": [{"id": "a1", "name": "词频"}],
    r"/api/v1/overview": {"runs_today": {"total": 0, "succeeded": 0, "failed": 0},
                          "published_workflows": 1, "builds_active": 0,
                          "schedules": [], "recent_failures": []},
    r"/api/v1/health-report": {"counts": {}, "items": []},
    r"/api/v1/scheduler/health": {"alive": True, "seconds_since_tick": 1},
    r"/api/v1/applications-archived": [],
    r"/api/v1/applications-archivable.*": [],
    r"/api/v1/applications/a1": {"id": "a1", "name": "词频"},
    r"/api/v1/applications/a1/draft": {},
    r"/api/v1/applications/a1/versions": [],
    r"/api/v1/applications/a1/runs.*": [{"id": "r1"}],
    r"/api/v1/applications/a1/builds": [{"id": "b1"}],
    r"/api/v1/builds/b1": {},
    r"/api/v1/builds/b1/transcript": {},
    r"/api/v1/runs/r1": {"status": "succeeded"},
    r"/api/v1/runs/r1/artifacts": [],
    r"/api/v1/runs/r1/events": {},          # SSE：实际只看状态和 Content-Type
    r"/api/v1/runs/r1/events/list.*": [],
}


def _run(routes) -> tuple[int, str]:
    client = FakeClient(routes)
    buffer = io.StringIO()
    with patch.object(contract, "RemoteClient", lambda *a, **k: client), \
         redirect_stdout(buffer):
        code = contract.run({"server": "http://x", "token": "t"})
    return code, _strip_ansi(buffer.getvalue())


class ConclusionMatchesWhatWasCheckedTest(unittest.TestCase):
    def test_the_full_backend_passes_and_says_how_many(self):
        code, output = _run(FULL)
        self.assertEqual(code, 0)
        self.assertIn("只读接口全齐", output)
        # 「全齐」必须带上数字：无条件的「全齐」正是这次修的 bug
        self.assertRegex(output, r"\d+ 个只读接口全齐")

    def test_it_never_claims_more_endpoints_than_it_probed(self):
        code, output = _run(FULL)
        claimed = int(re.search(r"(\d+) 个只读接口全齐", output).group(1))
        # 三张只读表都要算——2026-08-29 加了 STREAM_ENDPOINTS，
        # 这一行没跟上，于是它把结论多说了一个报了出来。
        # 报得对：漏的是这行，不是结论。
        probed = (len(contract.READ_ENDPOINTS) + len(contract.ID_ENDPOINTS)
                  + len(contract.STREAM_ENDPOINTS))
        self.assertLessEqual(claimed, probed, "结论里的数字比实际探过的还多")

    def test_a_missing_read_endpoint_is_reported_not_swallowed(self):
        """删掉一个只读接口，结论必须变——原先它会被整个吞掉。"""
        routes = {k: v for k, v in FULL.items() if k != r"/api/v1/builds/b1/transcript"}
        _, output = _run(routes)
        self.assertIn("/api/v1/builds/{id}/transcript", output)
        self.assertNotIn("只读接口全齐", output)

    def test_a_missing_required_endpoint_fails_the_check(self):
        routes = {k: v for k, v in FULL.items() if k != r"/api/v1/runs/r1"}
        code, output = _run(routes)
        self.assertEqual(code, 1)
        self.assertIn("必需接口", output)

    def test_unsampled_endpoints_are_named_in_every_conclusion(self):
        """取不到样本时如实说「没验」，而且每条结论分支都要说。

        原先只有全绿那条分支提，degraded 分支直接 return——
        于是「必需接口齐了」后面跟着 5 个根本没探过的接口，一个字不提。
        """
        # 没有任何 run/build 样本，且缺一个可选接口 → 走 degraded 分支
        routes = {k: v for k, v in FULL.items()
                  if k not in (r"/api/v1/applications/a1/runs.*",
                               r"/api/v1/applications/a1/builds",
                               r"/api/v1/applications/a1/versions")}
        routes[r"/api/v1/applications/a1/runs.*"] = []
        routes[r"/api/v1/applications/a1/builds"] = []
        _, output = _run(routes)
        self.assertIn("没验", output)
        self.assertIn("/api/v1/runs/{id}", output)

    def test_every_id_endpoint_is_actually_probed_with_a_real_id(self):
        """模板里的 {id} 必须被替换掉——否则探的是一个不存在的字面路径。"""
        client = FakeClient(FULL)
        buffer = io.StringIO()
        with patch.object(contract, "RemoteClient", lambda *a, **k: client), \
             redirect_stdout(buffer):
            contract.run({"server": "http://x", "token": "t"})
        self.assertFalse([p for p in client.seen if "{id}" in p],
                         "有请求把 {id} 原样发出去了")


class SamplerToleranceMatchesTheClientTest(unittest.TestCase):
    """取样器不能比客户端还严——不然会把"能用"误报成"没样本"。"""

    def test_run_id_key_is_accepted_as_well_as_id(self):
        routes = dict(FULL)
        routes[r"/api/v1/applications/a1/runs.*"] = [{"run_id": "r1"}]
        _, output = _run(routes)
        self.assertNotIn("没验", output)


if __name__ == "__main__":
    unittest.main()


class ContractCoversWhatTheClientActuallyCallsTest(unittest.TestCase):
    """契约表要盖住客户端真会请求的每一个只读接口。

    2026-08-29：把 guanjia 源码里出现的 /api/v1 路径和契约表对了一遍，
    发现 `/api/v1/runs/{id}/events`（SSE，run --follow 和 REPL 跟踪搭建用）
    从来没被检查过，而结论那句写的是「只读接口全齐——guanjia 能完整发挥」。
    只实现了 events/list、没实现 events 的后端会通过检查，
    然后 --follow 当场不动。/health 也一样漏着。

    这跟上一次的毛病是同一个：**结论说的比检查到的多**。
    表是手写的，客户端是另写的，两边迟早分家——所以让测试去比。
    """

    IGNORE = {
        # f-string 切片被正则截出来的碎片，不是真路径
        "/api/v1/applications/{app[", "/api/v1/applications/{ids[",
        "/api/v1/builds/{body[",
    }

    def _called(self) -> set:
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "guanjia"
        found = set()
        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            for match in re.finditer(
                    r'["\']((?:/api/v1|/health)[^"\'\s]*)["\']',
                    path.read_text(encoding="utf-8")):
                found.add(match.group(1))
        return found

    @staticmethod
    def _norm(path: str) -> str:
        import re

        return re.sub(r"\{[^}]*\}", "{id}", path).split("?")[0].rstrip("/")

    def _listed(self) -> set:
        from guanjia import contract

        out = set()
        for row in contract.READ_ENDPOINTS:
            out.add(self._norm(row[0]))
        for row in contract.ID_ENDPOINTS:
            out.add(self._norm(row[0]))
        for row in contract.STREAM_ENDPOINTS:
            out.add(self._norm(row[0]))
        for name, _purpose in contract.WRITE_ENDPOINTS:
            out.add(self._norm(name.split()[-1]))
        return out

    def test_no_endpoint_is_called_without_being_in_the_table(self):
        called = {self._norm(p) for p in self._called()
                  if p not in self.IGNORE}
        called -= {self._norm(p) for p in self.IGNORE}
        gaps = sorted(called - self._listed())
        self.assertEqual(gaps, [],
                         f"客户端会请求、但契约表里没有（结论会多说）：{gaps}")

    def test_the_count_matches_what_is_actually_probed(self):
        """结论里那个数必须等于三张只读表加起来。

        加了新表却不改计数的话，这句话会比实际查过的少报——
        而这句话的全部意义就是"数清楚查了几个"。
        """
        import inspect

        from guanjia import contract

        source = inspect.getsource(contract.run)
        self.assertIn("STREAM_ENDPOINTS", source,
                      "计数没把流式表算进去")


class TheFullFixtureIsActuallyFullTest(unittest.TestCase):
    """FULL 自称是"完整后端"，那它就得盖住表里每一条。

    2026-08-29 往 READ_ENDPOINTS 加 /health、往新表加 SSE 端点时，
    这份手写的 FULL 立刻落后了——而它落后的表现是
    「完整后端居然没通过」，还算响了。更糟的情况是反过来：
    表里删掉一条，FULL 多一条没人用的路由，谁也不知道。

    所以让测试去比，而不是靠记得同步两处。
    """

    def test_every_table_entry_has_a_route_in_the_fixture(self):
        from guanjia import contract

        rows = ([row[0] for row in contract.READ_ENDPOINTS]
                + [row[0] for row in contract.ID_ENDPOINTS]
                + [row[0] for row in contract.STREAM_ENDPOINTS])
        missing = []
        for template in rows:
            path = (template.replace("{id}", "a1")
                    if "/applications/{id}" in template
                    else template.replace("{id}", "b1")
                    if "/builds/{id}" in template
                    else template.replace("{id}", "r1"))
            if not any(re.fullmatch(pattern, path) for pattern in FULL):
                missing.append(template)
        self.assertEqual(missing, [],
                         f"FULL 自称完整，却没有这些路由：{missing}")



class StreamEndpointMustActuallyStreamTest(unittest.TestCase):
    """SSE 端点回 200 还不够——回的得是流。

    一个把 /runs/{id}/events 实现成"返回一个 JSON 数组"的后端，
    路由在、状态码 200，而 guanjia 会挂在那儿等一个永远不来的事件。
    只看状态码的检查会给它打勾。
    """

    class _JsonInsteadOfStream(FakeClient):
        def probe_stream(self, path):
            self.seen.append(path)
            return 200, "application/json"          # 路由在，但不是流

    def test_a_json_answer_on_a_stream_path_is_flagged(self):
        client = self._JsonInsteadOfStream(FULL)
        out = io.StringIO()
        with patch.object(contract, "RemoteClient", lambda *a, **k: client), \
             redirect_stdout(out):
            contract.run({"server": "http://x", "token": "t"})
        text = _strip_ansi(out.getvalue())
        self.assertIn("text/event-stream", text)
        self.assertNotIn("只读接口全齐", text)

    def test_a_real_stream_is_accepted(self):
        """别把闸关死：正经回 text/event-stream 的要能过。"""
        client = FakeClient(FULL)
        out = io.StringIO()
        with patch.object(contract, "RemoteClient", lambda *a, **k: client), \
             redirect_stdout(out):
            code = contract.run({"server": "http://x", "token": "t"})
        self.assertEqual(code, 0)
        self.assertIn("只读接口全齐", _strip_ansi(out.getvalue()))
