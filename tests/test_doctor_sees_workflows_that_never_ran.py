"""doctor 也要说"这几个还没跑过"，不能跟着报「都正常」。

平台侧刚把这件事分出来（体检报告里单列一格 never_ran）：
发布了却一次都没跑过的工作流，在四个状态里落到 ok——它确实没坏，
但"正常"是个结论，而这种工作流一条证据都没有，第一次跑会怎样谁也不知道。

doctor 不读那一格的话，就会照着 counts.ok 报「N 个已发布工作流都正常」，
和面板犯同一个错。**同一个判据要铺满所有出口**，客户端也是出口。

老服务端没有 never_ran 这个键——取不到当空，doctor 照旧工作。
"""

from __future__ import annotations

import io
import re
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from guanjia import doctor


def _strip(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class FakeClient:
    report: dict = {}

    def __init__(self, *a, **k):
        pass

    def health(self):
        return {"ok": True}

    def request(self, method, path, *a, **k):
        if path == "/api/v1/me":
            return {"user": {"name": "demo", "role": "admin"}}
        if path == "/api/v1/health-report":
            return FakeClient.report
        return {}


def _run(report: dict) -> tuple[int, str]:
    FakeClient.report = report
    cfg = {"server": "http://x", "token": "t", "profile": "default"}
    buffer = io.StringIO()
    with patch.object(doctor, "RemoteClient", FakeClient), \
            patch.object(doctor, "load_config", lambda: cfg), \
            patch.object(doctor, "_scheduler_health",
                         lambda c: ({"alive": True, "seconds_since_tick": 3}, "")), \
            redirect_stdout(buffer):
        code = doctor.run()
    return code, _strip(buffer.getvalue())


class DoctorSaysWhatItCannotVouchFor(unittest.TestCase):
    def test_a_never_run_workflow_is_called_out(self):
        code, output = _run({"counts": {"ok": 3}, "items": [],
                             "never_ran": ["每日报表"]})
        self.assertIn("每日报表", output)
        self.assertIn("还没跑过", output)
        self.assertNotIn("一切正常", output)
        self.assertEqual(code, 1, "该给一条能照着做的下一步，不能算全好")

    def test_it_says_how_to_find_out(self):
        """指出问题不给下一步，等于把包袱丢给用户。"""
        _, output = _run({"counts": {"ok": 1}, "items": [], "never_ran": ["报表"]})
        self.assertIn("guanjia run", output)

    def test_many_are_summarised_not_dumped(self):
        """一屏打不下就说总数——列前三、说清一共几个。

        断言要落在**那一行**上，不能只看整段输出里有没有"9 个"：
        第一版就是那么写的，而体检那行本来就有「9 个已发布工作流都正常」，
        于是把 `等 N 个` 整个删掉照样绿（变异验证抓到的）。
        计数用 7，和 counts.ok 的 9 岔开，免得又被别处的数字蒙混过去。
        """
        names = [f"工作流{i}" for i in range(7)]
        _, output = _run({"counts": {"ok": 9}, "items": [], "never_ran": names})
        line = next(l for l in output.splitlines() if "还没跑过" in l)
        self.assertIn("工作流0", line)
        self.assertIn("7 个", line, f"没说一共几个：{line}")
        self.assertNotIn("工作流6", line, "七个名字全列出来会刷屏")

    def test_all_healthy_and_all_have_run_is_still_all_clear(self):
        """反向那一条：真的都跑过就别扫兴。"""
        code, output = _run({"counts": {"ok": 3}, "items": [], "never_ran": []})
        self.assertIn("都正常", output)
        self.assertNotIn("还没跑过", output)
        self.assertEqual(code, 0)

    def test_an_old_server_without_the_field_still_works(self):
        """老服务端没有 never_ran 这个键——不能因此炸掉整个体检。"""
        code, output = _run({"counts": {"ok": 2}, "items": []})
        self.assertIn("都正常", output)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
