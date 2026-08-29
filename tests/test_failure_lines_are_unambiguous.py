"""失败清单那行字不能有歧义。

回归背景（2026-08-29）：`guanjia today` 打的是

    ✕ 文本行数与净字数统计 ×13 @2026-08-28T10:03:36  run fc2279c5  缺少必填输入「text」

13 和一个具体时刻贴在一起，读起来像"那天失败了 13 次"或
"那一刻失败了 13 次"。真值是"这个毛病前后一共 13 次，最近的一次在那时"。

同一个歧义先在服务端被抓到过——管家把 count 读成了当天的次数，
给模型的那一份于是改成了「这个原因一共出现过几次」「最近一次失败在」。
但 CLI、REPL、网页三处照旧：**闸只装在一个出口上**。
现在三处共用 guanjia/failures.py 的措辞。
"""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from guanjia.failures import summarize

REAL = {"workflow": "文本行数与净字数统计", "count": 13,
        "at": "2026-08-28T10:03:36+00:00", "run_id": "fc2279c5",
        "error": "缺少必填输入「text」"}


class WordingTest(unittest.TestCase):
    def test_the_count_says_what_it_counts(self):
        head, tail = summarize(REAL)
        self.assertIn("同样的毛病 13 次", tail)

    def test_the_time_says_it_is_the_latest_one(self):
        _, tail = summarize(REAL)
        self.assertIn("最近一次", tail)

    def test_the_count_and_the_time_are_not_glued_together(self):
        """`×13 @时刻` 就是原来的写法——两个数之间必须隔着说明词。"""
        head, tail = summarize(REAL)
        whole = f"{head} {tail}"
        self.assertNotIn("×13", whole)
        self.assertNotIn("13 @", whole)
        # 「13」和「08-28」之间要有汉字隔着，不能直接相邻
        between = whole[whole.index("13") + 2:whole.index("08-28")]
        self.assertTrue(any("一" <= c <= "鿿" for c in between), repr(between))

    def test_a_single_failure_does_not_claim_a_repeat(self):
        """只失败过一次就别说"同样的毛病 1 次"，那是废话也是噪音。"""
        _, tail = summarize({**REAL, "count": 1})
        self.assertNotIn("同样的毛病", tail)
        self.assertIn("最近一次", tail)

    def test_the_workflow_and_the_reason_lead(self):
        """人最想先知道的是哪个工作流、什么毛病，不是编号和时刻。"""
        head, _ = summarize(REAL)
        self.assertTrue(head.startswith("文本行数与净字数统计"), head)
        self.assertIn("缺少必填输入", head)
        self.assertNotIn("fc2279c5", head)

    def test_the_timestamp_is_readable(self):
        _, tail = summarize(REAL)
        self.assertIn("08-28 10:03", tail)
        self.assertNotIn("2026-08-28T10:03:36", tail)

    def test_a_missing_reason_does_not_print_an_empty_gap(self):
        head, _ = summarize({**REAL, "error": ""})
        self.assertIn("没有留下原因", head)

    def test_a_weird_timestamp_is_passed_through_not_crashed(self):
        """远端换了时间格式也不该把 today 弄崩——显示丑一点好过打不出来。"""
        for odd in ("", None, "刚刚", "2026-08-28"):
            _, tail = summarize({**REAL, "at": odd})
            self.assertTrue(tail)

    def test_a_non_numeric_count_does_not_crash(self):
        _, tail = summarize({**REAL, "count": "很多"})
        self.assertIn("最近一次", tail)


