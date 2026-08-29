"""子命令不能把用户敲的参数默默吞掉。

回归背景（2026-08-29 实测）：

    guanjia today --server http://别的机器

一声不吭地照旧查了**本机**。today 和 doctor 那两条分支压根不解析参数，
用户敲什么都被默默丢掉。屏幕上于是是一份看起来完全正常的报表，
而它来自另一台机器——用户不会知道。

**默默忽略比直接报错糟得多**：报错用户会改，忽略他不会知道。
诊断工具尤其如此：`guanjia doctor --server 生产机` 诊断的是本机，
给出的结论全是错对象的。

run / rerun / export 早就会说「不认识这些参数」了，只有这两条漏了——
又是同一个闸没装满出口。

顺带把 --server/--token/--profile 真的接上：拒绝是底线，能用才是答案。
"""
import io
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch


def _strip(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class ConnectionArgsTest(unittest.TestCase):
    def test_the_server_flag_is_read(self):
        from guanjia.__main__ import _connection_args

        got = _connection_args("guanjia today", ["--server", "http://x"])
        self.assertEqual(got["server"], "http://x")

    def test_token_and_profile_are_read_too(self):
        from guanjia.__main__ import _connection_args

        got = _connection_args("guanjia today",
                               ["--token", "t", "--profile", "prod"])
        self.assertEqual((got["token"], got["profile"]), ("t", "prod"))

    def test_nothing_given_means_nothing_overridden(self):
        """不给就是不覆盖——None 交给 load_config 去用档案里的值。"""
        from guanjia.__main__ import _connection_args

        self.assertEqual(_connection_args("guanjia today", []),
                         {"server": None, "token": None, "profile": None})

    def test_an_unknown_flag_is_refused_in_chinese(self):
        from guanjia.__main__ import _connection_args

        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            _connection_args("guanjia today", ["--胡说八道"])
        self.assertNotEqual(caught.exception.code, 0)
        self.assertIn("不认识这些参数", _strip(err.getvalue()))


class TodayHonoursTheServerFlagTest(unittest.TestCase):
    """光会拒绝还不够——写了地址就得真去那台机器。"""

    def test_the_given_server_is_the_one_queried(self):
        from guanjia import __main__ as entry

        seen = {}

        class Fake:
            def __init__(self, server, token, *a, **k):
                seen["server"] = server

            def request(self, method, path, **kw):
                if path.endswith("/overview"):
                    return {"runs_today": {"total": 0, "succeeded": 0,
                                           "failed": 0, "running": 0},
                            "published_workflows": 0, "builds_active": 0,
                            "week": [], "schedules": [], "recent_failures": []}
                from guanjia.remote import RemoteError
                raise RemoteError(404, "没有这个端点")

        buf = io.StringIO()
        with patch("guanjia.remote.RemoteClient", Fake), \
             patch("guanjia.config.load_config",
                   lambda server=None, token=None, profile=None: {
                       "server": server or "http://本机", "token": "t", "user": "me"}), \
             patch.object(entry.sys, "argv",
                          ["guanjia", "today", "--server", "http://别的机器"]), \
             redirect_stdout(buf):
            entry.main()
        self.assertEqual(seen.get("server"), "http://别的机器")


class DoctorHonoursTheServerFlagTest(unittest.TestCase):
    def test_doctor_diagnoses_the_server_it_was_told_to(self):
        """自诊断诊断错对象，比不诊断更糟。"""
        from guanjia import doctor

        seen = {}

        class Fake:
            def __init__(self, server, token=None, *a, **k):
                seen.setdefault("servers", []).append(server)

            def health(self):
                return {"status": "ok"}

            def request(self, method, path, *a, **k):
                if path == "/api/v1/me":
                    return {"user": {"name": "demo", "role": "admin"}}
                return {"counts": {"ok": 0}, "items": []}

        buf = io.StringIO()
        with patch.object(doctor, "RemoteClient", Fake), \
             patch.object(doctor, "list_profiles", lambda: ("default", {})), \
             patch.object(doctor, "_scheduler_health",
                          lambda c: ({"alive": True, "seconds_since_tick": 1}, "")), \
             redirect_stdout(buf):
            doctor.run({"server": "http://被指定的", "token": "t", "profile": "default"})
        self.assertTrue(seen.get("servers"), "一次远端都没连")
        self.assertTrue(all(s == "http://被指定的" for s in seen["servers"]), seen)

    def test_it_still_works_with_no_config_passed(self):
        """老调用方（不传 cfg）不能被这次改动弄坏。"""
        from guanjia import doctor

        class Dead:
            def __init__(self, server, token=None, *a, **k):
                self.server = server

            def health(self):
                from guanjia.remote import RemoteUnreachable
                raise RemoteUnreachable(self.server, "Connection refused")

        buf = io.StringIO()
        with patch.object(doctor, "load_config",
                          lambda: {"server": "http://档案里的", "token": "",
                                   "profile": "default"}), \
             patch.object(doctor, "list_profiles", lambda: ("default", {})), \
             patch.object(doctor, "RemoteClient", Dead), \
             redirect_stdout(buf):
            doctor.run()
        self.assertIn("档案里的", _strip(buf.getvalue()))


if __name__ == "__main__":
    unittest.main()
