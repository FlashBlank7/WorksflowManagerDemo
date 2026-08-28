"""状态码是给机器看的，别印给人。

回归背景（2026-08-29 端到端实测）：服务端这一天把状态码从各条出口都堵掉了
（管家回答、业主页、动作行、报错文案），客户端这边还留着三处：

    ✓ 打招呼 · run run-0001 · succeeded          ← guanjia run
    ⏳ building · 修订 3                          ← REPL 跟踪构建
    构建结束（needs_attention：…）                ← REPL 构建收尾

--json 那条路照给原状态码——脚本按它判，那是机器的接口。
"""
import re
import unittest

from guanjia.cli import BUILD_WORDS
from guanjia.runcmd import EXIT_CODES, MARKS, WORDS

ENGLISH = re.compile(r"[A-Za-z]{3,}")


class RunStatusWordsTest(unittest.TestCase):
    def test_every_status_with_a_mark_has_a_chinese_word(self):
        missing = sorted(set(MARKS) - set(WORDS))
        self.assertEqual(missing, [], f"这些状态会原样印出去：{missing}")

    def test_every_exit_code_status_has_a_word_too(self):
        self.assertEqual(sorted(set(EXIT_CODES) - set(WORDS)), [])

    def test_no_word_is_english(self):
        leaked = [w for w in WORDS.values() if ENGLISH.search(w)]
        self.assertEqual(leaked, [], f"对照表里还有英文：{leaked}")

    def test_words_are_distinct(self):
        """全译成同一句话，用户看不出成没成。"""
        self.assertEqual(len(set(WORDS.values())), len(WORDS))

    def test_success_and_failure_do_not_read_alike(self):
        self.assertNotEqual(WORDS["succeeded"], WORDS["failed"])


class BuildStatusWordsTest(unittest.TestCase):
    def test_the_statuses_the_repl_branches_on_are_all_covered(self):
        """REPL 判终态用的那几个，一个都不能漏——漏了就印英文。"""
        for status in ("published", "ready", "needs_attention", "failed", "cancelled"):
            self.assertIn(status, BUILD_WORDS, status)

    def test_no_word_is_english(self):
        leaked = [w for w in BUILD_WORDS.values() if ENGLISH.search(w)]
        self.assertEqual(leaked, [], f"对照表里还有英文：{leaked}")

    def test_an_unknown_status_falls_back_to_chinese(self):
        self.assertNotIn("weird_state", BUILD_WORDS)
        self.assertEqual(BUILD_WORDS.get("weird_state", "进行中"), "进行中")


class SourceHasNoRawStatusPrintTest(unittest.TestCase):
    """给人看的那几行里不能再直接插 status。

    只查 print/say 里的插值，--json 那条路不算——机器接口该给原状态码。
    """

    def test_no_user_facing_line_interpolates_the_raw_status(self):
        from pathlib import Path

        import guanjia.cli as cli
        import guanjia.runcmd as runcmd

        for module in (cli, runcmd):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if not re.search(r"\b(print|say)\(", stripped):
                    continue
                if "json.dumps" in stripped:
                    continue
                self.assertNotRegex(
                    stripped, r"\{\s*(status|result)\['status'\]\s*\}",
                    f"{module.__name__}: {stripped[:80]}")


if __name__ == "__main__":
    unittest.main()


class WebShellStatusTest(unittest.TestCase):
    """网页壳是第三个面，同一条规矩。

    结果框原先直接印「状态 failed」。运行历史那边只有符号没有词，
    所以之前没人注意到这一处。
    """

    @staticmethod
    def _app_js() -> str:
        from pathlib import Path

        import guanjia

        return (Path(guanjia.__file__).parent / "web" / "app.js").read_text(
            encoding="utf-8")

    def test_the_result_box_uses_chinese_words(self):
        source = self._app_js()
        self.assertIn("RUN_WORDS", source)
        self.assertNotIn("状态 ${esc(r.status)}", source)

    def test_the_web_map_covers_the_same_statuses_as_the_cli(self):
        """两个面说同一件事，别一个有「取消了」另一个没有。"""
        import re

        source = self._app_js()
        match = re.search(r"const RUN_WORDS=\{(.+?)\};", source, re.S)
        self.assertIsNotNone(match, "找不到网页壳的状态对照表")
        web = set(re.findall(r"(\w+):", match.group(1)))
        self.assertEqual(web, set(WORDS), f"两边覆盖的状态不一致：{web ^ set(WORDS)}")

    def test_the_two_maps_agree_on_the_wording(self):
        """同一个状态在 CLI 和网页壳里不该有两种说法。"""
        import re

        match = re.search(r"const RUN_WORDS=\{(.+?)\};", self._app_js(), re.S)
        web = dict(re.findall(r"(\w+):'([^']+)'", match.group(1)))
        self.assertEqual(web, WORDS)
