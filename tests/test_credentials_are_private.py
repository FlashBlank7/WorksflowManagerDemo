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

    def test_it_is_never_group_readable_even_for_an_instant(self):
        """"最后收成 0600"不够——中间那一小段也不能松。

        原来是 write_text 建文件、再 chmod，中间文件已经带着令牌、
        权限还是 0644。实测拿一个线程死盯着看，6103 次采样里
        **8 次逮到 0644**——这台机器上确实还有别的用户。
        现在用 os.open 带 0o600 建，一出生就是紧的。

        测法要小心：**事后那道 chmod 会把结果补成 0600**，
        所以光看最终权限，"建的时候是松的"照样绿（第一版就是这么写的，
        变异验证时 0o666 的实现一条都没红）。
        所以这里把 _private 停掉再看——验的是"建出来就是紧的"。
        umask 设成 0（"什么都不收"）：按 umask 建的会是 0666，
        按显式 mode 建的仍是 0600。
        """
        from guanjia import config

        target = self.home / ".guanjia.json"
        old_umask = os.umask(0)
        try:
            with patch.object(config, "_config_path", lambda: target), \
                    patch.object(config, "_private", lambda path: None):
                config._write("default", {"default": {"token": "secret"}})
        finally:
            os.umask(old_umask)
        self.assertEqual(_mode(target), 0o600, f"建出来就是 {oct(_mode(target))}")
        self.assertIn("secret", target.read_text(encoding="utf-8"),
                      "前提：这个文件里确实有令牌")

    def test_a_crash_midway_does_not_lose_the_saved_login(self):
        """写到一半掉电，留下的必须还是**旧的完整配置**，不是半截。

        原来是 write_text：先截断再写。崩在中间就留下一个残缺 json，
        下次启动 _read_raw 把它当空配置吞掉（那儿是 except 全捕），
        用户的登录就这么没了，而且没有任何提示。
        """
        from guanjia import config

        target = self.home / ".guanjia.json"
        with patch.object(config, "_config_path", lambda: target):
            config._write("default", {"default": {"server": "http://old",
                                                  "token": "old-token"}})

            def boom(fd, data):
                raise KeyboardInterrupt("拔电源")

            with patch.object(os, "write", boom):
                with self.assertRaises(KeyboardInterrupt):
                    config._write("default", {"default": {"token": "new"}})

        raw = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(raw["profiles"]["default"]["token"], "old-token")

    def test_no_temp_file_is_left_behind(self):
        """临时文件不能留在原地——那份也带着令牌，而且没人会去收拾它。"""
        from guanjia import config

        target = self.home / ".guanjia.json"
        with patch.object(config, "_config_path", lambda: target):
            config._write("default", {"default": {"token": "t"}})
        leftovers = [p.name for p in self.home.iterdir() if p.name != ".guanjia.json"]
        self.assertEqual(leftovers, [], f"剩下了 {leftovers}")

    def test_when_the_temp_file_route_fails_it_still_saves_and_cleans_up(self):
        """临时文件这条路走不通时的兜底：配置照样存下，且不留残渣。

        这一条是**逼着走 except 那一支**才有意义——不逼的话，
        兜底里的清理代码整段删掉，上面几条照样全绿（实测如此）。
        存不下配置比权限松更糟，所以兜底必须真的能存下。
        """
        from guanjia import config

        target = self.home / ".guanjia.json"
        real_replace = os.replace

        def fail(src, dst):
            raise OSError("这个文件系统不支持换名")

        with patch.object(config, "_config_path", lambda: target), \
                patch.object(os, "replace", fail):
            config._write("default", {"default": {"token": "fallback-token"}})
        self.assertIs(os.replace, real_replace, "补丁没退干净")

        self.assertIn("fallback-token", target.read_text(encoding="utf-8"))
        self.assertEqual(_mode(target), 0o600)
        leftovers = [p.name for p in self.home.iterdir() if p.name != ".guanjia.json"]
        self.assertEqual(leftovers, [], f"兜底路径留下了 {leftovers}")


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

    def test_a_crash_midway_keeps_the_previous_conversation(self):
        """存到一半被中断，留下的必须还是**上一次的完整对话**。

        原来是 write_text：先截断再写。网页壳被 Ctrl-C、机器掉电，
        留下半截 json，load 捕 JSONDecodeError 返回 None——
        整段对话就这么没了。而且丢的不只是这一轮：
        截断先发生，**上一次存好的内容也一起没**。
        """
        from guanjia import sessions

        with patch.object(sessions, "DIR", self.dir):
            sessions.save("abc123", [{"role": "user", "text": "第一轮"}])

            def boom(fd, data):
                raise KeyboardInterrupt("拔电源")

            with patch.object(os, "write", boom):
                with self.assertRaises(KeyboardInterrupt):
                    sessions.save("abc123", [{"role": "user", "text": "第二轮"}])

            back = sessions.load("abc123")
        self.assertIsNotNone(back, "上一次的对话被写坏了")
        self.assertIn("第一轮", json.dumps(back, ensure_ascii=False))

    def test_sessions_and_the_config_share_one_implementation(self):
        """两处各写一遍的话，迟早只有一处被修。

        同一个判据没铺满所有出口，这一周已经中过好几次——
        所以这里直接钉住"用的是同一个函数"。
        """
        from guanjia import config, sessions

        self.assertIs(sessions.write_private, config.write_private)


if __name__ == "__main__":
    unittest.main()
