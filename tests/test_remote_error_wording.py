"""后端出错时，用户看到的第一行也得是人话。

回归背景（2026-08-29，对着几种坏后端实测）：引导语一直是好的，
可它上面那一行漏了开发者写法——

    remote 500: {"detail":"internal boom"}
    后端自己出错了，稍后再试；持续如此就去看后端日志。

第一行三个问题：`remote 500:` 是开发者语言、正文是一坨 JSON、
里面那句是英文。平台侧客户端会打到的报错今天已经全部中文化，
这里只要把 detail 取出来，用户看到的就是那句中文。

还有一处：正文不是 JSON 时也走 RemoteError(200, …)，
于是印出 `remote 200:`——200 看着像成功，比不印还糊涂。
"""
import unittest

from guanjia.remote import RemoteError, RemoteUnreachable, _readable


class ReadableBodyTest(unittest.TestCase):
    def test_fastapi_detail_is_extracted(self):
        self.assertEqual(_readable('{"detail":"这个用户名已经有人用了，换一个吧"}'),
                         "这个用户名已经有人用了，换一个吧")

    def test_a_plain_body_is_left_alone(self):
        self.assertEqual(_readable("502 Bad Gateway"), "502 Bad Gateway")

    def test_broken_json_is_left_alone(self):
        body = '{"detail": 这不是合法 JSON'
        self.assertEqual(_readable(body), body)

    def test_a_non_string_detail_is_left_alone(self):
        # FastAPI 的 detail 也可能是数组（校验错误），别硬取
        body = '{"detail":[{"loc":["body"],"msg":"field required"}]}'
        self.assertEqual(_readable(body), body)

    def test_an_empty_detail_falls_back_to_the_body(self):
        self.assertEqual(_readable('{"detail":"   "}'), '{"detail":"   "}')

    def test_a_json_body_without_detail_is_left_alone(self):
        self.assertEqual(_readable('{"error":"boom"}'), '{"error":"boom"}')


class ErrorWordingTest(unittest.TestCase):
    def test_a_server_error_reads_as_chinese(self):
        message = str(RemoteError(500, '{"detail":"这个搭建还在跑，不用续——等它走完再说"}'))
        self.assertIn("后端返回 500", message)
        self.assertIn("等它走完", message)
        self.assertNotIn("remote", message)
        self.assertNotIn("{", message)

    def test_status_200_gets_no_prefix(self):
        """正文不是 JSON 时也走这里。印「remote 200」比不印还糊涂。"""
        message = str(RemoteError(200, "返回的不是 JSON（对面可能不是 guanjia 平台）：<html>"))
        self.assertTrue(message.startswith("返回的不是 JSON"), message)
        self.assertNotIn("200", message.split("：")[0])

    def test_status_zero_gets_no_prefix(self):
        self.assertTrue(str(RemoteError(0, "连不上")).startswith("连不上"))

    def test_unreachable_still_names_the_server(self):
        message = str(RemoteUnreachable("http://127.0.0.1:8000", "Connection refused"))
        self.assertIn("127.0.0.1:8000", message)
        self.assertNotIn("后端返回", message)

    def test_the_status_code_is_still_available_to_callers(self):
        """文案变了，status 这个字段不能动——契约自查按它分辨 404/401。"""
        self.assertEqual(RemoteError(404, "x").status, 404)

    def test_a_very_long_body_is_truncated(self):
        self.assertLessEqual(len(str(RemoteError(500, "啊" * 900))), 220)


if __name__ == "__main__":
    unittest.main()
