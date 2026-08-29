"""地址写歪是最平常的用户失误，不该被当成"意料之外的问题"。

回归背景（2026-08-29 实测）：

    $ guanjia doctor --server 'http://[bad'
    出了意料之外的问题：Invalid IPv6 URL
    哪里不对可以自查：guanjia doctor

三处都不对：
· 地址写错不是"意料之外"，是最常见的一种手误；
· "Invalid IPv6 URL" 是英文异常字符串，不是给用户的话；
· 给的下一步是"运行 guanjia doctor"——他刚运行的就是它，这是个死圈。

原因：urllib.request.Request(...) 在 try **外面**，它抛的 ValueError
（unknown url type / Invalid IPv6 URL）不在捕获的那几类里，
于是一路裸奔到顶层兜底。

修在 RemoteClient 一处，所有命令一起受益——地址是每条命令都要用的东西，
在每个入口各写一遍 except 才是没数清出口。
"""
import unittest

from guanjia.remote import (RemoteAddressInvalid, RemoteClient, RemoteError,
                            RemoteUnreachable, next_step)


class BadAddressTest(unittest.TestCase):
    def test_a_malformed_url_is_a_remote_error_not_a_raw_valueerror(self):
        for bad in ("http://[bad", "不是地址", "://x"):
            with self.assertRaises(RemoteError, msg=bad):
                RemoteClient(bad, "t", timeout=1).request("GET", "/health")

    def test_it_says_the_address_is_wrong_in_chinese(self):
        try:
            RemoteClient("http://[bad", "t", timeout=1).request("GET", "/health")
        except RemoteError as error:
            self.assertIn("服务器地址不对", str(error))
            self.assertIn("http://主机:端口", str(error))
        else:
            self.fail("没抛")

    def test_an_empty_server_does_not_print_an_empty_hole(self):
        try:
            RemoteClient("", "t", timeout=1).request("GET", "/health")
        except RemoteError as error:
            self.assertIn("（空）", str(error))

    def test_existing_unreachable_handlers_still_catch_it(self):
        """做成 RemoteUnreachable 的子类，是为了各处已有的 except 一个不用改。

        改成独立异常的话，那些 `except RemoteUnreachable` 全都接不住——
        修好一个入口、放跑其余的，就是这么发生的。
        """
        self.assertTrue(issubclass(RemoteAddressInvalid, RemoteUnreachable))
        try:
            RemoteClient("http://[bad", "t", timeout=1).request("GET", "/health")
        except RemoteUnreachable:
            pass
        else:
            self.fail("现成的 except RemoteUnreachable 接不住它")

    def test_the_next_step_is_about_fixing_the_address(self):
        """连不上的人要的是"确认后端启动了"，地址写歪的人要的是"改地址"。

        不分岔的话，给他的三条建议一条都不适用。
        """
        step = next_step(RemoteAddressInvalid("http://[bad", "Invalid IPv6 URL"))
        self.assertIn("改一下服务器地址", step)
        self.assertNotIn("确认它启动了", step)

    def test_the_next_step_does_not_send_him_back_to_doctor(self):
        """原来的死圈：doctor 让你去跑 doctor。"""
        step = next_step(RemoteAddressInvalid("http://[bad", "Invalid IPv6 URL"))
        self.assertNotIn("guanjia doctor", step)

    def test_a_real_connection_failure_still_says_connection_failure(self):
        """别把"连不上"也说成"地址不对"——那是另一种毛病，另一套下一步。"""
        error = RemoteUnreachable("http://127.0.0.1:59999", "Connection refused")
        self.assertIn("连不上", str(error))
        self.assertIn("连不上后端", next_step(error))


if __name__ == "__main__":
    unittest.main()
