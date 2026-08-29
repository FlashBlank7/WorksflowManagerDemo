"""失败那一行有**四个**出口，措辞必须一致——第四个此前没人盯着。

guanjia/failures.py 的头一段写着这件事的来由：同一句话原先在 CLI、REPL、
网页三处各写各的，「工作流 ×13 @2026-08-28T10:03:36」有歧义，
改的时候只改得动一处。抽出 failures.py 就是为了"改一次三处都跟着变"。

**可是网页壳是 JS，它拿不到那个模块**。app.js 里是手抄的一份，
注释还写着"CLI 和 REPL 走 guanjia/failures.py 的同一套措辞"——
也就是说作者知道它是抄的，但没有任何东西保证它不走样。

2026-08-30 就抓到一处走样：Python 那边把 `error[:60]` 改成截了缀省略号，
JS 那份还是干净地 `.slice(0,60)`。同一个毛病、第四个出口。

所以这个文件干一件事：**把两份措辞钉在一起**。JS 没法在这里跑，
那就读它的源码，逐句核对 Python 那边真正生成的字符串。
措辞要改就两边一起改，改漏一边这里就红。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guanjia.failures import more_kinds_note, summarize

APP_JS = (Path(__file__).resolve().parent.parent / "guanjia/web/app.js").read_text(
    encoding="utf-8")


def test_the_file_is_actually_there():
    """先钉住有东西可核——读空文件的话下面每一条都会一路全绿。"""
    assert len(APP_JS) > 2_000, len(APP_JS)
    assert "ov-failures" in APP_JS


class TestTheRepeatedFailureWording:
    def test_the_many_times_phrase_matches(self):
        """Python 生成「同样的毛病 13 次，最近一次 …」，JS 必须一字不差。"""
        _, tail = summarize({"workflow": "日报", "error": "x", "count": 13,
                             "at": "2026-08-28T10:03:36"})
        assert tail.startswith("同样的毛病 13 次，最近一次 ")
        assert "'同样的毛病 '+f.count+' 次，最近一次 '" in APP_JS

    def test_the_single_time_phrase_matches(self):
        """一次就是一次，不能也说成「同样的毛病 1 次」。"""
        _, tail = summarize({"workflow": "日报", "error": "x", "count": 1,
                             "at": "2026-08-28T10:03:36"})
        assert tail.startswith("最近一次 ")
        assert "'最近一次 '" in APP_JS

    def test_the_run_id_separator_matches(self):
        _, tail = summarize({"workflow": "日报", "error": "x", "count": 1,
                             "at": "2026-08-28T10:03:36", "run_id": "abc123"})
        assert tail.endswith(" · run abc123")
        assert "· run ${esc(f.run_id)}" in APP_JS


class TestTheTruncationNote:
    def test_python_marks_a_cut_reason(self):
        head, _ = summarize({"workflow": "日报", "error": "错" * 200})
        assert head.endswith("…")

    def test_the_web_shell_marks_it_too(self):
        """2026-08-30 走样的就是这一处：JS 那份还在干净地 slice。"""
        assert ".slice(0,60)}" not in APP_JS, "网页壳又在干净地砍了"
        assert "clip(f.error||'',60)" in APP_JS

    def test_both_cut_at_the_same_width(self):
        """一边 60 一边 40 的话，同一条失败在两处长得不一样。"""
        head, _ = summarize({"workflow": "日报", "error": "错" * 200})
        assert head.count("错") == 60
        assert "60)" in APP_JS


class TestTheMoreKindsNote:
    def test_python_says_how_many_kinds_are_hidden(self):
        note = more_kinds_note({"recent_failures": [{}, {}],
                                "recent_failures_total": 9}, shown=2)
        assert "还有 7 种别的毛病没列出来" in note

    def test_the_web_shell_says_the_same(self):
        assert "还有 '+(allFails-shownFails)+' 种别的毛病没列出来" in APP_JS

    def test_neither_side_claims_there_are_no_more_when_it_cannot_tell(self):
        """老远端没给总数时两边都得闭嘴——**谎报"没有更多"比不提更糟**。"""
        assert more_kinds_note({"recent_failures": [{}, {}]}, shown=5) == ""
        assert "typeof d.recent_failures_total==='number'" in APP_JS


@pytest.mark.parametrize("phrase", ["近期没有失败", "还有 "])
def test_the_wordings_this_file_pins_are_all_present(phrase):
    """免得哪天 app.js 被整个重写、上面那些 `in` 断言集体变成空断言。"""
    assert phrase in APP_JS
