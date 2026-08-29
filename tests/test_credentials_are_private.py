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


class OldLooseFilesGetTightenedTest(unittest.TestCase):
    """光在"写"的时候收是不够的。

    这次改动之前登录过的人，配置文件是 0644；他只要不再改配置，
    就永远走不到 _write，那份令牌一直躺在那儿给同机所有人读。
    老文件名 .bench.json 更彻底：只读不写，永远收不到。

    所以读的时候也收。这是我们自己建的文件，收它不算越权。
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self._env = patch.dict(os.environ, {"HOME": str(self.home)})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.assertEqual(Path.home(), self.home, "这套测试要靠 HOME 真被改掉")

    def _loose(self, name: str) -> Path:
        path = self.home / name
        path.write_text(json.dumps({"server": "http://x", "token": "老令牌"}),
                        encoding="utf-8")
        path.chmod(0o644)
        return path

    def test_just_reading_the_config_tightens_it(self):
        from guanjia import config

        path = self._loose(".guanjia.json")
        self.assertEqual(config.load_config()["token"], "老令牌", "得真读到了才算")
        self.assertEqual(_mode(path), 0o600, oct(_mode(path)))

    def test_the_old_filename_is_tightened_too(self):
        """.bench.json 我们只读不写，不在读这一侧收就永远收不到。"""
        from guanjia import config

        path = self._loose(".bench.json")
        self.assertEqual(config.load_config()["token"], "老令牌")
        self.assertEqual(_mode(path), 0o600, oct(_mode(path)))

    def test_a_broken_config_is_tightened_before_it_is_given_up_on(self):
        """坏 JSON 当空处理——但里面照样可能有半截令牌，权限还是得收。"""
        from guanjia import config

        path = self.home / ".guanjia.json"
        path.write_text('{"token": "半截', encoding="utf-8")
        path.chmod(0o644)
        config.load_config()
        self.assertEqual(_mode(path), 0o600, oct(_mode(path)))

    def test_a_stricter_choice_is_left_alone(self):
        """0400 比 0600 还严，可能是用户故意的——别替他放宽。"""
        from guanjia import config

        path = self._loose(".guanjia.json")
        path.chmod(0o400)
        config.load_config()
        self.assertEqual(_mode(path), 0o400, oct(_mode(path)))


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
