"""命令行和网页壳把字符串转成值的规则，说好是同一套——第二处没人盯。

`coerce_input` 的注释写着"网页壳 app.js 的 coerceInput() 是同一套规则，
改这里记得同步改那边"，和 failures.py 那边一样：**知道是抄的，
但没有任何东西保证它不走样**。核了一遍，整数那一支确实走样了，
而且那不是措辞问题，是会静默发错值的：

    JS: Number('') === 0，Number.isInteger(0) === true  → 空串收成 0
    紧接着的必填校验判的是 String(值).trim()===''，0 不是空串 → 放行

也就是**必填的整数留空，网页壳会替你填一个 0 发出去**。
同一支还把 '3.0'、'1e3'、'0x10' 当整数收下，而 Python 的 int() 全拒。
（小数那一支反倒是对的——它显式判了空串。整数支就差这一下。）

这台机器上没有 node，跑不了真正的对拍，所以这里做两件事：
一是把 Python 那侧的规则**逐条钉死**（真值表，将来任一侧改了都得回来对），
二是读 app.js 的源码确认它用的是同一条判据。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from guanjia.plugins.workflow import InputTypeError, coerce_input

APP_JS = (Path(__file__).resolve().parent.parent / "guanjia/web/app.js").read_text(
    encoding="utf-8")


def test_the_js_side_is_actually_there():
    """先钉住读得到——读空文件的话下面的源码断言会集体全绿。"""
    assert "function coerceInput(" in APP_JS


class TestIntegers:
    @pytest.mark.parametrize("raw, want", [
        ("42", 42), ("  42  ", 42), ("-7", -7), ("+7", 7), ("0", 0),
        ("1_000", 1000),      # Python 的 int() 认下划线
    ])
    def test_accepted(self, raw, want):
        assert coerce_input(raw, "integer") == want

    @pytest.mark.parametrize("raw", [
        "",          # ← 网页壳原来在这里收成 0，然后必填校验放行
        "   ",
        "3.0",       # ← 网页壳原来收下（Number('3.0') 是整数 3）
        "1e3",       # ← 同上，收成 1000
        "0x10",      # ← 同上，收成 16
        "abc", "3,000",
    ])
    def test_refused(self, raw):
        with pytest.raises(InputTypeError, match="整数"):
            coerce_input(raw, "integer")

    def test_the_web_shell_uses_the_same_rule(self):
        """JS 那侧必须是同一条判据：先 trim，再按"只准符号加数字"判。"""
        assert r"/^[+-]?\d+(_\d+)*$/.test(s)" in APP_JS
        assert "Number(raw);if(!Number.isInteger(n))" not in APP_JS, "老规则又回来了"

    def test_the_empty_string_hole_is_named_in_the_js(self):
        """把来由写在代码边上，下次有人"简化"这一支时看得见。"""
        assert "空串会变成 0" in APP_JS


class TestNumbers:
    @pytest.mark.parametrize("raw, want", [("3.5", 3.5), ("42", 42.0), ("-0.5", -0.5)])
    def test_accepted(self, raw, want):
        assert coerce_input(raw, "number") == want

    @pytest.mark.parametrize("raw", ["", "   ", "abc"])
    def test_refused(self, raw):
        with pytest.raises(InputTypeError, match="数字"):
            coerce_input(raw, "number")

    def test_the_web_shell_also_refuses_an_empty_one(self):
        """小数那一支本来就是对的——钉住，别哪天跟着整数支一起被改坏。"""
        assert "raw.trim()===''||Number.isNaN(n)" in APP_JS


class TestBooleans:
    TRUE_WORDS = ("true", "1", "yes", "y", "是", "on")

    @pytest.mark.parametrize("raw", TRUE_WORDS)
    def test_the_true_words(self, raw):
        assert coerce_input(raw, "boolean") is True
        assert coerce_input(raw.upper(), "boolean") is True     # 大小写不敏感

    @pytest.mark.parametrize("raw", ["false", "0", "no", "n", "否", "off", "", "随便"])
    def test_everything_else_is_false(self, raw):
        assert coerce_input(raw, "boolean") is False

    def test_the_web_shell_has_the_same_word_list(self):
        listed = re.search(r"\[('true'.*?)\]\.includes", APP_JS)
        assert listed, "找不到 JS 那份真值词表"
        words = re.findall(r"'([^']+)'", listed.group(1))
        assert tuple(words) == self.TRUE_WORDS, words


class TestJsonShapes:
    @pytest.mark.parametrize("kind", ["array", "object", "any", "json"])
    def test_parsed_as_json(self, kind):
        assert coerce_input('[1, 2]', kind) == [1, 2]

    @pytest.mark.parametrize("kind", ["array", "object", "any", "json"])
    def test_bad_json_says_so(self, kind):
        with pytest.raises(InputTypeError, match="JSON"):
            coerce_input("不是JSON", kind)

    def test_the_web_shell_covers_the_same_four_kinds(self):
        assert "k==='array'||k==='object'||k==='any'||k==='json'" in APP_JS


class TestAnythingElseStaysText:
    @pytest.mark.parametrize("kind", ["string", "text", None, "", "怪类型"])
    def test_untouched(self, kind):
        assert coerce_input("  原样  ", kind) == "  原样  "
