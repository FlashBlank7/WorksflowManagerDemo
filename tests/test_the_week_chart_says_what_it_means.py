"""近 7 日那条趋势条，每一格代表什么——此前没有任何测试。

变异验证（2026-08-30，全量 505 条）：`_cell` 的三个判据**一个都没被抓住**——
  · `fail > ok` 改成 `>=`：成败持平的那天会被标成「失败居多」
  · 「○ 跑了但没出结果」这一档整个去掉
  · 「· 无运行」这一档整个去掉——**那天什么都没跑，画出来是 ✓ 全成**

最后一条最要命，而且和这个项目已经写过一遍的判据是同一条：
没跑过不等于好（health 那边的「还没跑过，好不好还看不出来」）。
趋势条是 REPL 进来第一眼看到的东西，一排绿勾意味着"这周挺好"，
而真相可能是"这周根本没跑"。

每一档都配一个反向，否则把 _cell 写成"永远返回 ✕"也能全绿。
"""

from __future__ import annotations

from guanjia.overview_view import _cell, render


def day(ok=0, fail=0, other=0, date="2026-08-30"):
    return {"date": date, "ok": ok, "fail": fail, "other": other}


class TestEachCellMeansOneThing:
    def test_nothing_ran_is_not_a_green_check(self):
        """空的一天必须看得出是空的。画成 ✓ 等于谎报「这天全成」。"""
        assert _cell(day()) == "·"

    def test_all_succeeded_is_a_check(self):
        assert _cell(day(ok=3)) == "✓"

    def test_some_failed_but_success_leads_is_the_middle_mark(self):
        assert _cell(day(ok=3, fail=1)) == "△"

    def test_failures_outnumbering_successes_is_the_bad_mark(self):
        assert _cell(day(ok=1, fail=3)) == "✕"

    def test_a_tie_is_not_yet_failures_leading(self):
        """3 成 3 败是「有失败」，不是「失败居多」。
        `>` 写成 `>=` 全量 505 条都抓不住——这条就是钉那个边界。"""
        assert _cell(day(ok=3, fail=3)) == "△"

    def test_ran_but_produced_nothing_has_its_own_mark(self):
        """排队/进行中/暂停：跑了，但还没有结果。
        既不能算成功也不能算失败，更不能算「没跑」。"""
        assert _cell(day(other=2)) == "○"

    def test_all_five_marks_are_distinct(self):
        """五档不能有两档撞成同一个字符——撞了就等于少一档。"""
        marks = [_cell(day()), _cell(day(ok=1)), _cell(day(ok=3, fail=1)),
                 _cell(day(ok=1, fail=3)), _cell(day(other=1))]
        assert len(set(marks)) == 5, marks

    def test_other_is_optional(self):
        """老远端不给 other 字段时不能炸。"""
        assert _cell({"date": "2026-08-30", "ok": 1, "fail": 0}) == "✓"


class TestTheLegendMatchesWhatIsDrawn:
    def test_every_mark_that_can_appear_is_explained(self):
        """图例里少一个字符，那个字符出现时就没人知道它什么意思。"""
        lines = render({
            "runs_today": {"total": 0, "succeeded": 0, "failed": 0, "running": 0},
            "published_workflows": 0, "builds_active": 0,
            "week": [day(), day(ok=1), day(ok=3, fail=1),
                     day(ok=1, fail=3), day(other=1)],
            "recent_failures": [], "recent_failures_total": 0,
        })
        week_line = next(t for _, t in lines if "近7日" in t)
        legend = week_line.split("（", 1)[1]
        for mark in ("·", "✓", "△", "✕", "○"):
            assert mark in legend, f"图例里没有 {mark}"
