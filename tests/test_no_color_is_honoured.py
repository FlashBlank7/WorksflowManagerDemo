"""管道里、NO_COLOR 下，不许再吐色码。

真机 2026-08-30：`NO_COLOR=1 guanjia doctor | head` 照样吐
`\x1b[32m✓\x1b[0m`。色码在 contract / doctor / cli 三处各写各的
（96 个用点），而没有任何一处问过"现在该上色吗"。
对一个要给别人用的命令行工具这是硬伤：输出进不了 grep、进不了日志、
进不了 CI 的比对。NO_COLOR 是社区约定（no-color.org）。

**这条必须起子进程真跑**：色码常量是导入时算出来的，
在同一个进程里改完环境变量再导入已经晚了——那样测的是
"我以为的判据"，不是用户真跑出来的东西（这一周已经栽过一次）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ESC = "\x1b"


@pytest.fixture
def home():
    with tempfile.TemporaryDirectory() as made:
        yield Path(made)


def _run(args: list[str], home: Path, **env_extra) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "PYTHONPATH": str(ROOT),
        # 指向一个必然连不上的地址：这条测的是**上不上色**，
        # 不是能不能连上远端。连不上那条路照样会打色码。
        "GUANJIA_SERVER": "http://127.0.0.1:1",
        "GUANJIA_TOKEN": "t",
    })
    env.pop("NO_COLOR", None)
    env.pop("FORCE_COLOR", None)
    env.update(env_extra)
    return subprocess.run([sys.executable, "-m", "guanjia", *args],
                          capture_output=True, text=True, cwd=ROOT,
                          env=env, timeout=60)


class TestNoColorIsObeyed:
    def test_doctor_emits_no_escape_codes(self, home):
        done = _run(["doctor"], home, NO_COLOR="1")
        assert ESC not in done.stdout + done.stderr, repr(
            (done.stdout + done.stderr)[:200])

    def test_an_empty_no_color_still_counts(self, home):
        """约定是**只看设没设，不看值**。NO_COLOR= 也要算数。"""
        done = _run(["doctor"], home, NO_COLOR="")
        assert ESC not in done.stdout + done.stderr


class TestAPipeIsNotATerminal:
    def test_doctor_through_a_pipe_is_plain(self, home):
        """subprocess 的 stdout 就是管道——不设 NO_COLOR 也不该上色。

        这是当初真正踩到的形状：`guanjia doctor | head` 满屏 [32m。
        """
        done = _run(["doctor"], home)
        assert ESC not in done.stdout + done.stderr, repr(done.stdout[:200])

    def test_today_through_a_pipe_is_plain(self, home):
        done = _run(["today"], home)
        assert ESC not in done.stdout + done.stderr


class TestColourCanStillBeForced:
    def test_force_color_wins_over_the_pipe(self, home):
        """反向那一条：CI 里想留色的人要有出口。
        少了它，把 use_color 写成"永远返回 False"也能让上面全绿——
        那样终端里也没色了。"""
        done = _run(["doctor"], home, FORCE_COLOR="1")
        assert ESC in done.stdout + done.stderr

    def test_no_color_beats_force_color(self, home):
        """两个都设时 NO_COLOR 赢——约定如此。"""
        done = _run(["doctor"], home, NO_COLOR="1", FORCE_COLOR="1")
        assert ESC not in done.stdout + done.stderr


class TestTheDecisionItself:
    """判据本身也要正着测一遍——上面全是子进程，跑得慢、看不清是哪一条。"""

    def test_a_tty_gets_colour(self, monkeypatch):
        from guanjia.palette import use_color

        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)

        class _Tty:
            def isatty(self):
                return True

        assert use_color(_Tty()) is True

    def test_a_stream_that_raises_is_treated_as_no_colour(self, monkeypatch):
        """拿不准就不上色：多余的色码比少了更烦人。"""
        from guanjia.palette import use_color

        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)

        class _Broken:
            def isatty(self):
                raise OSError("closed")

        assert use_color(_Broken()) is False
