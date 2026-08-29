"""网页壳上"谁起的这次运行"：空不等于定时。

原来是 `esc(r.by||'⏰ 定时')`——**只要平台没记来源，就贴"定时"的标签**。
而平台真机上没记来源的运行里混着管家代跑的（17 条）和测试跑的（265 条），
那些全被说成了定时。**把"不知道"说成一个具体答案**。

平台侧已经让调度器显式记 "schedule" / "schedule_manual"；
这边照着翻，翻不出来就如实说"来源没记"。

JS 没有单元测试框架（零依赖是这个项目的卖点），所以这里用
Python 把那个函数抠出来跑——测的是真的那几行，不是抄一份。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "guanjia/web/app.js"


def _node() -> str:
    for candidate in ("node", str(Path.home() / ".local/node/bin/node")):
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            return candidate
        except (OSError, subprocess.CalledProcessError):
            continue
    return ""


def _by_label(value) -> str:
    """把 app.js 里的 byLabel 抠出来，用 node 跑一遍。"""
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(r"function byLabel\(by\)\{.*?\n\}", source, re.S)
    assert match, "app.js 里找不到 byLabel——函数改名了就得改这里"
    node = _node()
    if not node:
        pytest.skip("本机没有 node")
    script = match.group(0) + f"\nconsole.log(byLabel({value!r}))"
    done = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_an_empty_source_is_not_called_scheduled():
    """整件事就是这一条。"""
    assert _by_label("") == "来源没记"


def test_whitespace_counts_as_empty():
    assert _by_label("   ") == "来源没记"


def test_a_scheduled_run_is_labelled():
    assert "定时" in _by_label("schedule")


def test_a_manual_catch_up_is_distinguished():
    """手动补跑和按点开火不是一回事，别混成一个标签。"""
    manual = _by_label("schedule_manual")
    assert "手动" in manual and manual != _by_label("schedule")


def test_a_person_shows_through():
    """其余是用户名，原样显示——别把人名也翻了。"""
    assert _by_label("zhaoyang") == "zhaoyang"


def test_the_old_guess_is_gone():
    """源码里不该再有"空就当定时"那种写法。

    只看代码行，不看注释——注释里正引用着那句老写法当反面教材，
    连注释一起搜的话这条会被自己的说明文字绊倒（第一版就是）。
    """
    lines = [line for line in APP_JS.read_text(encoding="utf-8").splitlines()
             if not line.lstrip().startswith("//")]
    code = "\n".join(lines)
    assert "r.by||'⏰ 定时'" not in code
    assert "byLabel(r.by)" in code
