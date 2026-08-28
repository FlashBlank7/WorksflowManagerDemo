"""终端里 **加粗** 不该显示成星号。

回归背景（2026-08-28 看录好的 demo 才发现）：网页壳有 md() 把
**x** 渲染成 <b>x</b>，CLI 直接原样打印，于是招牌动线的结果长这样：
    - **行数**: 3 行
    - **净字数**: 5 字
访客第一眼看到的就是它。
"""
import unittest

from guanjia.cli import render_md

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


class RenderMarkdownTest(unittest.TestCase):
    def test_bold_becomes_terminal_bold(self):
        self.assertEqual(render_md("- **行数**: 3 行"),
                         f"- {BOLD}行数{RESET}: 3 行")

    def test_inline_code_is_dimmed(self):
        self.assertEqual(render_md("用 `text` 参数"), f"用 {DIM}text{RESET} 参数")

    def test_plain_text_is_untouched(self):
        for line in ("普通一行", "", "跑成了，行数 3、净字数 5"):
            self.assertEqual(render_md(line), line)

    def test_single_asterisk_is_not_markup(self):
        # 乘号、脚注这类单星号不能被吃掉
        self.assertEqual(render_md("星号*单个*不动"), "星号*单个*不动")
        self.assertEqual(render_md("3 * 4 = 12"), "3 * 4 = 12")

    def test_several_bold_spans_on_one_line(self):
        self.assertEqual(render_md("**甲**和**乙**"),
                         f"{BOLD}甲{RESET}和{BOLD}乙{RESET}")

    def test_internal_context_marker_is_filtered(self):
        """服务端已经在出口剪了；流式分片逐字发出，这边再挡一道。"""
        self.assertEqual(render_md('<上下文 上一轮做了="x" />它不能发邮件'),
                         "它不能发邮件")

    def test_ordinary_angle_brackets_survive(self):
        self.assertEqual(render_md("用 <b> 标签"), "用 <b> 标签")

    def test_unclosed_marker_is_left_alone(self):
        # 模型写了半截，不能把后面整行都当成加粗吞掉
        self.assertEqual(render_md("**没有收尾"), "**没有收尾")
