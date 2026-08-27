"""sessions 本地会话存储：落盘、标题、过滤、排序、坏文件容错。"""

import json
import tempfile
import unittest
from pathlib import Path

from guanjia import sessions


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir = sessions.DIR
        sessions.DIR = Path(self.tmp.name)

    def tearDown(self):
        sessions.DIR = self.old_dir
        self.tmp.cleanup()

    def test_roundtrip_and_title(self):
        sid = sessions.new_session()
        sessions.save(sid, [
            {"role": "assistant", "text": "你好"},
            {"role": "user", "text": "帮我做一个每天八点的GPU报告工作流谢谢啦"},
        ])
        data = sessions.load(sid)
        self.assertEqual(data["id"], sid)
        self.assertEqual(data["title"], "帮我做一个每天八点的GPU报告工作流谢谢啦"[:24])
        self.assertEqual(len(data["messages"]), 2)

    def test_answerbox_filtered_and_capped(self):
        sid = sessions.new_session()
        msgs = [{"role": "user", "text": f"m{i}"} for i in range(210)]
        msgs.append({"kind": "answerbox", "build_id": "b1"})
        sessions.save(sid, msgs)
        data = sessions.load(sid)
        self.assertEqual(len(data["messages"]), 200)
        self.assertTrue(all(m.get("kind") != "answerbox" for m in data["messages"]))

    def test_load_missing_or_corrupt(self):
        self.assertIsNone(sessions.load("nope1234"))
        (sessions.DIR).mkdir(parents=True, exist_ok=True)
        (sessions.DIR / "bad1.json").write_text("{oops", encoding="utf-8")
        self.assertIsNone(sessions.load("bad1"))
        self.assertEqual(sessions.list_sessions(), [])  # 坏文件不进列表

    def test_list_order_and_latest(self):
        sessions.DIR.mkdir(parents=True, exist_ok=True)
        for sid, at in (("aaa11111", "2026-08-27 10:00"), ("bbb22222", "2026-08-27 10:05")):
            (sessions.DIR / f"{sid}.json").write_text(json.dumps({
                "id": sid, "title": sid, "updated_at": at, "messages": [],
            }), encoding="utf-8")
        items = sessions.list_sessions()
        self.assertEqual([i["id"] for i in items], ["bbb22222", "aaa11111"])
        self.assertEqual(sessions.latest_id(), "bbb22222")


if __name__ == "__main__":
    unittest.main()
