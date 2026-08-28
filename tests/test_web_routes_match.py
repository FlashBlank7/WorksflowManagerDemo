"""网页壳两边的路由要对得上。

app.js 调什么、app.py 就得提供什么。这两个文件谁改了名，
另一边不会报错——只会在浏览器里静默 404，那一块功能就白屏。
Python 测试碰不到 JS，所以用文本比对来守这条线。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "guanjia" / "web" / "app.js"
PY = ROOT / "guanjia" / "app.py"

# app.js 里形如 api('/api/xxx' 的调用。
# 路径引号闭合后的第一个非空字符决定方法：',' 说明带 body（POST），')' 说明不带（GET）。
# 别想用「括号里有没有逗号」判断——body 里的对象自带逗号和括号，正则会全判成 POST
# （第一版就是这么错的，报了 9 处全是假的）。
CALLED = re.compile(r"""api\(\s*['"`](/api/[a-zA-Z0-9/_-]+)""")
CALL_WITH_METHOD = re.compile(r"""api\(\s*(['"`])(/api/[a-zA-Z0-9/_-]+)\1\s*(.)""")
# app.py 里形如 "/api/xxx" 的字面量
SERVED = re.compile(r'"(/api/[a-zA-Z0-9/_-]+)"')


def _called() -> set[str]:
    return set(CALLED.findall(JS.read_text(encoding="utf-8")))


def _served() -> set[str]:
    return set(SERVED.findall(PY.read_text(encoding="utf-8")))


class WebRoutesMatchTest(unittest.TestCase):
    def test_every_route_the_page_calls_is_served(self):
        missing = sorted(_called() - _served())
        self.assertEqual(missing, [], f"app.js 调了 app.py 没有的路由：{missing}")

    def test_the_scan_actually_found_routes(self):
        """别让正则失效之后静默通过——那就成了摆设。"""
        self.assertGreater(len(_called()), 10, "从 app.js 里没扫到几个路由")
        self.assertGreater(len(_served()), 10, "从 app.py 里没扫到几个路由")

    def test_the_core_ones_are_present_on_both_sides(self):
        called, served = _called(), _served()
        for route in ("/api/chat", "/api/overview", "/api/workflow/run"):
            self.assertIn(route, called, route)
            self.assertIn(route, served, route)


def _called_with_methods() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = {}
    for _quote, path, nxt in CALL_WITH_METHOD.findall(JS.read_text(encoding="utf-8")):
        calls.setdefault(path, set()).add("POST" if nxt == "," else "GET")
    return calls


def _served_with_methods() -> dict[str, set[str]]:
    text = PY.read_text(encoding="utf-8")
    blocks = (("GET", text[text.index("def do_GET"):text.index("def do_POST")]),
              ("POST", text[text.index("def do_POST"):]))
    served: dict[str, set[str]] = {}
    for name, block in blocks:
        for path in SERVED.findall(block):
            served.setdefault(path, set()).add(name)
    return served


class WebRouteMethodsMatchTest(unittest.TestCase):
    """路径对得上还不够，方法也得对得上。

    这条的由来：只比路径的话，把 api('/x') 改成 api('/x', body) 而后端
    没加 POST 处理，测试拦不住——浏览器里就是个静默 404。
    """

    def test_no_method_mismatch(self):
        served = _served_with_methods()
        bad = []
        for path, methods in sorted(_called_with_methods().items()):
            have = served.get(path)
            if not have:
                continue          # 路径本身缺失由上面那条测试管
            missing = methods - have
            if missing:
                bad.append(f"{path}: 用 {sorted(methods)} 调，后端只处理 {sorted(have)}")
        self.assertEqual(bad, [], "调用方法与后端处理方法对不上：\n" + "\n".join(bad))

    def test_the_method_scan_found_both_kinds(self):
        """扫不到 GET 或扫不到 POST，多半是正则失效了——那这道门就是摆设。"""
        kinds = {m for methods in _called_with_methods().values() for m in methods}
        self.assertEqual(kinds, {"GET", "POST"}, f"只扫到 {kinds}")
