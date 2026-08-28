"""导出再导入必须真的能搬过去，失败也不能留下空壳。

回归背景（2026-08-28 真机）：
1) 建壳时已经把 description/requirement 写进去了，紧接着又原样 set_metadata
   一次——空操作，远端 422「draft operation would not change the workflow」。
   export→import 这条「把工作流分享给别人」的路整条不通。
2) 壳是先建的：那次失败在列表里留下一具同名空壳，
   下次按名字找就成了「有歧义，匹配到多个」。
"""
import unittest
from unittest.mock import MagicMock

from guanjia.plugins import workflow

SNAP = {
    "name": "统计",
    "description": "输入 text，输出 line_count",
    "requirement": "输入一段文本，输出行数",
    "workflow": {"nodes": [{"id": "s", "type": "start"}], "edges": []},
    "agents": {},
    "tests": [],
}


class _Remote:
    """记下每一次请求，并允许让某个 op 抛错。"""

    def __init__(self, fail_op=None):
        self.calls = []
        self.fail_op = fail_op
        self.revision = 0

    def request(self, method, path, body=None):
        self.calls.append((method, path, body or {}))
        if path == "/api/v1/applications" and method == "POST":
            return {"id": "app-1"}
        if path.endswith("/draft") and method == "GET":
            return {"revision": 0}
        if path.endswith("/draft") and method == "POST":
            if body.get("op") == self.fail_op:
                raise RuntimeError("remote 422: would not change the workflow")
            self.revision += 1
            return {"revision": self.revision}
        return {}

    def ops(self):
        return [b.get("op") for m, p, b in self.calls
                if p.endswith("/draft") and m == "POST"]


class ImportRoundTripTest(unittest.TestCase):
    def test_metadata_already_set_at_creation_is_not_resent(self):
        remote = _Remote()
        workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        # set_metadata 会是空操作，远端拒绝，整个导入就断了
        self.assertNotIn("set_metadata", remote.ops())
        self.assertIn("replace_workflow", remote.ops())

    def test_agents_and_tests_still_go_through(self):
        """元数据那步挪进 try 之后，后面几步不能被顺手漏掉。"""
        remote = _Remote()
        snap = dict(SNAP,
                    agents={"a": {"id": "a"}},
                    tests=[{"id": "t1", "mandatory": True}])
        workflow.import_snapshot(remote, {"snapshot": snap}, publish=False)
        self.assertEqual(remote.ops(),
                         ["upsert_agent", "replace_workflow", "replace_tests"])

    def test_failure_archives_the_shell_it_created(self):
        remote = _Remote(fail_op="replace_workflow")
        with self.assertRaises(RuntimeError):
            workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        archived = [(p, b) for m, p, b in remote.calls if p.endswith("/archive")]
        self.assertEqual(len(archived), 1, "失败的导入在列表里留下了空壳")
        self.assertTrue(archived[0][1]["archived"])

    def test_the_exception_says_whether_cleanup_worked(self):
        # 调用方要能如实告诉用户「留下的东西清没清掉」
        remote = _Remote(fail_op="replace_workflow")
        with self.assertRaises(RuntimeError) as caught:
            workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        self.assertIs(caught.exception.guanjia_import_cleaned, True)
        self.assertEqual(caught.exception.guanjia_import_app_id, "app-1")

    def test_failed_cleanup_is_reported_as_such(self):
        class NoArchive(_Remote):
            def request(self, method, path, body=None):
                if path.endswith("/archive"):
                    raise RuntimeError("remote 404")
                return super().request(method, path, body)

        remote = NoArchive(fail_op="replace_workflow")
        with self.assertRaises(RuntimeError) as caught:
            workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        self.assertIs(caught.exception.guanjia_import_cleaned, False)

    def test_success_does_not_archive_anything(self):
        remote = _Remote()
        workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        self.assertFalse([p for m, p, b in remote.calls if p.endswith("/archive")])

    def test_old_backend_without_archive_still_reports_the_real_error(self):
        class NoArchive(_Remote):
            def request(self, method, path, body=None):
                if path.endswith("/archive"):
                    raise RuntimeError("remote 404")
                return super().request(method, path, body)

        remote = NoArchive(fail_op="replace_workflow")
        with self.assertRaises(RuntimeError) as caught:
            workflow.import_snapshot(remote, {"snapshot": SNAP}, publish=False)
        # 收不掉壳不能把真正的失败原因盖掉
        self.assertIn("would not change", str(caught.exception))
