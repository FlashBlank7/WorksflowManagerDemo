"""每条命令都得在 --help 和两份 README 里出现。

2026-08-29 对了一遍才发现：`guanjia rerun` 在 `--help` 里有、
在**英文** README 里有，唯独中文 README 没有——而中文那份是主文档。
两份文档各写各的，迟早分家；分家之后没有任何东西会响，
只有读文档的人以为这个功能不存在。

（同一个形状今天已经修过好几处：冒烟的内部词清单、契约表、
  路由登记表、工具清单——手抄的东西都会漂。）
"""
import re
import unittest
from pathlib import Path

from guanjia.__main__ import HELP, KNOWN_COMMANDS

ROOT = Path(__file__).resolve().parent.parent
# help 本身就是命令，但它不需要在文档里单独占一行
NOT_DOCUMENTED = {"help"}
# 隐藏命令（补全用的内部入口）不对外
COMMANDS = sorted(KNOWN_COMMANDS - NOT_DOCUMENTED)


class DocsCoverCommandsTest(unittest.TestCase):
    def test_there_are_commands_to_check(self):
        """空列表会让下面几条永远绿——那是"检查存在但什么也没查"。"""
        self.assertGreater(len(COMMANDS), 5)

    def test_help_lists_every_command(self):
        missing = [c for c in COMMANDS if f"guanjia {c}" not in HELP]
        self.assertEqual(missing, [], f"--help 里没有这些命令：{missing}")

    def test_the_chinese_readme_lists_every_command(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        missing = [c for c in COMMANDS if not re.search(rf"guanjia {c}\b", text)]
        self.assertEqual(missing, [], f"README.md 里没有这些命令：{missing}")

    def test_the_english_readme_lists_every_command(self):
        path = ROOT / "README.en.md"
        if not path.exists():
            self.skipTest("没有英文 README")
        text = path.read_text(encoding="utf-8")
        missing = [c for c in COMMANDS if not re.search(rf"guanjia {c}\b", text)]
        self.assertEqual(missing, [], f"README.en.md 里没有这些命令：{missing}")

    def test_the_readmes_do_not_promise_commands_that_do_not_exist(self):
        """反向：文档里写了、实际没有的命令，比漏写更糟——用户会照着敲。"""
        for name in ("README.md", "README.en.md"):
            path = ROOT / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            # 只看**代码块里**的行首用法。散文里的 "guanjia is a thin client"
            # 也长这样，按行首匹配会把 "is" 当成命令——第一版就这么误报了。
            # 语言标记要通配。写死 (bash|sh|console) 的话，遇到 ```json、```text
            # 这种块，正则会从**收尾**的围栏开始配对，之后所有块整体错位——
            # 结果是散文被当成代码块（"guanjia is a thin client" → 命令 "is"），
            # 而真正的代码块反倒一个都没取到。第一版就是这么误报的。
            blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
            promised = {m.group(1) for block in blocks for m in
                        re.finditer(r"^guanjia ([a-z_]+)", block, re.M)}
            fake = sorted(promised - KNOWN_COMMANDS - {"help"})
            self.assertEqual(fake, [], f"{name} 写了不存在的命令：{fake}")


if __name__ == "__main__":
    unittest.main()


class KnownLimitsTracksTheVersionTest(unittest.TestCase):
    """「已知边界」自称对齐某个版本——那就得真的对得上。

    2026-08-29 一看：文档写着"对齐版本 0.6.1"，而 pyproject 已经 0.7.0，
    里面那条"网页壳只监听 127.0.0.1"也早就不准了（`--host` 能对外开，
    而且当天起回环也要访问密钥）。

    这份文档的整个价值就是"诚实"——它一旦落后，就从"已知边界"
    变成"过时的承诺"，比不写更坏。
    """

    def _limits(self) -> str:
        return (ROOT / "docs" / "known-limits.md").read_text(encoding="utf-8")

    def test_the_stated_version_is_the_real_one(self):
        from guanjia import __version__

        self.assertIn(__version__, self._limits(),
                      f"known-limits 没对齐到 {__version__}")

    def test_it_says_binding_can_be_opened_up(self):
        """别把回环说成唯一选项。

        原文是「`guanjia web` 只监听 127.0.0.1」——说得像绑定方式没得选，
        而 `--host` 一直能对外开。断言写成"不许出现某句话"太钝了
        （改成"**默认**只监听 127.0.0.1"之后那句话仍在，而它是对的）；
        要断的是**这份文档有没有把可以对外开这件事说出来**。
        """
        self.assertIn("--host", self._limits())

    def test_the_access_key_change_is_recorded(self):
        self.assertIn("访问密钥", self._limits())
