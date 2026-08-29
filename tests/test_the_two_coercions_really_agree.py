"""真·对拍：把网页壳的 JS 抠出来跑一遍，逐个输入和 Python 比。

同名的那个文件（test_the_two_coercions_agree）钉的是**源码文本**——
"JS 里得有这条正则"。那是没有 node 时的将就办法，而它只能证明
代码长得对，证明不了跑起来一样。

这台机器上其实有 node（~/.local/node/bin，跑着的 next-server 用的就是它，
只是不在 PATH 上），所以这里直接把 coerceInput 抠出来真跑：
同一张输入表喂两边，结果必须一模一样。

这条差别不是学术的：2026-08-30 抓到的那个 bug——`Number('')` 是 0、
`Number.isInteger(0)` 为真，于是**必填的整数留空被填成 0 发出去**——
源码断言抓不到，对拍一跑就现形。

没有 node 时**跳过并说清楚**，不静默通过（"一个都没找到默认算成功"
是这个仓已经栽过的坑）。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from guanjia.plugins.workflow import InputTypeError, coerce_input

APP_JS = Path(__file__).resolve().parent.parent / "guanjia/web/app.js"
NODE = shutil.which("node") or os.path.expanduser("~/.local/node/bin/node")

# 两边都该这样判的输入。挑的是**差一点**的那些：
# 空串、带小数点、科学计数、十六进制、下划线、前后空格。
CASES = [
    ("42", "integer"), ("  7 ", "integer"), ("-3", "integer"), ("+3", "integer"),
    ("0", "integer"), ("1_000", "integer"),
    ("", "integer"), ("   ", "integer"), ("3.0", "integer"), ("1e3", "integer"),
    ("0x10", "integer"), ("abc", "integer"), ("3,000", "integer"),
    ("3.5", "number"), ("42", "number"), ("", "number"), ("abc", "number"),
    ("true", "boolean"), ("是", "boolean"), ("ON", "boolean"),
    ("false", "boolean"), ("", "boolean"), ("随便", "boolean"),
    ("[1, 2]", "array"), ("{\"a\": 1}", "object"), ("不是json", "array"),
    ("原样", "string"), ("原样", None),
]


def _python_side(raw, kind):
    try:
        return {"ok": True, "value": coerce_input(raw, kind)}
    except InputTypeError:
        return {"ok": False}


def _js_side(cases):
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(r"function coerceInput\(raw,type\)\{[\s\S]*?\n  return raw\}",
                      source)
    assert match, "从 app.js 里抠不出 coerceInput——函数签名改了？"
    script = match.group(0) + """
const cases = JSON.parse(process.argv[1]);
const out = cases.map(([raw, kind]) => {
  try { return {ok: true, value: coerceInput(raw, kind)} }
  catch (e) { return {ok: false} }
});
process.stdout.write(JSON.stringify(out));
"""
    done = subprocess.run([NODE, "-e", script, json.dumps(cases)],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(not os.path.exists(NODE),
                    reason=f"没有 node（找过 PATH 和 {NODE}）——这条对拍跳过了")
class TestTheyReallyAgree:
    def test_every_case_matches(self):
        js = _js_side(CASES)
        assert len(js) == len(CASES)
        mismatched = []
        for (raw, kind), theirs in zip(CASES, js):
            mine = _python_side(raw, kind)
            if mine["ok"] != theirs["ok"]:
                mismatched.append((raw, kind, mine, theirs))
            elif mine["ok"] and mine["value"] != theirs["value"]:
                mismatched.append((raw, kind, mine, theirs))
        assert not mismatched, mismatched

    def test_the_empty_integer_is_refused_on_both_sides(self):
        """单拎出来：这就是 2026-08-30 抓到的那个——网页壳把它填成 0 发出去，
        而紧接着的必填校验判的是空串，0 不是空串，于是放行。"""
        js = _js_side([("", "integer")])[0]
        assert js["ok"] is False
        assert _python_side("", "integer")["ok"] is False

    def test_the_case_table_covers_both_verdicts(self):
        """防空跑：表里必须既有该收的也有该拒的，
        不然"两边都拒"或"两边都收"也能让上面全绿。"""
        verdicts = {_python_side(raw, kind)["ok"] for raw, kind in CASES}
        assert verdicts == {True, False}
