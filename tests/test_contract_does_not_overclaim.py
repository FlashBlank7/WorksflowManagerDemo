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

    def request(self, method, path, *args, **kwargs):
        self.seen.append(path)
        for pattern, payload in self.routes.items():
            if re.fullmatch(pattern, path):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise contract.RemoteError(404, "Not Found")


FULL = {
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
        probed = len(contract.READ_ENDPOINTS) + len(contract.ID_ENDPOINTS)
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
