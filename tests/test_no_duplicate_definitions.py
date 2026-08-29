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
