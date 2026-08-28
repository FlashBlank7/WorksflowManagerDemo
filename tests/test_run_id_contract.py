"""后端少给一个字段，客户端要说人话，不能甩 KeyError。

回归背景（2026-08-28）：写第一个「别人的后端」
（examples/minimal_backend.py）时当场撞到——建运行的响应里给的是
id 不是 run_id，`guanjia run` 直接 KeyError: 'run_id'，
一个 Python traceback 糊在脸上，既没说哪里不对也没说该怎么改。

这正是「有第二个实现」要验的东西：契约只列了有哪些接口，
没说返回什么形状；实现方照着做，撞上的是栈回溯。
"""
import unittest

from guanjia.plugins.workflow import _run_id_of
from guanjia.remote import RemoteError


class RunIdContractTest(unittest.TestCase):
    def test_the_documented_field_works(self):
        self.assertEqual(_run_id_of({"run_id": "r1"}, "发起运行"), "r1")

    def test_plain_id_is_accepted_too(self):
        # 这个字段两种叫法都常见，能认就认
        self.assertEqual(_run_id_of({"id": "r2"}, "发起运行"), "r2")

    def test_run_id_wins_when_both_are_present(self):
        self.assertEqual(_run_id_of({"id": "r-old", "run_id": "r-new"}, "发起运行"),
                         "r-new")

    def test_missing_field_explains_what_the_backend_should_return(self):
        with self.assertRaises(RemoteError) as caught:
            _run_id_of({"foo": 1}, "发起运行")
        message = str(caught.exception)
        self.assertIn("run_id", message)      # 该给什么
        self.assertIn("foo", message)         # 实际给了什么

    def test_empty_response_is_named_as_such(self):
        with self.assertRaises(RemoteError) as caught:
            _run_id_of({}, "发起运行")
        self.assertIn("空响应", str(caught.exception))

    def test_blank_values_do_not_count_as_a_run_id(self):
        for payload in ({"run_id": ""}, {"run_id": "   "}, {"run_id": None}):
            with self.assertRaises(RemoteError):
                _run_id_of(payload, "发起运行")
