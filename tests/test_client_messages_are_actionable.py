"""报错要给出路，而且不能是英文异常原文。

回归背景（2026-08-29 逐条试用户会撞到的路）：

    $ guanjia remote use 蛤蟆   → 没有档案「蛤蟆」            （有哪些？没说）
    $ guanjia import bad.json  → 不是合法 JSON：Expecting value: line 1 column 1 (char 0)
    $ guanjia import /没有.json → 读不了文件：[Errno 2] No such file or directory: …

三条都是同一个毛病：把异常原样印出来，用户既看不懂也不知道下一步做什么。
"""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class ImportMessagesTest(unittest.TestCase):
    def test_a_missing_file_says_the_path_not_the_errno(self):
        from guanjia import runcmd

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            code = runcmd.import_main(["/没有这个文件.json"])
        out = buffer.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("/没有这个文件.json", out)
        self.assertNotIn("Errno", out)
        self.assertNotIn("No such file", out)

    def test_a_broken_json_says_where_and_what_to_do(self):
        from guanjia import runcmd

        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("不是 json", encoding="utf-8")
            buffer = io.StringIO()
            with redirect_stderr(buffer):
                code = runcmd.import_main([str(bad)])
        out = buffer.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("第 1 行", out)
        self.assertIn("guanjia export", out, "没告诉他快照该从哪来")
        self.assertNotIn("Expecting value", out)


class RemoteProfileMessageTest(unittest.TestCase):
    def test_an_unknown_profile_lists_the_real_ones(self):
        from guanjia.__main__ import main

        buffer = io.StringIO()
        with patch("sys.argv", ["guanjia", "remote", "use", "蛤蟆"]), \
             patch("guanjia.config.use_profile", side_effect=KeyError("蛤蟆")), \
             patch("guanjia.config.list_profiles",
                   return_value=("default", {"default": {}, "线上": {}})), \
             redirect_stdout(buffer), self.assertRaises(SystemExit):
            main()
        out = buffer.getvalue()
        self.assertIn("没有档案「蛤蟆」", out)
        self.assertIn("default", out)
        self.assertIn("线上", out)

    def test_with_no_profiles_it_says_how_to_add_one(self):
        from guanjia.__main__ import main

        buffer = io.StringIO()
        with patch("sys.argv", ["guanjia", "remote", "use", "蛤蟆"]), \
             patch("guanjia.config.use_profile", side_effect=KeyError("蛤蟆")), \
             patch("guanjia.config.list_profiles", return_value=("", {})), \
             redirect_stdout(buffer), self.assertRaises(SystemExit):
            main()
        self.assertIn("remote add", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
