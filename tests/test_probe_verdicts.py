"""`doctor --contract` 每一格判成什么，是有后果的。

变异验证（2026-08-30，全量 643 条）：`_probe` 里把 401/403 那一支
去掉——于是**有路由但没权限的接口被判成"缺失"**——一条测试都没红。

后果 contract.py 自己写着（在 _scheduler_health 的注释里）：
"用户照着这句去升级后端，白费半天工夫。诊断工具给错方向比不给方向更糟。"
判成缺失，实现方会去写一个已经存在的接口；判成 ok，才知道该去查权限。

四种判决各配正反，另加一条"四种判决互不相同"——
两种撞成一个词，等于少一种判决。
"""

from __future__ import annotations

import urllib.error

import pytest

from guanjia.contract import _probe
from guanjia.remote import RemoteError, RemoteUnreachable


class _Client:
    """按构造时给的结果作答。probe 只调 request 这一个方法。"""

    def __init__(self, *, payload=None, error=None):
        self._payload = payload
        self._error = error

    def request(self, method, path, *a, **k):
        if self._error is not None:
            raise self._error
        return self._payload


def _verdict(**kwargs) -> str:
    return _probe(_Client(**kwargs), "/api/v1/anything")[0]


class TestAPresentEndpoint:
    def test_a_good_payload_is_ok(self):
        assert _verdict(payload={"a": 1}) == "ok"

    def test_a_missing_field_is_a_shape_problem_not_a_missing_route(self):
        """路由在、形状不对——这两件事要分开说，修法完全不同。"""
        status, why = _probe(_Client(payload={}), "/x", required=("a",))
        assert status == "shape"
        assert "a" in why


class TestPermissionIsNotAbsence:
    """**这一族就是漏网的那个。**"""

    @pytest.mark.parametrize("code", [401, 403])
    def test_no_permission_still_counts_as_implemented(self, code):
        assert _verdict(error=RemoteError(code, "no")) == "ok"

    @pytest.mark.parametrize("code", [401, 403])
    def test_it_says_why_it_still_counted(self, code):
        """判成 ok 但不说清"是权限不足"，用户会以为这一格真的通了。"""
        _, why = _probe(_Client(error=RemoteError(code, "no")), "/x")
        assert str(code) in why
        assert "权限" in why

    @pytest.mark.parametrize("code", [401, 403])
    def test_it_is_not_reported_as_missing(self, code):
        """反过来钉一遍：判成 missing 会让实现方去写一个已经存在的接口。"""
        assert _verdict(error=RemoteError(code, "no")) != "missing"


class TestAbsence:
    @pytest.mark.parametrize("code", [404, 405])
    def test_not_found_is_missing(self, code):
        assert _verdict(error=RemoteError(code, "nope")) == "missing"

    @pytest.mark.parametrize("code", [500, 502])
    def test_a_server_error_is_not_missing(self, code):
        """500 不等于没实现——接口在，只是炸了。混为一谈会指错方向。"""
        assert _verdict(error=RemoteError(code, "boom")) == "error"


class TestUnreachable:
    def test_a_dead_remote_is_its_own_verdict(self):
        """「连不上」和「没这个接口」是两件事：一个查网络，一个改后端。"""
        assert _verdict(error=RemoteUnreachable("http://x", "refused")) == "unreachable"

    def test_a_url_error_is_also_unreachable(self):
        assert _verdict(error=urllib.error.URLError("boom")) == "unreachable"

    def test_a_timeout_is_also_unreachable(self):
        assert _verdict(error=TimeoutError("slow")) == "unreachable"


def test_the_four_verdicts_are_distinct():
    """两种判决撞成同一个词，等于少一种判决——而每一种的下一步都不同。"""
    got = {
        _verdict(payload={"a": 1}),
        _verdict(error=RemoteError(404, "")),
        _verdict(error=RemoteError(500, "")),
        _verdict(error=RemoteUnreachable("http://x", "refused")),
    }
    assert got == {"ok", "missing", "error", "unreachable"}, got
