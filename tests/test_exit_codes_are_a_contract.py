"""退出码是脚本和 cron 唯一读得懂的东西——它是对外承诺，不是实现细节。

README 里写着"退出码可判"，却从来没说过每个码是什么意思。
写 `if guanjia run 日报; then …` 的人需要知道：1 是没跑成、4 是停下等人填、
3 是这边不认识那个状态、2 是命令用法不对。

变异验证（2026-08-30，全量 664 条）：把「认不出的状态」那个兜底
从 3 改成 0——**不认识就当成功**——一条都没红。
平台的状态是会长的（health-report 里已经有 waiting 这一档），
哪天返回一个客户端没见过的词，cron 就会安静地当成跑成了。

这个文件同时钉住两件事：码本身，以及**文档里写的和代码里的一致**。
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guanjia import runcmd

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = [{"name": "text", "label": "文本", "type": "string",
           "example": "hi", "required": False}]


def _run_with_status(status: str) -> int:
    target = {"id": "a1", "name": "统计", "published": True}
    with patch.object(runcmd.workflow, "list_workflows", return_value=[target]), \
         patch.object(runcmd.workflow, "input_schema", return_value=SCHEMA), \
         patch.object(runcmd.workflow, "run",
                      return_value={"run_id": "r1", "status": status,
                                    "outputs": {}, "error": ""}), \
         patch.object(runcmd, "RemoteClient", MagicMock()), \
         patch.object(runcmd, "load_config",
                      return_value={"server": "s", "token": "t"}), \
         redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return runcmd.main(["统计", "--json"])


class TestTheDocumentedCodes:
    @pytest.mark.parametrize("status, code", [
        ("succeeded", 0),
        ("failed", 1),
        ("cancelled", 1),
        ("paused", 4),
    ])
    def test_each_status_maps_to_its_code(self, status, code):
        assert _run_with_status(status) == code

    def test_an_unknown_status_is_not_success(self):
        """**这条是漏网的那个。** 平台的状态会长（health-report 里已经有
        waiting 这一档）；哪天回一个客户端没见过的词，
        兜底要是 0，cron 就安静地当成跑成了。"""
        assert _run_with_status("某个还没见过的状态") == 3

    def test_the_unknown_code_is_distinct_from_the_known_ones(self):
        """3 不能和 0/1/4 撞——撞了就分不出"没跑成"和"我不认识"。"""
        assert 3 not in set(runcmd.EXIT_CODES.values())


class TestTheDocumentationMatchesTheCode:
    """文档写错比不写更糟：照着错的写脚本，错得很有信心。"""

    def _readme(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    @pytest.mark.parametrize("name", ["README.md", "README.en.md"])
    def test_every_code_is_documented(self, name):
        text = self._readme(name)
        for status, code in runcmd.EXIT_CODES.items():
            assert re.search(rf"^\s*\|?\s*{code}\b", text, re.M), (name, status, code)

    @pytest.mark.parametrize("name", ["README.md", "README.en.md"])
    def test_the_unknown_code_is_documented_too(self, name):
        assert re.search(r"^\s*\|?\s*3\b", self._readme(name), re.M), name

    @pytest.mark.parametrize("name", ["README.md", "README.en.md"])
    def test_the_usage_error_code_is_documented(self, name):
        """2 是"命令用法不对"（名字找不到、参数不是 k=v）——
        它和"跑了但没成"是两回事，脚本要分开处理。"""
        assert re.search(r"^\s*\|?\s*2\b", self._readme(name), re.M), name
