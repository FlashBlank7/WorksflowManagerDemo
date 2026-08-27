"""REPL Tab 补全器：四层候选逻辑（纯函数测，模拟行缓冲）。"""

import os
import tempfile
import unittest
from unittest import mock

from guanjia import cli
from guanjia import config as gconfig


class CompleterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp.name
        for key in ("GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE"):
            os.environ.pop(key, None)

    def tearDown(self):
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        self.tmp.cleanup()
        cli._WF_CACHE[:] = []

    def _all(self, buffer, text):
        with mock.patch.object(cli.readline, "get_line_buffer", return_value=buffer):
            out, state = [], 0
            while True:
                item = cli._completer(text, state)
                if item is None:
                    return out
                out.append(item)
                state += 1

    def test_slash_commands(self):
        self.assertEqual(self._all("/re", "/re"), ["/remote"])
        self.assertIn("/today", self._all("/", "/"))

    def test_remote_subcommands(self):
        self.assertEqual(self._all("/remote u", "u"), ["use"])
        self.assertEqual(sorted(self._all("/remote ", "")), ["add", "list", "rm", "use"])

    def test_remote_profile_names(self):
        gconfig.save_login("http://a:1", "t", "", "prod")
        gconfig.save_login("http://b:2", "t", "", "pre")
        self.assertEqual(sorted(self._all("/remote use p", "p")), ["pre", "prod"])
        self.assertEqual(self._all("/remote rm prod", "prod"), ["prod"])

    def test_workflow_names_after_wf(self):
        cli._WF_CACHE[:] = ["GPU日报", "对账"]
        self.assertEqual(self._all("跑一下 GPU", "GPU"), ["GPU日报"])
        self.assertEqual(self._all("x", "没有的"), [])


if __name__ == "__main__":
    unittest.main()
