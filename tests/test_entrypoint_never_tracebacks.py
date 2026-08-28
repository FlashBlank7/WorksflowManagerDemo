"""用户不该看到栈回溯。任何一条都不行。

回归背景（2026-08-29，对着一个"200 但形状不对"的后端实测）：
`guanjia today` 抛 KeyError: 'runs_today' 加一整屏回溯。
客户端里对远端返回值的直取下标有 224 处（cli.py 49、runcmd.py 74…），
逐个改 .get() 既大、又会把真实信号一起吞掉。
所以在入口兜一次：一个地方盖住全部。

顺带盯住一件容易漏的事：pyproject 的 console script 得指向带兜底的那个入口。
指错的话，`python -m guanjia` 有兜底，而装出来的 `guanjia` 命令没有——
而用户用的正是后者。
"""
import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from guanjia.__main__ import _run_cli


def _invoke(error: BaseException) -> tuple[int, str]:
    buffer = io.StringIO()
    with patch("guanjia.__main__.main", side_effect=error), redirect_stdout(buffer):
        try:
            _run_cli()
        except SystemExit as exit_error:
            return int(exit_error.code or 0), buffer.getvalue()
    return 0, buffer.getvalue()


class EntrypointCatchesEverythingTest(unittest.TestCase):
    def test_a_shape_mismatch_points_at_the_contract_check(self):
        code, output = _invoke(KeyError("runs_today"))
        self.assertEqual(code, 1)
        self.assertIn("形状对不上", output)
        self.assertIn("doctor --contract", output)
        self.assertNotIn("Traceback", output)

    def test_index_type_and_attribute_errors_are_the_same_family(self):
        for error in (IndexError("list index out of range"),
                      TypeError("'NoneType' object is not subscriptable"),
                      AttributeError("'list' object has no attribute 'get'")):
            code, output = _invoke(error)
            self.assertEqual(code, 1, error)
            self.assertIn("形状对不上", output)

    def test_ctrl_c_exits_quietly(self):
        """他自己按的，不该再教育他一遍。"""
        code, output = _invoke(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertNotIn("doctor", output)
        self.assertEqual(output.strip(), "")

    def test_an_unexpected_error_still_says_something_useful(self):
        code, output = _invoke(RuntimeError("说不清的问题"))
        self.assertEqual(code, 1)
        self.assertIn("说不清的问题", output)
        self.assertIn("guanjia doctor", output)
        self.assertNotIn("Traceback", output)

    def test_a_normal_run_is_untouched(self):
        buffer = io.StringIO()
        with patch("guanjia.__main__.main") as fake, redirect_stdout(buffer):
            _run_cli()
        fake.assert_called_once()
        self.assertEqual(buffer.getvalue(), "")

    def test_system_exit_passes_through(self):
        """命令自己 sys.exit(0) 的话，兜底不能把它改成 1。"""
        self.assertEqual(_invoke(SystemExit(0))[0], 0)
        self.assertEqual(_invoke(SystemExit(2))[0], 2)


class ConsoleScriptIsWiredToTheGuardTest(unittest.TestCase):
    """兜底是"一个函数 + 一个入口"。函数写好了没接上，等于没写。"""

    def test_pyproject_points_at_the_guarded_entry(self):
        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml"
                     ).read_text(encoding="utf-8")
        match = re.search(r"^guanjia\s*=\s*\"([^\"]+)\"", pyproject, re.M)
        self.assertIsNotNone(match, "pyproject 里找不到 guanjia 这个命令")
        self.assertEqual(match.group(1), "guanjia.__main__:_run_cli",
                         "装出来的 guanjia 命令绕过了兜底")


if __name__ == "__main__":
    unittest.main()
