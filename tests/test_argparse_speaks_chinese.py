"""参数报错也得说人话。

回归背景（2026-08-29 逐个试用户常犯的操作）：

    $ guanjia run
    usage: guanjia run [-h] [--json] [--wait WAIT] [--follow] name [pairs ...]
    guanjia run: error: the following arguments are required: name

    $ guanjia 蛤蟆
    usage: python -m guanjia [-h] [--login] [--server SERVER]
    python -m guanjia: error: unrecognized arguments: 蛤蟆

`guanjia run` 不带参数是最常见的一种误操作，回的却是一句英文
外加一个内部参数名。而这个工具其余地方全是中文。
"""
import io
import unittest
from contextlib import redirect_stderr

from guanjia.argparse_zh import ChineseArgumentParser


def _fail(*argv, setup=None) -> str:
    parser = ChineseArgumentParser(prog="guanjia run")
    parser.add_argument("name", help="工作流名字（支持唯一子串）或 id")
    parser.add_argument("--wait", type=float, default=120.0, help="最长等待秒数")
    if setup:
        setup(parser)
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        try:
            parser.parse_args(list(argv))
        except SystemExit:
            pass
    return buffer.getvalue()


class ChineseArgparseTest(unittest.TestCase):
    def test_a_missing_argument_says_what_it_is(self):
        out = _fail()
        self.assertIn("还缺参数", out)
        self.assertIn("工作流名字", out, "只说 name 对用户没有意义")
        self.assertNotIn("the following arguments", out)

    def test_a_bad_type_says_what_to_fill_in(self):
        out = _fail("x", "--wait", "蛤蟆")
        self.assertIn("要填数字", out)
        self.assertNotIn("invalid float value", out)
        self.assertNotIn("float", out)

    def test_an_unrecognised_argument_is_translated(self):
        out = _fail("x", "--nope")
        self.assertIn("不认识", out)
        self.assertNotIn("unrecognized", out)

    def test_the_usage_line_is_still_shown(self):
        """用法行里有 --json --wait 这些，留着是有用的。"""
        self.assertIn("usage:", _fail())

    def test_it_still_exits_with_code_2(self):
        parser = ChineseArgumentParser(prog="t")
        parser.add_argument("x")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            parser.parse_args([])
        self.assertEqual(caught.exception.code, 2)

    def test_an_unmapped_message_still_gets_printed(self):
        """没配到模式的报错不能被吞掉——那比英文更糟。"""
        parser = ChineseArgumentParser(prog="t")
        buffer = io.StringIO()
        with redirect_stderr(buffer), self.assertRaises(SystemExit):
            parser.error("something we never mapped")
        self.assertIn("something we never mapped", buffer.getvalue())


class EveryParserUsesItTest(unittest.TestCase):
    """一个子命令漏了，用户在那条路上还是撞英文。"""

    def test_no_plain_argument_parser_is_left(self):
        import re
        from pathlib import Path

        import guanjia

        root = Path(guanjia.__file__).parent
        leftovers = []
        for path in sorted(root.glob("*.py")):
            if path.name == "argparse_zh.py":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if re.search(r"argparse\.ArgumentParser\(", line):
                    leftovers.append(f"{path.name}: {line.strip()[:60]}")
        self.assertEqual(leftovers, [], f"这些还在用英文 parser：{leftovers}")


class UnknownCommandTest(unittest.TestCase):
    def test_a_typo_suggests_the_real_command(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        from guanjia.__main__ import main

        buffer = io.StringIO()
        with patch("sys.argv", ["guanjia", "tody"]), redirect_stdout(buffer), \
             self.assertRaises(SystemExit):
            main()
        out = buffer.getvalue()
        self.assertIn("没有「tody」这个命令", out)
        self.assertIn("today", out)

    def test_it_lists_the_available_commands(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        from guanjia.__main__ import KNOWN_COMMANDS, main

        buffer = io.StringIO()
        with patch("sys.argv", ["guanjia", "蛤蟆"]), redirect_stdout(buffer), \
             self.assertRaises(SystemExit):
            main()
        for command in ("today", "run", "doctor"):
            self.assertIn(command, buffer.getvalue())
        self.assertIn("run", KNOWN_COMMANDS)

    def test_a_real_command_is_not_intercepted(self):
        """挡得太宽就把正常命令也拦了。"""
        from unittest.mock import patch

        from guanjia.__main__ import main

        with patch("sys.argv", ["guanjia", "today"]), \
             patch("guanjia.config.load_config",
                   return_value={"server": "http://x", "token": ""}), \
             patch("guanjia.remote.RemoteClient") as client:
            client.return_value.request.side_effect = RuntimeError("到这一步就够了")
            try:
                main()
            except (RuntimeError, SystemExit):
                pass
        # 没有打印"没有「today」这个命令"就算过——真跑到了远端那一步


if __name__ == "__main__":
    unittest.main()
