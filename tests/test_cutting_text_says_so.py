"""截字符串的规矩收在一处：截了要说。

2026-08-30 这一天在两个仓里数出七处「干净地砍掉」。每一处单看都无所谓，
合起来是同一句话：**看的人分不出这是全文还是半截**。而这条线上最能
照着做的一句常常在末尾——平台那边量过，227 条失败里超过 500 字的 4 条，
被砍掉的尾巴恰好是「要么让节点 X 真正产出…」。

这个文件盯两件事：clip 本身，以及**它真的被接在了那些出口上**
（"函数写好了没接在调用点上"这一周撞过四次）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from guanjia.cut import clip

GUANJIA = Path(__file__).resolve().parent.parent / "guanjia"


class TestTheRuleItself:
    def test_short_text_is_untouched(self):
        assert clip("短", 10) == "短"

    def test_exactly_at_the_limit_is_untouched(self):
        """边界：正好 limit 个字不算超，不该缀省略号。"""
        assert clip("x" * 10, 10) == "x" * 10

    def test_one_over_the_limit_is_marked(self):
        assert clip("x" * 11, 10) == "x" * 10 + "…"

    def test_the_ellipsis_does_not_eat_the_body(self):
        """省略号加在 limit 之外——不然每次截都会少一个字。"""
        assert len(clip("x" * 50, 10)) == 11

    def test_none_becomes_empty_not_the_word_none(self):
        """`str(None)` 是 'None'，印给用户就是一句莫名其妙的话。"""
        assert clip(None, 10) == ""

    def test_a_non_string_is_stringified(self):
        assert clip(12345, 3) == "123…"


def _sources() -> dict[str, str]:
    return {str(p.relative_to(GUANJIA.parent)): p.read_text(encoding="utf-8")
            for p in GUANJIA.rglob("*.py")}


class TestItIsActuallyWiredUp:
    """光有函数不算数——这一周"写好了没接上"撞过四次。"""

    @pytest.mark.parametrize("path, needle", [
        ("guanjia/runcmd.py", "clip(text, 500)"),        # guanjia run 的产出
        ("guanjia/runcmd.py", "clip(error, 300)"),       # guanjia run 的报错
        ("guanjia/doctor.py", "clip(skipped, 160)"),     # 体检里被跳过的定时
        ("guanjia/plugins/workflow.py", "clip(text, 80)"),
        ("guanjia/remote.py", "clip(text, 120)"),
        ("guanjia/failures.py", "clip(error, 60)"),
        # 网页壳这两处不是 print，是塞进 JSON 交给页面显示的正文——
        # 下面那条"不许再有光秃秃的 [:N]"只盯 print 行，抓不到它们。
        ("guanjia/app.py", "clip(error, 150)"),    # 连不上远端时页面上那句
        ("guanjia/app.py", "clip(error, 200)"),    # 对话流里的报错
    ])
    def test_the_call_site_uses_it(self, path, needle):
        assert needle in _sources()[path], f"{path} 没接上"

    def test_no_prose_output_still_slices_silently(self):
        """凡是 print 出去给人读的正文，不许再出现光秃秃的 [:N]。

        只盯 print 那一行：标签、名字、时间戳这些切片是格式化不是截断
        （给会话标题缀省略号反而怪），不在这条的管辖范围。
        """
        offenders = []
        for path, text in _sources().items():
            for i, line in enumerate(text.splitlines(), 1):
                if "print(" not in line:
                    continue
                if re.search(r"\[:\s*\d{2,}\s*\]", line):
                    offenders.append(f"{path}:{i} {line.strip()[:60]}")
        assert not offenders, offenders
