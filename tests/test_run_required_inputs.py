"""脚本里少给一个参数，不该换来一条永久的失败记录。

回归背景：交互补参只在 tty 且非 --json 时才跑。脚本、cron、--json
三种场景少给参数就直接发出去，服务端建一条运行记录、在 start 节点失败。
那条失败永久留在业主历史里，还会喂给体检与「近期失败」面板——
真机上排第一的失败原因就是这个。
"""
import io
import unittest
from contextlib import redirect_stderr
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
             redirect_stderr(err):
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
