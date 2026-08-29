""""等超时了"和"连不上"不是一回事，下一步也不同。

连不上：服务器不在（立刻 Connection refused）→ 去确认它启动了没有。
等超时：服务器**在**，只是不答 → 去看它是不是卡住了。
说成同一句"确认它启动了"，会把人支到错的方向——而这不是假想：
这个平台出过一次启动时全表扫描跑 90 分钟，那期间所有请求都是这样。

顺带一条：REPL 里那个客户端默认 120 秒（聊天要那么久）。
`/today`、`/wf` 这种"看一眼"的命令用同一个超时，后端卡住时
**整整两分钟一个字都不出**，看着像死了。信息类命令自己传短的。
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from guanjia.cli import LOOK_TIMEOUT
from guanjia.remote import (
    RemoteClient,
    RemoteError,
    RemoteTimeout,
    RemoteUnreachable,
    next_step,
)


@pytest.fixture
def hanging_server():
    """接了就不答——真的挂起，不是 mock 出来的。"""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    stop = threading.Event()

    held = []

    def serve():
        try:
            while not stop.is_set():
                conn, _ = srv.accept()
                # **要留住引用**：不留的话连接对象当场被回收、socket 关闭，
                # 客户端拿到的是 Connection reset 而不是超时——
                # 第一版就是这么写的，测出来的是"连不上"。
                held.append(conn)
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.getsockname()[1]}"
    stop.set()
    srv.close()


class TestTheTwoAreToldApart:
    def test_a_hang_is_a_timeout(self, hanging_server):
        client = RemoteClient(hanging_server, "t", timeout=0.5)
        with pytest.raises(RemoteTimeout):
            client.request("GET", "/api/v1/overview")

    def test_nobody_listening_is_still_unreachable(self):
        """反向那一条：真的连不上不能被算成超时。"""
        client = RemoteClient("http://127.0.0.1:1", "t", timeout=0.5)
        with pytest.raises(RemoteUnreachable) as caught:
            client.request("GET", "/x")
        assert not isinstance(caught.value, RemoteTimeout)

    def test_a_timeout_is_still_catchable_as_unreachable(self, hanging_server):
        """继承关系不能断：老的 except RemoteUnreachable 分支还得接得住。"""
        client = RemoteClient(hanging_server, "t", timeout=0.5)
        with pytest.raises(RemoteUnreachable):
            client.request("GET", "/x")


class TestTheAdviceDiffers:
    def test_a_timeout_does_not_say_go_check_it_started(self, hanging_server):
        step = next_step(RemoteTimeout(hanging_server, 15))
        assert "卡住" in step or "正忙" in step
        assert "确认它启动了" not in step

    def test_unreachable_still_says_check_it_started(self):
        step = next_step(RemoteUnreachable("http://x", "refused"))
        assert "启动" in step

    def test_the_message_says_how_long_it_waited(self):
        """"等了多久"是判断"是不是我超时设太短"的唯一线索。"""
        assert "15" in str(RemoteTimeout("http://x", 15))


class TestLookingAroundDoesNotUseTheChatTimeout:
    def test_the_look_timeout_is_short_enough_to_notice(self):
        """绝对值也钉一下：从常量推出来的断言在常量被改时照样绿。"""
        assert 3 <= LOOK_TIMEOUT <= 30, LOOK_TIMEOUT

    def test_it_is_shorter_than_the_client_default(self):
        default = RemoteClient("http://x", "t").timeout
        assert LOOK_TIMEOUT < default, (LOOK_TIMEOUT, default)

    def test_a_per_call_timeout_actually_applies(self, hanging_server):
        """按次传的超时要真的生效——不生效的话上面那条常量就是摆设。"""
        client = RemoteClient(hanging_server, "t", timeout=30.0)
        started = time.monotonic()
        with pytest.raises(RemoteError):
            client.request("GET", "/x", timeout=0.5)
        assert time.monotonic() - started < 5, "按次超时没生效，用了默认的 30 秒"


class TestBothShapesOfTimeoutAreRecognised:
    """超时有两种来法，只认一种就漏一半。

    裸的 TimeoutError 是一种；urllib 把 socket 超时包进 URLError.reason
    是另一种，而后者恰恰更常见。变异验证抓到的：把判断简化成
    `isinstance(error, TimeoutError)`，上面那些用真挂起服务器的用例
    **一条都不红**——因为那条路走的正好是裸的那种。
    """

    @staticmethod
    def _looks(error) -> bool:
        from guanjia.remote import _looks_like_timeout

        return _looks_like_timeout(error)

    def test_a_bare_timeout(self):
        assert self._looks(TimeoutError("timed out"))

    def test_one_wrapped_in_urlerror(self):
        import urllib.error

        assert self._looks(urllib.error.URLError(TimeoutError("timed out")))

    def test_one_whose_reason_only_says_so_in_text(self):
        """有些平台包的是字符串而不是异常对象。"""
        import urllib.error

        assert self._looks(urllib.error.URLError("The read operation timed out"))

    def test_a_refused_connection_is_not_a_timeout(self):
        """反向那一条：不然"认得宽"就成了"什么都算超时"。"""
        import urllib.error

        assert not self._looks(
            urllib.error.URLError(ConnectionRefusedError("Connection refused")))


class TestTheReplActuallyPassesTheShortTimeout:
    """光有常量没用——得真传下去。

    变异验证抓到的：把 `/today` 的 timeout=LOOK_TIMEOUT 去掉，
    488 条一条不红。常量在、没人用，是"看着像在把关"的另一种。
    """

    @staticmethod
    def _cli_source() -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent
                / "guanjia/cli.py").read_text(encoding="utf-8")

    def test_the_overview_call_passes_it(self):
        source = self._cli_source()
        assert '"/api/v1/overview", timeout=LOOK_TIMEOUT' in source

    def test_every_look_around_call_passes_it(self):
        """信息类的几个端点都要带上，别只改一个。

        按**调用**看而不是按行看：有的调用换行写，超时参数落在下一行，
        逐行判会把它当成漏掉的（第一版就是这么误报的）。
        """
        import re

        source = self._cli_source()
        for path in ("/api/v1/overview", "/api/v1/health-report",
                     "/api/v1/applications"):
            for call in re.findall(
                    r"remote\.request\([^)]*" + re.escape(f'"{path}"') + r"[^)]*\)",
                    source, re.S):
                assert "LOOK_TIMEOUT" in call, call
