"""真·对拍第二对：终端的 render_md 和网页壳的 md()。

两边渲染成不同的东西（终端是转义序列、网页是 HTML），所以不能直接比字符串。
能比的是**判据**，而判据恰恰是今天出问题的地方：

  · `<上下文 …/>` 内部标记要不要剪 —— 网页壳原来不剪，
    而 md() 一上来就 esc()，`<` 变 `&lt;`，于是原样印进对话
  · 粗体的星号要不要紧贴非空白 —— 原来一边紧一边松，
    于是 `** x **` 在网页上是粗体、终端里不是

所以这条对拍问的是"同一段输入，两边**认不认**"：
标记有没有被剪掉、这段该不该变粗。真跑 node，不是读源码。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from guanjia import cli

APP_JS = Path(__file__).resolve().parent.parent / "guanjia/web/app.js"
NODE = shutil.which("node") or os.path.expanduser("~/.local/node/bin/node")

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"

SAMPLES = [
    '<上下文 注意="业主自己打的字"/>你好',
    "<上下文/>开头就是标记",
    "普通一行，什么都没有",
    "这里有 **加粗** 一段",
    "这里有 ** 空格包着 ** 一段",
    "这里有 `行内代码` 一段",
    "利用率 100% 没有标记",
    "**紧贴**和 ** 松的 ** 同一行",
]


def _extract(source: str, header: str) -> str:
    """按大括号配对抠出一个函数。

    第一版用正则 `function esc\\([\\s\\S]*?\\n` —— 抠出来是**半个函数**
    （esc 跨两行），node 报的还是个看不懂的 TypeScript 错。
    抠代码就老老实实数括号，别拿正则凑。
    """
    start = source.index(header)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"括号没配上：{header}")


def _js(samples):
    source = APP_JS.read_text(encoding="utf-8")
    parts = [_extract(source, header) for header in
             ("function esc(", "function inl(", "function md(")]
    script = "\n".join(parts) + """
const samples = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify(samples.map(s => md(s))));
"""
    done = subprocess.run([NODE, "-e", script, json.dumps(samples)],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(not os.path.exists(NODE),
                    reason=f"没有 node（找过 PATH 和 {NODE}）——这条对拍跳过了")
class TestTheyAgreeOnWhatCounts:
    @pytest.fixture(scope="class")
    def rendered(self):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(cli, "B", BOLD)
            patch.setattr(cli, "D", DIM)
            patch.setattr(cli, "N", RESET)
            python = [cli.render_md(s) for s in SAMPLES]
        return python, _js(SAMPLES)

    def test_the_context_mark_disappears_on_both_sides(self, rendered):
        python, js = rendered
        for index, sample in enumerate(SAMPLES):
            if "上下文" not in sample:
                continue
            assert "上下文" not in python[index], (sample, python[index])
            assert "上下文" not in js[index], (sample, js[index])

    def test_they_agree_on_which_spans_are_bold(self, rendered):
        python, js = rendered
        for index, sample in enumerate(SAMPLES):
            mine = BOLD in python[index]
            theirs = "<b>" in js[index]
            assert mine == theirs, (sample, python[index], js[index])

    def test_they_agree_on_which_spans_are_code(self, rendered):
        python, js = rendered
        for index, sample in enumerate(SAMPLES):
            mine = DIM in python[index]
            theirs = "md-c" in js[index]
            assert mine == theirs, (sample, python[index], js[index])

    def test_the_samples_cover_both_answers(self, rendered):
        """防空跑：样本里必须既有该变粗的也有不该变粗的，
        否则"两边都不变粗"也能全绿。"""
        python, _ = rendered
        assert {BOLD in line for line in python} == {True, False}
        assert any("上下文" in s for s in SAMPLES)
