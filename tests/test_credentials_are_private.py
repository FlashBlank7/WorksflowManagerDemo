"""存令牌的文件不能全机可读。

回归背景（2026-08-29 实测）：~/.guanjia.json 里存着 API 令牌，
权限却是 **0644**。这台机器上还有别的用户——谁都能读走令牌、
以你的身份操作平台。

原因很朴素：write_text 按 umask 建文件，默认 umask 022 就是 644。
不显式收权限，就是松的。会话文件同理（里面是对话内容）。
"""
import json
import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


class ConfigIsPrivateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def test_the_config_file_is_owner_only(self):
        from guanjia import config

        target = self.home / ".guanjia.json"
        with patch.object(config, "_config_path", lambda: target):
            config._write("default", {"default": {"server": "http://x",
                                                  "token": "secret", "user": "me"}})
        self.assertEqual(_mode(target), 0o600, f"权限是 {oct(_mode(target))}")

    def test_the_token_really_is_in_there(self):
        """先确认这个文件确实存着令牌——不然上一条断言是空的。"""
        from guanjia import config

        target = self.home / ".guanjia.json"
        with patch.object(config, "_config_path", lambda: target):
            config._write("default", {"default": {"server": "http://x",
                                                  "token": "secret-token", "user": "me"}})
        self.assertIn("secret-token", target.read_text(encoding="utf-8"))

    def test_rewriting_keeps_it_private(self):
        """已经存在的文件（可能是旧版本建的 644）也要被收紧。"""
        from guanjia import config

        target = self.home / ".guanjia.json"
        target.write_text("{}", encoding="utf-8")
        target.chmod(0o644)
        with patch.object(config, "_config_path", lambda: target):
            config._write("default", {"default": {"token": "t"}})
        self.assertEqual(_mode(target), 0o600)


class SessionsArePrivateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "sessions"

    def test_the_session_directory_and_files_are_owner_only(self):
        from guanjia import sessions

        with patch.object(sessions, "DIR", self.dir):
            self.assertTrue(sessions.save("abc123", [{"role": "user", "text": "你好"}]))
            saved = self.dir / "abc123.json"
            self.assertTrue(saved.exists())
            self.assertEqual(_mode(self.dir), 0o700, oct(_mode(self.dir)))
            self.assertEqual(_mode(saved), 0o600, oct(_mode(saved)))

    def test_the_conversation_is_actually_stored(self):
        from guanjia import sessions

        with patch.object(sessions, "DIR", self.dir):
            sessions.save("abc123", [{"role": "user", "text": "机密内容"}])
            body = json.loads((self.dir / "abc123.json").read_text(encoding="utf-8"))
        self.assertIn("机密内容", json.dumps(body, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
