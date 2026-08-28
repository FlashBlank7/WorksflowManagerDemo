"""终端里 **加粗** 不该显示成星号。

回归背景（2026-08-28 看录好的 demo 才发现）：网页壳有 md() 把
**x** 渲染成 <b>x</b>，CLI 直接原样打印，于是招牌动线的结果长这样：
    - **行数**: 3 行
    - **净字数**: 5 字
访客第一眼看到的就是它。
"""
import unittest

from guanjia.cli import render_md, stream_chunk

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

    def test_python_operators_are_not_eaten(self):
        """这是给开发者用的终端工具，不能把人要复制走的代码静默改错。

        原本 ** 两侧不管有没有空白都当加粗，于是：
            "2 ** 10 = 1024，2 ** 20"  →  "2 [粗] 10 = 1024，2 [复位] 20"
            "{**a, **b}"               →  "{a, b}"
        一问「怎么合并两个字典」就能撞上。
        """
        for code in ("2 ** 10 = 1024，2 ** 20 = 1048576",
                     "合并字典用 {**a, **b}",
                     "dict(**base, **patch)",
                     "a ** b ** c",
                     "kwargs 用 **kw 展开"):
            self.assertEqual(render_md(code), code, code)

    def test_whitespace_padded_markers_are_not_bold(self):
        # 左右紧挨非空白才算标记（CommonMark 的 flanking 规则）
        self.assertEqual(render_md("**  空白开头**"), "**  空白开头**")
        self.assertEqual(render_md("**结尾空白  **"), "**结尾空白  **")

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


class StreamChunkTest(unittest.TestCase):
    """流式分片的接线：判据有人守不代表接线有人守。

    这一组的由来是接线自查——把 REPL 里的 render_md 换成直接 print，
    只测 render_md 的用例照样全绿。逻辑因此从 REPL 里拎出来单独测。
    """

    def _feed(self, chunks):
        pending, out = "", []
        for chunk in chunks:
            text, pending = stream_chunk(pending, chunk)
            out.append(text)
        return "".join(out), pending

    def test_bold_split_across_chunks_is_rendered_not_leaked(self):
        out, pending = self._feed(["- **行", "数**: 3\n"])
        self.assertEqual(out, f"- {BOLD}行数{RESET}: 3\n")
        self.assertEqual(pending, "")

    def test_context_marker_split_across_chunks_is_filtered(self):
        out, _ = self._feed(["<上下文 上一轮", '做了="x" />它不能发邮件\n'])
        self.assertEqual(out, "它不能发邮件\n")

    def test_plain_text_streams_immediately(self):
        # 没有标记的正文要照常一个字一个字冒，不能全攒到行尾
        out, pending = self._feed(["跑完", "了"])
        self.assertEqual(out, "跑完了")
        self.assertEqual(pending, "")

    def test_a_pending_marker_holds_the_whole_line(self):
        """出现标记后整行都攒着，不只攒带标记的那一截。

        故意选的简单做法：只要尾巴里有 * ` <，整段就等到行尾再渲染。
        代价是这一行少了点「逐字冒」的实时感；换来的是不会有半个 **
        或半个 <上下文 抢先冒到屏幕上。绝大多数句子没有标记，不受影响。
        """
        out, pending = self._feed(["前面 **粗"])
        self.assertEqual(out, "")
        self.assertEqual(pending, "前面 **粗")
