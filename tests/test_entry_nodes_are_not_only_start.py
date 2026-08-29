"""工作流的入口节点有三种，不是只有 start。

平台自己的校验器认的是 {start, schedule_trigger, event_subscription_trigger}
（"workflow must contain exactly one start or schedule_trigger node"），
而且 schedule_trigger 有自己的 inputs 字段（界面上叫「定时输入」）。
平台前端也早就认 start 和 schedule_trigger 两种。**客户端这边只认 start。**

后果正是 runcmd 里那句注释想避免的：定时工作流拿到的是"没有输入"，
于是 guanjia run 既不提示、也不拦，直接发请求——服务端建一条在入口就失败的
运行记录，永久留在历史里，还让体检以为这个工作流坏了。
（真机上「文本行数与净字数统计」正因为缺必填输入失败了 13 次。）

真机核过：「服务器GPU日报」的入口就是 schedule_trigger、没有 start 节点。
它的定时输入恰好是空的，所以今天还没咬到人——但那是运气。

顺带分开第二件事：**"入口节点没有输入" 和 "根本找不到入口节点" 不一样**。
后者返回 [] 会让调用方以为"不用填任何东西"，照样把请求发出去。
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from guanjia.plugins import workflow


def _remote(nodes: list[dict]) -> Mock:
    remote = Mock()
    remote.request.return_value = {"snapshot": {"workflow": {"nodes": nodes}}}
    return remote


def _entry(kind: str, inputs: list[dict]) -> dict:
    return {"id": "n0", "type": kind, "config": {"inputs": inputs}}


FIELD = {"name": "text", "label": "文本", "type": "string", "required": True}


class EveryEntryTypeIsRead(unittest.TestCase):
    def test_each_entry_type_yields_its_inputs(self):
        for kind in ("start", "schedule_trigger", "event_subscription_trigger"):
            with self.subTest(kind=kind):
                schema = workflow.input_schema(_remote([_entry(kind, [FIELD])]), "a1")
                self.assertEqual([f["name"] for f in schema], ["text"], kind)
                self.assertTrue(schema[0]["required"])

    def test_a_scheduled_workflow_with_no_inputs_is_still_empty(self):
        """真机上那个定时工作流就是这样——空是对的，别把空报成读不懂。"""
        schema = workflow.input_schema(_remote([_entry("schedule_trigger", [])]), "a1")
        self.assertEqual(schema, [])

    def test_other_nodes_do_not_pretend_to_be_the_entry(self):
        """反向那一条：随便哪个节点都能当入口的话，读到的输入就是错的。"""
        with self.assertRaises(workflow.UnknownWorkflowShape):
            workflow.input_schema(
                _remote([{"id": "n1", "type": "llm",
                          "config": {"inputs": [FIELD]}}]), "a1")


class NoEntryNodeIsNotTheSameAsNoInputs(unittest.TestCase):
    def test_it_refuses_to_say_nothing_is_needed(self):
        """找不到入口就明说读不懂——返回 [] 等于替业主打包票"不用填"。"""
        with self.assertRaises(workflow.UnknownWorkflowShape) as caught:
            workflow.input_schema(_remote([{"id": "e", "type": "end"}]), "a1")
        message = str(caught.exception)
        self.assertIn("入口节点", message)
        self.assertIn("schedule_trigger", message, "要说清认得哪几种")

    def test_the_message_suggests_a_way_out(self):
        with self.assertRaises(workflow.UnknownWorkflowShape) as caught:
            workflow.input_schema(_remote([]), "a1")
        self.assertIn("升级 guanjia", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
