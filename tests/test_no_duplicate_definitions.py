"""同一个文件里不许把同一个名字定义两遍。

**重复的测试比重复的生产代码更坏**：同名的第二个 def 会把第一个顶掉，
第一份一次都不跑，而它在文件里看着就是有覆盖的。
平台那边（Lilies）扫出过三处重复的测试函数、一处生产函数定义了四遍。
客户端当下是干净的——这条测试是为了让它保持干净。

ruff 的 F 类不管这个：F811 只在"重定义之前那个名字被用过"时才报，
"定义完紧接着再定义一遍"的形状它不出声（实测平台那个文件当时 lint 全绿）。

函数**内部**的嵌套重定义不扫：那有正当用法。
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULES = sorted(
    [p for p in (ROOT / "guanjia").rglob("*.py")]
    + [p for p in (ROOT / "tests").rglob("*.py")]
    + [p for p in (ROOT / "scripts").rglob("*.py")]
    + [p for p in (ROOT / "examples").rglob("*.py")]
)


def test_there_are_modules_to_check():
    """先钉住有东西可扫——空列表会让下面两条一路全绿却什么都没查。"""
    assert len(MODULES) > 40, len(MODULES)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_name_is_defined_twice_at_module_level(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tops = [n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    repeated = {name: n for name, n in Counter(x.name for x in tops).items() if n > 1}
    assert not repeated, f"{path.name} 里重复定义：{repeated}"


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_method_is_defined_twice_in_a_class(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = [n.name for n in node.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        repeated = {name: n for name, n in Counter(methods).items() if n > 1}
        assert not repeated, f"{path.name}::{node.name} 里重复定义：{repeated}"


# —— 平台那侧今天挖出的第三种形状：**成组**被复制 ——
#
# 2026-08-30 在平台的 builder.py 抓到：反刍守卫那四句连着写了三遍，
# 三遍在同一个 except 里顺序跑。后果不是死代码，是**算错**——
# 一次被拒计数加 3，模型第一次被拒就被告知"这是第 3 次"。
#
# 先写的那条"相邻两句一模一样"抓不到它：重复的是四句一组，
# 组与组之间隔着那个 if，任何两条**相邻**语句都不相同。
# 客户端这边扫过是干净的（0 处），这条是防着以后。
#
# 门槛 3 句：两句一组的重复偶尔正当（连发两次同样的事件测去重，
# 平台那边就有一处），三句一字不差地紧挨着出现基本只可能是复制粘贴。
GROUP_MIN = 3


def _statement_blocks(tree: ast.AST):
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and len(block) > 1:
                yield block


def _repeated_group(block: list):
    dumped = [ast.dump(stmt) for stmt in block]
    for size in range(GROUP_MIN, len(dumped) // 2 + 1):
        for start in range(len(dumped) - 2 * size + 1):
            if dumped[start:start + size] == dumped[start + size:start + 2 * size]:
                return block[start].lineno, block[start + size].lineno
    return None


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_group_of_statements_is_copy_pasted(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for block in _statement_blocks(tree):
        repeat = _repeated_group(block)
        if repeat:
            found.append(f"第 {repeat[0]} 行起的一组，在第 {repeat[1]} 行又来了一遍")
    assert not found, f"{path.name}：{found}"


def test_the_group_check_can_see_a_real_one():
    """扫描器自己得抓得住——它对每个文件都断言"没有"，写坏成永远返回 None 就全绿。"""
    body = "\n".join(["def f(x):"] + ["    a = 1", "    b = 2", "    c = 3"] * 2)
    assert any(_repeated_group(block)
               for block in _statement_blocks(ast.parse(body)))


def test_the_group_check_does_not_flag_two_line_repeats():
    body = ("async def f(s, e):\n    await s.send(e)\n    await s.wait()\n"
            "    await s.send(e)\n    await s.wait()\n")
    assert not any(_repeated_group(block)
                   for block in _statement_blocks(ast.parse(body)))
