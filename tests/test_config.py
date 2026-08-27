"""config 多远端档案：迁移、优先级、增删切换。零依赖，unittest 直跑。"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from guanjia import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_env = {}
        for key in ("HOME", "GUANJIA_SERVER", "GUANJIA_TOKEN", "GUANJIA_PROFILE",
                    "BENCH_SERVER", "BENCH_TOKEN"):
            self.old_env[key] = os.environ.pop(key, None)
        os.environ["HOME"] = self.tmp.name

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _write(self, data):
        (Path(self.tmp.name) / ".guanjia.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_defaults_without_file(self):
        cfg = config.load_config()
        self.assertEqual(cfg["server"], "http://127.0.0.1:8000")
        self.assertEqual(cfg["token"], "")
        self.assertEqual(cfg["profile"], "default")

    def test_reads_old_flat_format(self):
        self._write({"server": "http://a:1/", "token": "t1"})
        cfg = config.load_config()
        self.assertEqual(cfg["server"], "http://a:1")  # 尾斜杠被去掉
        self.assertEqual(cfg["token"], "t1")
        self.assertEqual(cfg["profile"], "default")

    def test_broken_json_treated_as_empty(self):
        (Path(self.tmp.name) / ".guanjia.json").write_text("{oops", encoding="utf-8")
        self.assertEqual(config.load_config()["profile"], "default")

    def test_save_login_migrates_and_activates(self):
        self._write({"server": "http://a:1", "token": "t1"})
        name = config.save_login("http://b:2", "t2", "alice", "prod")
        self.assertEqual(name, "prod")
        active, profiles = config.list_profiles()
        self.assertEqual(active, "prod")
        self.assertEqual(set(profiles), {"default", "prod"})
        self.assertEqual(profiles["default"]["token"], "t1")  # 旧配置迁移保留
        self.assertEqual(config.load_config()["server"], "http://b:2")

    def test_use_and_drop_profile(self):
        config.save_login("http://a:1", "t1", "u1", "one")
        config.save_login("http://b:2", "t2", "u2", "two")
        config.use_profile("one")
        self.assertEqual(config.load_config()["server"], "http://a:1")
        with self.assertRaises(KeyError):
            config.use_profile("nope")
        config.drop_profile("one")  # 删掉活动档案 → 活动名落到剩余档案
        active, profiles = config.list_profiles()
        self.assertEqual(active, "two")
        self.assertEqual(set(profiles), {"two"})

    def test_env_and_args_precedence(self):
        config.save_login("http://file:1", "tf", "", "default")
        os.environ["GUANJIA_SERVER"] = "http://env:2"
        self.assertEqual(config.load_config()["server"], "http://env:2")
        self.assertEqual(config.load_config(server="http://arg:3")["server"], "http://arg:3")

    def test_profile_env_selects(self):
        config.save_login("http://a:1", "t1", "", "one")
        config.save_login("http://b:2", "t2", "", "two")
        os.environ["GUANJIA_PROFILE"] = "one"
        cfg = config.load_config()
        self.assertEqual((cfg["profile"], cfg["server"]), ("one", "http://a:1"))


if __name__ == "__main__":
    unittest.main()
