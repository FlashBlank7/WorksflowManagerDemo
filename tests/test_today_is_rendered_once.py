"""「今日统筹」那一屏只许有一份渲染。

两处各写各的时长歪了（2026-08-29 对比）：

  guanjia today 有、REPL 没有：近 7 日趋势条、体检里不正常的那几条、
                              失败列 5 条（REPL 3 条）、"为什么失败"的提示、
                              进行中为 0 时不显示那一栏
  REPL 有、guanjia today 没有：定时的"最近触发"日期

**招牌那条路（REPL）反而少了最有用的一块**——趋势条和体检。
两份各改各的，谁也不知道对方少了什么。

现在合成一份 overview_view.render；样式还是各按各的口味上色，
但**内容必须一致**。失败列几条留成参数：那是屏幕密度，不是内容差别。
"""

from __future__ import annotations

import ast
from pathlib import Path

from guanjia.overview_view import render

ROOT = Path(__file__).resolve().parent.parent


def _overview(**extra):
    base = {
        "runs_today": {"total": 3, "succeeded": 2, "failed": 1, "running": 0},
        "published_workflows": 3,
        "builds_active": 0,
        "week": [{"date": "2026-08-28", "ok": 2, "fail": 1, "other": 0},
                 {"date": "2026-08-29", "ok": 1, "fail": 0, "other": 0}],
        "schedules": [{"workflow": "日报", "at": "08:00",
                       "timezone": "Asia/Shanghai",
                       "last_fire_date": "2026-08-29"}],
        "recent_failures": [],
        "recent_failures_total": 0,
    }
    base.update(extra)
    return base


def _text(lines) -> str:
    return "\n".join(text for _style, text in lines)


class TestTheScreenHasEverythingBothUsedToHave:
    def test_the_week_chart_is_there(self):
        """REPL 原来没有这一条——最有用的一块。"""
        body = _text(render(_overview()))
        assert "近7日" in body and "08-29" in body

    def test_a_schedule_shows_when_it_last_fired(self):
        """`guanjia today` 原来没有这一条。"""
        assert "最近触发 2026-08-29" in _text(render(_overview()))

    def test_health_problems_show_up(self):
        health = {"items": [{"workflow": "坏的", "state": "broken",
                             "reason": "近7天全部失败"}]}
        body = _text(render(_overview(), health=health))
        assert "坏的" in body and "近7天全部失败" in body

    def test_never_run_is_called_out_apart(self):
        """没跑过的不是"坏"，单独一行说——和体检那边一个口径。"""
        body = _text(render(_overview(), health={"items": [], "never_ran": ["新的"]}))
        assert "新的" in body and "还没跑过" in body

    def test_healthy_items_are_not_listed(self):
        """只列不正常的——把好的也列出来就成了刷屏。"""
        health = {"items": [{"workflow": "好的", "state": "ok", "reason": ""}]}
        assert "好的" not in _text(render(_overview(), health=health))


class TestTheDetailsThatWereRefinedInOnlyOnePlace:
    def test_running_is_hidden_when_zero(self):
        """REPL 原来一直显示"进行中0"。"""
        assert "⋯" not in _text(render(_overview()))

    def test_running_is_shown_when_there_is_some(self):
        body = _text(render(_overview(
            runs_today={"total": 3, "succeeded": 1, "failed": 0, "running": 2})))
        assert "⋯2" in body

    def test_the_failure_limit_is_a_parameter_not_a_fork(self):
        """屏幕密度可以不同，内容不能不同。"""
        failures = [{"workflow": f"w{i}", "error": "boom", "count": 1,
                     "at": "2026-08-28T10:00:00"} for i in range(5)]
        def _rows(shown: int) -> int:
            # 只数失败那几行。整段里 "✕" 还出现在标题（✕1）和图例
            # （✕失败居多）里——**断言要落在那几行上**，
            # 第一版按整段数，5 和 3 全被标题图例顶成一样（实测）。
            lines = render(_overview(recent_failures=failures,
                                     recent_failures_total=5),
                           failures_shown=shown)
            return sum(1 for _s, text in lines if text.startswith("  ✕ "))

        assert _rows(3) == 3 and _rows(5) == 5

    def test_the_failure_block_says_it_is_not_today(self):
        """顶上写着"今日运行"，这一栏是"最近"——不说清会被当成今天的。"""
        failures = [{"workflow": "w", "error": "boom", "count": 1,
                     "at": "2026-08-28T10:00:00"}]
        assert "最近的失败" in _text(render(_overview(recent_failures=failures)))


class TestNeitherCallerRendersItAgain:
    """防它再长歪：两处都不许自己拼那一屏。"""

    @staticmethod
    def _calls_render(path: str) -> bool:
        return "overview_view import render" in (ROOT / path).read_text(encoding="utf-8")

    def test_the_command_uses_the_shared_renderer(self):
        assert self._calls_render("guanjia/__main__.py")

    def test_the_repl_uses_the_shared_renderer(self):
        assert self._calls_render("guanjia/cli.py")

    def test_nobody_builds_the_headline_by_hand(self):
        """那句"今日运行 N（✓… ✕…）"只许出现在渲染器里。"""
        owners = [path.name for path in (ROOT / "guanjia").rglob("*.py")
                  if "今日运行 " in path.read_text(encoding="utf-8")]
        assert owners == ["overview_view.py"], owners


def test_an_old_backend_without_health_still_renders():
    """体检端点缺席时（老远端）主体照常出——不能整屏空掉。"""
    assert "今日运行" in _text(render(_overview(), health=None))


def test_the_renderer_has_no_print():
    """渲染器只回行、不打印：打印了就没法给两种样式复用。"""
    source = (ROOT / "guanjia/overview_view.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "print"]
    assert not calls
