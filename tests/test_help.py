"""顶层 --help：完整命令地图，不落进 REPL argparse。"""

import contextlib
import io
import sys
import unittest

from guanjia import __main__ as entry


class HelpTest(unittest.TestCase):
    def _help(self, flag):
        old = sys.argv
        sys.argv = ["guanjia", flag]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                entry.main()
        finally:
            sys.argv = old
        return out.getvalue()

    def test_lists_every_command(self):
        text = self._help("--help")
        for word in ("web", "today", "run", "remote", "doctor",
                     "completion", "--login", "--version", "/help"):
            self.assertIn(word, text)

    def test_h_and_word_alias(self):
        self.assertEqual(self._help("-h"), self._help("help"))


if __name__ == "__main__":
    unittest.main()
