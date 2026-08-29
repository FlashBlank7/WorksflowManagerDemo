"""脚本里少给一个参数，不该换来一条永久的失败记录。

回归背景：交互补参只在 tty 且非 --json 时才跑。脚本、cron、--json
三种场景少给参数就直接发出去，服务端建一条运行记录、在 start 节点失败。
那条失败永久留在业主历史里，还会喂给体检与「近期失败」面板——
真机上排第一的失败原因就是这个。
"""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

from guanjia import runcmd

SCHEMA = [
    {"name": "text", "label": "文本", "type": "string",
     "example": "第一行\n第二行", "required": True},
    {"name": "lang", "label": "语言", "type": "string",
     "example": "", "required": False},
]


class RequiredInputsTest(unittest.TestCase):
    def _run(self, pairs, schema=SCHEMA):
        target = {"id": "a1", "name": "统计", "published": True}
        err = io.StringIO()
        with patch.object(runcmd.workflow, "list_workflows", return_value=[target]), \
             patch.object(runcmd.workflow, "input_schema", return_value=schema), \
             patch.object(runcmd.workflow, "run",
                          return_value={"run_id": "r1", "status": "succeeded",
                                        "outputs": {}, "error": ""}) as run, \
             patch.object(runcmd, "RemoteClient", MagicMock()), \
             patch.object(runcmd, "load_config",
                          return_value={"server": "s", "token": "t"}), \
             redirect_stderr(err), redirect_stdout(io.StringIO()):
            # --json 的正常输出会糊在测试日志里，挡住真正该看的东西
            code = runcmd.main(["统计", *pairs, "--json"])
        return code, err.getvalue(), run

    def test_missing_required_input_never_reaches_the_server(self):
        code, text, run = self._run([])
        self.assertEqual(code, 2)
        run.assert_not_called()          # 关键：注定失败的运行根本没被创建
        self.assertIn("text", text)

    def test_the_message_can_be_copy_pasted(self):
        _, text, _ = self._run([])
        self.assertIn("guanjia run 统计 text=", text)

    def test_optional_input_alone_does_not_block(self):
        code, _, run = self._run(["text=hi"])
        self.assertEqual(code, 0)
        run.assert_called_once()

    def test_blank_value_counts_as_missing(self):
        code, _, run = self._run(["text=   "])
        self.assertEqual(code, 2)
        run.assert_not_called()

    def test_workflow_without_declared_inputs_is_not_blocked(self):
        # 取不到声明时宁可放行——误拦比漏拦更烦人
        code, _, run = self._run([], schema=[])
        self.assertEqual(code, 0)
        run.assert_called_once()

    def test_empty_name_says_what_to_type(self):
        """空名字会被当成「匹配所有」，原本报「有歧义，匹配到多个「」」。

        用户看了完全不知道自己做错了什么——他只是没打名字。
        """
        target = {"id": "a1", "name": "统计", "published": True}
        err = io.StringIO()
        with patch.object(runcmd.workflow, "list_workflows", return_value=[target]), \
             patch.object(runcmd.workflow, "run") as run, \
             patch.object(runcmd, "RemoteClient", MagicMock()), \
             patch.object(runcmd, "load_config",
                          return_value={"server": "s", "token": "t"}), \
             redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = runcmd.main(["   ", "--json"])
        text = err.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("要给出工作流名字", text)
        self.assertNotIn("有歧义", text)
        run.assert_not_called()


class SchemaFetchFailureIsSaidOutLoud(unittest.TestCase):
    """取不到类型表时也要说一声——原来这一支是光秃秃一个 pass。

    取不到 ⇒ **不转换**：声明成 array/object 的输入会被当字符串发出去
    （真机 60 个声明输入里 32 个是 array），服务端在下游某个节点炸开，
    报错完全指不到"你的参数没被转成数组"。
    照发是对的（不能凭猜测挡住一次正当调用），闷着不对——
    旁边 UnknownWorkflowShape 那一支一直是这么办的，这支漏了。
    """

    def _run(self, error):
        target = {"id": "a1", "name": "统计", "published": True}
        err = io.StringIO()
        with patch.object(runcmd.workflow, "list_workflows", return_value=[target]), \
             patch.object(runcmd.workflow, "input_schema", side_effect=error), \
             patch.object(runcmd.workflow, "run",
                          return_value={"run_id": "r1", "status": "succeeded",
                                        "outputs": {}, "error": ""}) as run, \
             patch.object(runcmd, "RemoteClient", MagicMock()), \
             patch.object(runcmd, "load_config",
                          return_value={"server": "s", "token": "t"}), \
             redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = runcmd.main(["统计", "items=[1,2]", "--json"])
        return code, err.getvalue(), run

    def test_it_says_something(self):
        code, text, run = self._run(runcmd.RemoteError(500, "boom"))
        self.assertIn("读不出这个工作流要填什么", text)

    def test_it_warns_that_arrays_may_not_go_through(self):
        """光说"读不出"不够——得说清这会导致什么，不然下游报错莫名其妙。"""
        _, text, _ = self._run(runcmd.RemoteError(500, "boom"))
        self.assertIn("数组", text)

    def test_it_still_sends_the_run(self):
        """不拦：我们并不知道它一定会失败，拦下来等于凭猜测挡住一次正当调用。"""
        _, _, run = self._run(runcmd.RemoteError(500, "boom"))
        run.assert_called_once()

    def test_the_unknown_shape_branch_still_speaks_too(self):
        """对照组：旁边那一支本来就会说话，别在改这支时把它碰坏。"""
        _, text, run = self._run(
            runcmd.workflow.UnknownWorkflowShape("认不出入口节点"))
        self.assertIn("读不出这个工作流要填什么", text)
        run.assert_called_once()
