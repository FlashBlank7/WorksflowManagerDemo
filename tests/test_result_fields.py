"""运行结果字段来源：顶层 outputs/error 优先，状态集覆盖全。

真机缺陷（2026-08-28）：平台的 WorkflowRunState 模型根本没有 error 字段，
客户端却只读 state.error —— `guanjia run` 失败时显示"错误：None"，无法诊断；
outputs 读 state 里逐节点拍平的中间态，展示出来是某个中间节点的 payload。
"""

import unittest

from guanjia.plugins import workflow
from guanjia import runcmd


class ResultFieldsTest(unittest.TestCase):
    def test_error_prefers_top_level(self):
        run = {"status": "failed",
               "error": "node start failed: missing required input: sales",
               "state": {"inputs": {}}}          # state 里没有 error —— 真实形状
        self.assertIn("missing required input", workflow._result_error(run))

    def test_error_falls_back_to_state(self):
        run = {"status": "failed", "error": None, "state": {"error": "老远端写这里"}}
        self.assertEqual(workflow._result_error(run), "老远端写这里")

    def test_error_empty_when_absent(self):
        self.assertEqual(workflow._result_error({"status": "succeeded"}), "")

    def test_outputs_prefer_top_level(self):
        run = {"outputs": {"report": "业务结果"},
               "state": {"outputs": {"mid": {"payload": "中间态"}}}}
        self.assertEqual(workflow._result_outputs(run), {"report": "业务结果"})

    def test_outputs_fall_back_to_flattened_state(self):
        run = {"outputs": {}, "state": {"outputs": {
            "n1": {"a": 1}, "n2": {"b": 2}}}}
        self.assertEqual(workflow._result_outputs(run), {"a": 1, "b": 2})

    def test_flatten_keeps_conflicting_keys(self):
        """同名键不再静默覆盖——冲突的那个带上节点名。"""
        run = {"state": {"outputs": {"n1": {"x": 1}, "n2": {"x": 2}}}}
        flat = workflow._result_outputs(run)
        self.assertEqual(flat["x"], 1)
        self.assertEqual(flat["n2.x"], 2)

    def test_terminal_statuses_cover_paused_and_cancelled(self):
        self.assertIn("paused", workflow.TERMINAL_STATUSES)
        self.assertIn("cancelled", workflow.TERMINAL_STATUSES)

    def test_exit_codes_and_marks(self):
        self.assertEqual(runcmd.EXIT_CODES["succeeded"], 0)
        self.assertEqual(runcmd.EXIT_CODES["failed"], 1)
        self.assertEqual(runcmd.EXIT_CODES["cancelled"], 1)   # 取消也是没成
        self.assertEqual(runcmd.EXIT_CODES["paused"], 4)      # 等人工输入，独立码
        for status in ("succeeded", "failed", "cancelled", "paused", "running", "queued"):
            self.assertIn(status, runcmd.MARKS)


if __name__ == "__main__":
    unittest.main()


class InputCoercionTest(unittest.TestCase):
    """命令行给的永远是字符串，按声明类型转成真实值。

    真机 60 个声明输入里 32 个 type=array —— 不转换的话这些工作流从
    `guanjia run` / cron 出口 100% 跑不通。
    """

    def test_array_and_object(self):
        self.assertEqual(workflow.coerce_input('[{"a":1}]', "array"), [{"a": 1}])
        self.assertEqual(workflow.coerce_input('{"k":"v"}', "object"), {"k": "v"})

    def test_numbers_and_bool(self):
        self.assertEqual(workflow.coerce_input("3.5", "number"), 3.5)
        self.assertEqual(workflow.coerce_input("7", "integer"), 7)
        self.assertIs(workflow.coerce_input("是", "boolean"), True)
        self.assertIs(workflow.coerce_input("no", "boolean"), False)

    def test_string_passthrough_and_unknown_type(self):
        self.assertEqual(workflow.coerce_input("abc", "string"), "abc")
        self.assertEqual(workflow.coerce_input("abc", None), "abc")
        self.assertEqual(workflow.coerce_input("abc", "什么类型"), "abc")

    def test_multiline_string_survives(self):
        """招牌 demo 的三行文本必须原样传过去，不能被截断。"""
        text = "第一行\n第二行\n第三行"
        self.assertEqual(workflow.coerce_input(text, "string"), text)

    def test_bad_values_raise_not_silently_drop(self):
        for raw, kind in [("不是JSON", "array"), ("abc", "number"), ("3.5", "integer")]:
            with self.assertRaises(workflow.InputTypeError):
                workflow.coerce_input(raw, kind)