class EveryExitUsesItTest(unittest.TestCase):
    """出口要数全：CLI 的 today、REPL 的 /today，都得走同一套措辞。

    （网页那份在 app.js 里，同样的措辞，由浏览器渲染，这里测不到。）
    """

    OVERVIEW = {
        "runs_today": {"total": 1, "succeeded": 1, "failed": 0, "running": 0},
        "published_workflows": 3, "builds_active": 0,
        "week": [], "schedules": [], "recent_failures": [REAL],
    }

    def _fake_client(self, extra_404=True):
        overview = self.OVERVIEW

        class Fake:
            def __init__(self, *a, **k):
                pass

            def request(self, method, path, **kw):
                if path.endswith("/overview"):
                    return overview
                from guanjia.remote import RemoteError
                raise RemoteError(404, "没有这个端点")   # 体检端点不影响 today 主体

        return Fake

    def test_the_today_command_uses_it(self):
        from guanjia import __main__ as entry

        buf = io.StringIO()
        with patch("guanjia.remote.RemoteClient", self._fake_client()), \
             patch("guanjia.config.load_config",
                   lambda *a, **k: {"server": "http://x", "token": "t", "user": "me"}), \
             patch.object(entry.sys, "argv", ["guanjia", "today"]), \
             redirect_stdout(buf):
            entry.main()
        out = buf.getvalue()
        self.assertIn("同样的毛病 13 次", out)
        self.assertNotIn("×13", out)
        self.assertNotIn("2026-08-28T10:03:36", out)



class TruncationIsAnnouncedTest(unittest.TestCase):
    """列表截了就要说——本周第四次同一个形状：给一页、不说这是一页。

    面板一屏只放得下几行，"几行"很容易被读成"就这些"，
    而第 6 种毛病可能才是要命的那个。
    """

    def _overview(self, shown_rows, total=None):
        d = {"recent_failures": [dict(REAL) for _ in range(shown_rows)]}
        if total is not None:
            d["recent_failures_total"] = total
        return d

    def test_it_says_how_many_kinds_are_hidden(self):
        from guanjia.failures import more_kinds_note

        note = more_kinds_note(self._overview(8, total=20), shown=5)
        self.assertIn("15", note)          # 20 种，屏幕上 5 种

    def test_it_counts_from_what_is_on_screen_not_what_arrived(self):
        """远端给了 8 条、屏幕只放 5 条——藏起来的是 15 不是 12。"""
        from guanjia.failures import more_kinds_note

        self.assertIn("15", more_kinds_note(self._overview(8, total=20), shown=5))

    def test_nothing_is_said_when_nothing_is_hidden(self):
        from guanjia.failures import more_kinds_note

        self.assertEqual(more_kinds_note(self._overview(3, total=3), shown=5), "")

    def test_an_old_backend_without_the_total_does_not_lie(self):
        """老远端没有这个字段：宁可不说，也不能谎报"没有更多"。

        但手里这批本身超出屏幕时，那部分还是要说。
        """
        from guanjia.failures import more_kinds_note

        self.assertEqual(more_kinds_note(self._overview(3), shown=5), "")
        self.assertIn("3", more_kinds_note(self._overview(8), shown=5))

    def test_the_today_command_prints_it(self):
        from guanjia import __main__ as entry

        overview = {
            "runs_today": {"total": 1, "succeeded": 1, "failed": 0, "running": 0},
            "published_workflows": 3, "builds_active": 0,
            "week": [], "schedules": [],
            "recent_failures": [dict(REAL) for _ in range(8)],
            "recent_failures_total": 20,
        }

        class Fake:
            def __init__(self, *a, **k):
                pass

            def request(self, method, path, **kw):
                if path.endswith("/overview"):
                    return overview
                from guanjia.remote import RemoteError
                raise RemoteError(404, "没有这个端点")

        buf = io.StringIO()
        with patch("guanjia.remote.RemoteClient", Fake), \
             patch("guanjia.config.load_config",
                   lambda *a, **k: {"server": "http://x", "token": "t", "user": "me"}), \
             patch.object(entry.sys, "argv", ["guanjia", "today"]), \
             redirect_stdout(buf):
            entry.main()
        self.assertIn("还有 15 种", buf.getvalue())

if __name__ == "__main__":
    unittest.main()
