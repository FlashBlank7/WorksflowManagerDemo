"""出错时的下一步要跟着原因走。

回归背景：新用户装上 guanjia、还没有后端，`guanjia today` 回他
「先运行 guanjia --login」——他没有服务器，登录一百次也没用。
"""
import unittest

from guanjia.remote import RemoteError, RemoteUnreachable, next_step


class NextStepTest(unittest.TestCase):
    def test_unreachable_never_tells_you_to_log_in(self):
        step = next_step(RemoteUnreachable("http://127.0.0.1:8000", "Connection refused"))
        self.assertNotIn("--login", step)
        # 得说清 guanjia 需要一个后端，并给出没有后端时的去处
        self.assertIn("薄客户端", step)
        self.assertIn("doctor", step)

    def test_unreachable_message_has_no_fake_status_code(self):
        # status 0 是内部记号，印成 "remote 0:" 会被当成错误代码去搜
        text = str(RemoteUnreachable("http://127.0.0.1:8000", "Connection refused"))
        self.assertNotIn("remote 0", text)
        self.assertIn("连不上", text)

    def test_real_status_codes_are_still_shown(self):
        # 2026-08-29 前缀从 "remote 401: " 换成了「后端返回 401：」——
        # 这条测试要保的是"码还看得见"，不是那串英文写法本身。
        message = str(RemoteError(401, "令牌不对或已失效——重新登录一次"))
        self.assertIn("401", message)
        self.assertNotIn("remote", message)

    def test_expired_session_says_log_in_not_deploy(self):
        step = next_step(RemoteError(401, "令牌不对或已失效——重新登录一次"))
        self.assertIn("--login", step)
        self.assertNotIn("部署", step)

    def test_a_permission_wall_is_not_called_an_expired_session(self):
        """403 和 401 是两件事，原来合在一起说"重新登录"。

        平台的 403 是「这一步只有管理员能做——找这套平台的管理员帮忙」：
        **登录是好的，权限不够**。让他再登一次同一个账号只会撞同一堵墙。
        建议给错方向比不给更糟——doctor 那边早就为同一条道理分过岔
        （"还没登录" vs "令牌失效"）。
        """
        step = next_step(RemoteError(403, "这一步只有管理员能做——找这套平台的管理员帮忙"))
        self.assertIn("权限", step)
        self.assertNotIn("重新登录：guanjia --login", step)
        self.assertNotIn("失效", step)

    def test_a_403_before_logging_in_gets_the_first_run_guide(self):
        """没登录就撞 403 的人，缺的和撞 401 的人是同一步——给完整那份。

        （拆 401/403 时我给 403 单写了一句短的，
        test_first_run_message 里那条当场变红。测试是对的：
        第一次用的人要的是完整流程，不是一句 --login。）
        """
        step = next_step(RemoteError(403, "需要身份"), has_token=False)
        self.assertIn("还没登录过", step)
        self.assertIn("找部署这套平台的人要", step)

    def test_missing_endpoint_points_at_version_drift(self):
        step = next_step(RemoteError(404, "Not Found"))
        self.assertIn("版本", step)

    def test_server_side_failure_is_not_blamed_on_the_user(self):
        for status in (500, 502, 503):
            step = next_step(RemoteError(status, "boom"))
            self.assertIn("后端", step)
            self.assertNotIn("--login", step)

    def test_anything_else_still_gets_a_way_forward(self):
        for status in (400, 409, 418, 429):
            step = next_step(RemoteError(status, "?"))
            self.assertTrue(step.strip())
            self.assertIn("doctor", step)
