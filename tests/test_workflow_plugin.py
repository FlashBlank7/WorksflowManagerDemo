"""workflow 插件纯函数：事件时间线映射。"""

import unittest

from guanjia.plugins.workflow import _map_events


class MapEventsTest(unittest.TestCase):
    def test_duration_and_labels(self):
        rows = _map_events({"events": [
            {"id": 1, "type": "workflow.started",
             "at": "2026-08-27T06:31:06.796738+00:00", "data": {}},
            {"id": 2, "type": "node.started",
             "at": "2026-08-27T06:31:07.400000+00:00",
             "data": {"node_id": "fetch", "title": "取数"}},
            {"id": 3, "type": "node.completed",
             "at": "2026-08-27T06:31:09.900000+00:00",
             "data": {"node_id": "fetch", "title": "取数"}},
        ]})
        self.assertEqual([r["type"] for r in rows],
                         ["workflow.started", "node.started", "node.completed"])
        self.assertEqual(rows[0]["at"], "06:31:06")
        self.assertEqual(rows[1]["label"], "取数")
        self.assertEqual(rows[2]["extra"], "2.5s")

    def test_error_appended_and_truncated(self):
        rows = _map_events({"events": [
            {"id": 1, "type": "node.failed",
             "at": "2026-08-27T06:31:07+00:00",
             "data": {"node_id": "n1", "error": "x" * 500}},
        ]})
        self.assertEqual(rows[0]["label"], "n1")
        self.assertEqual(len(rows[0]["extra"]), 160)

    def test_empty_and_missing_fields(self):
        self.assertEqual(_map_events({}), [])
        rows = _map_events({"events": [{"id": 1, "type": "x", "at": "", "data": None}]})
        self.assertEqual(rows[0], {"at": "", "type": "x", "label": "x", "extra": ""})


if __name__ == "__main__":
    unittest.main()
