"""doctor 说「一切正常」之前，得真的查过调度器。

回归背景（2026-08-29）：调度器只在"已经有工作流误点（stale）"时才查。
可调度器刚死、还没到任何定时点的时候，一个工作流都不会 stale——
于是 doctor 一次都没查，却在最后打出「一切正常。直接 guanjia 开聊。」

而定时不开火恰恰是那种无声的故障：用户收不到任何提示，
只是报表再也不来了。诊断工具最不该做的，就是在没查过某个部件时宣布全好。

（同一天在 doctor --contract 那边修过一模一样的毛病：
结论说"只读接口全齐"，而表里只有 7 个、客户端实际调 23 个。）
"""
import io
import re
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from guanjia import doctor


def _strip(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class FakeClient:
    """假远端。health() 通了就算可达（doctor 就是这么判的）。"""

    report: dict = {"counts": {"ok": 2}, "items": []}

    def __init__(self, *a, **k):
        pass

    def health(self):
        return {"status": "ok"}

    def request(self, method, path, *a, **k):
        if path == "/api/v1/me":
            return {"user": {"name": "demo", "role": "admin"}}
        if path == "/api/v1/health-report":
            return FakeClient.report
        return {}


def _run(*, health=None, scheduler=None):
    """跑一遍 doctor，回 (退出码, 输出)。"""
    FakeClient.report = health if health is not None else {"counts": {"ok": 2}, "items": []}
    cfg = {"server": "http://x", "token": "t", "profile": "default"}
    buffer = io.StringIO()
    with patch.object(doctor, "RemoteClient", FakeClient), \
         patch.object(doctor, "load_config", lambda: cfg), \
         patch.object(doctor, "_scheduler_health", lambda c: scheduler), \
         redirect_stdout(buffer):
        code = doctor.run()
    return code, _strip(buffer.getvalue())


class DoctorChecksSchedulerTest(unittest.TestCase):
    def test_a_healthy_run_still_reports_the_scheduler(self):
        """所有工作流都好的时候，也得看见调度器那一行。"""
        _, output = _run(scheduler=({"alive": True, "seconds_since_tick": 3}, ""))
        self.assertIn("调度器在跑", output)

    def test_a_dead_scheduler_is_caught_even_when_nothing_is_stale_yet(self):
        """这就是 bug 本体：没有工作流误点，但调度器已经死了。"""
        code, output = _run(scheduler=({"alive": False, "seconds_since_tick": 900}, ""))
        self.assertIn("调度器停了", output)
        self.assertNotIn("一切正常", output)
        self.assertEqual(code, 1)

    def test_it_says_what_to_do_about_a_dead_scheduler(self):
        _, output = _run(scheduler=({"alive": False, "seconds_since_tick": 900}, ""))
        self.assertIn("定时任务不会开火", output)

    def test_the_dead_scheduler_line_carries_the_bad_mark(self):
        """**记号也要断言。**变异验证（2026-08-30）：把「调度器停了」那行的
        ✕ 换成 ✓，643 条一条都没红——上面几条只查了文字和退出码。
        一行写着「✓ 调度器停了」，眼睛先接住的是那个 ✓。
        """
        _, output = _run(scheduler=({"alive": False, "seconds_since_tick": 900}, ""))
        line = next(l for l in _strip(output).splitlines() if "调度器停了" in l)
        self.assertIn("✕", line, line)
        self.assertNotIn("✓", line, line)

    def test_a_missing_endpoint_says_not_checked_rather_than_nothing(self):
        """老服务端没这个接口——如实说"没验"，不能默默跳过还宣布全好。"""
        code, output = _run(scheduler=(None, "远端没有这个接口，多半是旧版本"))
        self.assertIn("没验", output)
        self.assertEqual(code, 0, "接口缺失不该判死")

    def test_the_reason_for_not_checking_is_specific(self):
        """没查成的原因要分开说。

        第一版一律打「没验（远端没有这个接口，多半是旧版本）」——
        可 401 的时候接口明明在，只是没登录。用户照这句去升级后端，
        白费半天工夫。诊断工具给错方向比不给方向更糟。
        """
        _, output = _run(scheduler=(None, "还没登录，查不了"))
        self.assertIn("还没登录", output)
        self.assertNotIn("旧版本", output)

    def test_the_scheduler_is_only_queried_once(self):
        """原先健康分支和 stale 分支各查一次，会打两行。"""
        calls = []

        def fake_sched(cfg):
            calls.append(1)
            return {"alive": True, "seconds_since_tick": 5}, ""

        FakeClient.report = {"counts": {"ok": 0, "stale": 1},
                             "items": [{"workflow": "日报", "state": "stale",
                                        "reason": "没按时开火"}]}
        cfg = {"server": "http://x", "token": "t", "profile": "default"}
        buffer = io.StringIO()
        with patch.object(doctor, "RemoteClient", FakeClient), \
             patch.object(doctor, "load_config", lambda: cfg), \
             patch.object(doctor, "_scheduler_health", fake_sched), \
             redirect_stdout(buffer):
            doctor.run()
        self.assertEqual(len(calls), 1, f"查了 {len(calls)} 次")
        self.assertEqual(_strip(buffer.getvalue()).count("调度器在跑"), 1)

    def test_a_stale_workflow_with_a_live_scheduler_still_gets_advice(self):
        """调度器活着但工作流没开火——建议不能丢。"""
        _, output = _run(
            health={"counts": {"ok": 0, "stale": 1},
                    "items": [{"workflow": "日报", "state": "stale", "reason": "没开火"}]},
            scheduler=({"alive": True, "seconds_since_tick": 5}, ""))
        self.assertIn("调度器是活的", output)


if __name__ == "__main__":
    unittest.main()


class AliveIsNotAllFiringTest(unittest.TestCase):
    """「调度器在跑」不等于「所有定时都开火了」。

    平台侧 2026-08-29 补了 per-application 保护：一个坏工作流不再拖垮全体。
    但它自己每轮都被跳过，而调度器照样心跳、照样报 alive。
    doctor 这时打 ✓ 就是替它瞒着——诊断工具最不该做的就是这个。
    """

    SKIPPED = {"alive": True, "seconds_since_tick": 3,
               "last_error": "这一轮跳过了 「服务器GPU日报」：KeyError: 版本查不到"}

    def test_a_skipped_schedule_is_not_a_green_tick(self):
        code, out = _run(scheduler=(self.SKIPPED, ""))
        self.assertIn("没能开火", out)
        self.assertIn("服务器GPU日报", out)
        self.assertNotIn("一切正常", out)
        self.assertNotEqual(code, 0, "有定时不开火，退出码不该是 0")

    def test_the_tick_on_that_line_is_not_green(self):
        """**这条名字里说的就是这件事，可原来没有一条断言真的看那个记号。**

        变异验证（2026-08-30，全量 643 条）：把 `mark = WARN if skipped else OK`
        改成 `mark = OK`，一条都没红——上面那条查的是下面那行详情
        （"但有定时没能开火：…"），而详情照旧会打印。
        于是用户看到的是「✓ 调度器在跑」加一行小字，眼睛先接住的是那个 ✓。
        这个类的注释写着"doctor 这时打 ✓ 就是替它瞒着"，
        断言却没落在那一行上。
        """
        _, out = _run(scheduler=(self.SKIPPED, ""))
        line = next(l for l in _strip(out).splitlines() if "调度器在跑" in l)
        self.assertNotIn("✓", line, line)
        self.assertIn("!", line, line)

    def test_a_clean_scheduler_does_get_a_green_tick_on_that_line(self):
        """反向：不能宽到"调度器那行永远不给 ✓"。"""
        _, out = _run(scheduler=({"alive": True, "seconds_since_tick": 3,
                                  "last_error": ""}, ""))
        line = next(l for l in _strip(out).splitlines() if "调度器在跑" in l)
        self.assertIn("✓", line, line)

    def test_a_clean_scheduler_is_still_a_green_tick(self):
        code, out = _run(scheduler=({"alive": True, "seconds_since_tick": 3,
                                     "last_error": ""}, ""))
        self.assertIn("调度器在跑", out)
        self.assertNotIn("没能开火", out)
        self.assertEqual(code, 0)

    def test_a_backend_without_the_field_is_treated_as_clean(self):
        """老远端没有 last_error——别凭空报一个不存在的问题。"""
        code, out = _run(scheduler=({"alive": True, "seconds_since_tick": 3}, ""))
        self.assertNotIn("没能开火", out)
        self.assertEqual(code, 0)
