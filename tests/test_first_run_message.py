"""从没登录过的人，不该被告知"登录态失效了"。

回归背景（2026-08-29，拿一个全新的 HOME 走新用户路径）：

    $ guanjia today
    后端返回 401：令牌不对或已失效——重新登录一次
    登录态失效了，重新登录：guanjia --login

他一次都还没登录过。这句话既说不通，也没告诉他第一步该干什么——
服务器地址从哪来、注册令牌找谁要，一个字没有。

而"登录过但令牌过期"的老用户，看到的应该还是原来那句短提示：
他知道 --login 是什么，不需要再念一遍完整流程。
"""
import unittest

from guanjia.remote import RemoteError, RemoteUnreachable, next_step


class FirstRunMessageTest(unittest.TestCase):
    def test_a_brand_new_user_is_told_how_to_start(self):
        text = next_step(RemoteError(401, "令牌不对或已失效——重新登录一次"), has_token=False)
        self.assertIn("还没登录过", text)
        self.assertIn("guanjia --login", text)
        self.assertNotIn("失效", text)

    def test_it_says_where_to_get_the_server_and_token(self):
        """新用户卡住的地方不是"敲哪个命令"，是"地址和令牌哪来的"。"""
        text = next_step(RemoteError(401, "x"), has_token=False)
        self.assertIn("服务器地址", text)
        self.assertIn("注册令牌", text)

    def test_an_expired_session_keeps_the_short_message(self):
        """老用户知道 --login 是什么，不用再念一遍完整流程。"""
        text = next_step(RemoteError(401, "x"), has_token=True)
        self.assertIn("失效", text)
        self.assertNotIn("找部署这套平台的人要", text)

    def test_403_is_treated_the_same_as_401(self):
        self.assertIn("还没登录过", next_step(RemoteError(403, "x"), has_token=False))

    def test_the_default_stays_the_old_behaviour(self):
        """不传 has_token 的调用点不能因此改口。"""
        self.assertIn("失效", next_step(RemoteError(401, "x")))

    def test_unreachable_is_unaffected_by_the_token(self):
        """连不上的时候，有没有令牌都不是重点。"""
        for has in (True, False):
            text = next_step(RemoteUnreachable("http://x", "refused"), has_token=has)
            self.assertIn("连不上后端", text)

    def test_a_server_error_is_unaffected(self):
        self.assertIn("后端自己出错", next_step(RemoteError(500, "x"), has_token=False))


class EveryEntryPassesTheFlagTest(unittest.TestCase):
    """一个入口漏传，新用户在那条路上还是看见"失效了"。"""

    def test_no_call_site_forgets_has_token(self):
        import re
        from pathlib import Path

        import guanjia

        root = Path(guanjia.__file__).parent
        bare = []
        for path in sorted(root.rglob("*.py")):
            if path.name == "remote.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"next_step\(\s*error\s*\)", line):
                    bare.append(f"{path.name}:{number}")
        self.assertEqual(bare, [], f"这些调用点没传 has_token：{bare}")


if __name__ == "__main__":
    unittest.main()
