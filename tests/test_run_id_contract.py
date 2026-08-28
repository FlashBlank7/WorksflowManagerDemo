"""后端少给一个字段，客户端要说人话，不能甩 KeyError。

回归背景（2026-08-28）：写第一个「别人的后端」
（examples/minimal_backend.py）时当场撞到——建运行的响应里给的是
id 不是 run_id，`guanjia run` 直接 KeyError: 'run_id'，
一个 Python traceback 糊在脸上，既没说哪里不对也没说该怎么改。

这正是「有第二个实现」要验的东西：契约只列了有哪些接口，
没说返回什么形状；实现方照着做，撞上的是栈回溯。
"""
import unittest

from guanjia.plugins import workflow
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


class RunUsesTheHelperTest(unittest.TestCase):
    """光有函数不够：run() 真调用它了吗？

    这条的由来是接线自查——把 run() 里那句 _run_id_of 换回
    created["run_id"]，只测函数的测试照样全绿，
    而真机上撞到的正是那句 KeyError。
    """

    class _Remote:
        def __init__(self, created):
            self.created = created

        def request(self, method, path, body=None):
            if method == "POST":
                return self.created
            return {"status": "succeeded", "outputs": {}, "error": ""}

    def test_missing_run_id_raises_a_readable_error_not_keyerror(self):
        from guanjia.remote import RemoteError

        with self.assertRaises(RemoteError) as caught:
            workflow.run(self._Remote({"foo": 1}), "app-1", {}, wait_seconds=1)
        self.assertIn("run_id", str(caught.exception))

    def test_plain_id_still_runs(self):
        result = workflow.run(self._Remote({"id": "r9"}), "app-1", {}, wait_seconds=5)
        self.assertEqual(result["run_id"], "r9")

    def test_start_run_uses_the_helper_too(self):
        from guanjia.remote import RemoteError

        with self.assertRaises(RemoteError):
            workflow.start_run(self._Remote({"nope": 1}), "app-1", {})
