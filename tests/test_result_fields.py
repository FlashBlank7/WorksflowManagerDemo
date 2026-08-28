"""运行结果字段来源：顶层 outputs/error 优先，状态集覆盖全。

真机缺陷（2026-08-28）：平台的 WorkflowRunState 模型根本没有 error 字段，
客户端却只读 state.error —— `guanjia run` 失败时显示"错误：None"，无法诊断；
outputs 读 state 里逐节点拍平的中间态，展示出来是某个中间节点的 payload。
"""

import os
import unittest

from guanjia.plugins import workflow
from guanjia import runcmd


class ResultFieldsTest(unittest.TestCase):
    def test_error_prefers_top_level(self):
        run = {"status": "failed",
               "error": "node start failed: missing required input: sales",
               "state": {"inputs": {}}}          # state 里没有 error —— 真实形状
        self.assertIn("missing required input", workflow._result_error(run))

    def test_error_falls_back_to_state(self):
        run = {"status": "failed", "error": None, "state": {"error": "老远端写这里"}}
        self.assertEqual(workflow._result_error(run), "老远端写这里")

    def test_error_empty_when_absent(self):
        self.assertEqual(workflow._result_error({"status": "succeeded"}), "")

    def test_outputs_prefer_top_level(self):
        run = {"outputs": {"report": "业务结果"},
               "state": {"outputs": {"mid": {"payload": "中间态"}}}}
        self.assertEqual(workflow._result_outputs(run), {"report": "业务结果"})

    def test_outputs_fall_back_to_flattened_state(self):
        run = {"outputs": {}, "state": {"outputs": {
            "n1": {"a": 1}, "n2": {"b": 2}}}}
        self.assertEqual(workflow._result_outputs(run), {"a": 1, "b": 2})

    def test_flatten_keeps_conflicting_keys(self):
        """同名键不再静默覆盖——冲突的那个带上节点名。"""
        run = {"state": {"outputs": {"n1": {"x": 1}, "n2": {"x": 2}}}}
        flat = workflow._result_outputs(run)
        self.assertEqual(flat["x"], 1)
        self.assertEqual(flat["n2.x"], 2)

    def test_terminal_statuses_cover_paused_and_cancelled(self):
        self.assertIn("paused", workflow.TERMINAL_STATUSES)
        self.assertIn("cancelled", workflow.TERMINAL_STATUSES)

    def test_exit_codes_and_marks(self):
        self.assertEqual(runcmd.EXIT_CODES["succeeded"], 0)
        self.assertEqual(runcmd.EXIT_CODES["failed"], 1)
        self.assertEqual(runcmd.EXIT_CODES["cancelled"], 1)   # 取消也是没成
        self.assertEqual(runcmd.EXIT_CODES["paused"], 4)      # 等人工输入，独立码
        for status in ("succeeded", "failed", "cancelled", "paused", "running", "queued"):
            self.assertIn(status, runcmd.MARKS)


if __name__ == "__main__":
    unittest.main()


class InputCoercionTest(unittest.TestCase):
    """命令行给的永远是字符串，按声明类型转成真实值。

    真机 60 个声明输入里 32 个 type=array —— 不转换的话这些工作流从
    `guanjia run` / cron 出口 100% 跑不通。
    """

    def test_array_and_object(self):
        self.assertEqual(workflow.coerce_input('[{"a":1}]', "array"), [{"a": 1}])
        self.assertEqual(workflow.coerce_input('{"k":"v"}', "object"), {"k": "v"})

    def test_numbers_and_bool(self):
        self.assertEqual(workflow.coerce_input("3.5", "number"), 3.5)
        self.assertEqual(workflow.coerce_input("7", "integer"), 7)
        self.assertIs(workflow.coerce_input("是", "boolean"), True)
        self.assertIs(workflow.coerce_input("no", "boolean"), False)

    def test_string_passthrough_and_unknown_type(self):
        self.assertEqual(workflow.coerce_input("abc", "string"), "abc")
        self.assertEqual(workflow.coerce_input("abc", None), "abc")
        self.assertEqual(workflow.coerce_input("abc", "什么类型"), "abc")

    def test_multiline_string_survives(self):
        """招牌 demo 的三行文本必须原样传过去，不能被截断。"""
        text = "第一行\n第二行\n第三行"
        self.assertEqual(workflow.coerce_input(text, "string"), text)

    def test_bad_values_raise_not_silently_drop(self):
        for raw, kind in [("不是JSON", "array"), ("abc", "number"), ("3.5", "integer")]:
            with self.assertRaises(workflow.InputTypeError):
                workflow.coerce_input(raw, kind)


class ColdPathGuardTest(unittest.TestCase):
    """冷路径审计（2026-08-28）确认过的几条，锁住别回去。"""

    def test_import_rejects_non_dict_payload(self):
        """典型来源：export -o - | jq '.snapshot.workflow.nodes' | import -"""
        for payload in ([], None, "hi", 123):
            with self.assertRaises(ValueError) as caught:
                workflow.import_snapshot(None, payload)      # 校验在任何网络请求之前
            self.assertIn("顶层应该是一个对象", str(caught.exception))

    def test_save_returns_false_instead_of_raising(self):
        """HOME 只读时，招牌 REPL 不该在答完之后崩掉并把整段对话带走。"""
        import tempfile
        from pathlib import Path as _Path

        from guanjia import sessions

        old = sessions.DIR
        tmp = tempfile.mkdtemp()
        try:
            os.chmod(tmp, 0o555)
            sessions.DIR = _Path(tmp) / "sessions"
            self.assertIs(sessions.save("s1", [{"role": "user", "text": "你好"}]), False)
        finally:
            os.chmod(tmp, 0o755)
            sessions.DIR = old

    def test_save_returns_true_when_writable(self):
        import tempfile
        from pathlib import Path as _Path

        from guanjia import sessions

        old = sessions.DIR
        with tempfile.TemporaryDirectory() as tmp:
            sessions.DIR = _Path(tmp) / "sessions"
            try:
                self.assertIs(sessions.save("s1", [{"role": "user", "text": "你好"}]), True)
                self.assertEqual(sessions.load("s1")["messages"][0]["text"], "你好")
            finally:
                sessions.DIR = old

    def test_wait_for_is_shared_by_run_and_follow(self):
        """--follow 直播不通时要落回这个等待函数，而不是把已建好的 run 丢半路。"""
        self.assertTrue(callable(workflow.wait_for))
        from guanjia import runcmd as rc

        source = __import__("inspect").getsource(rc._follow)
        self.assertIn("workflow.wait_for", source)
        self.assertIn("except (RemoteError, OSError)", source)


class FirstRunTest(unittest.TestCase):
    """全新用户：不能一上来就问「服务器地址」——他还不知道这工具要连什么。"""

    def test_guide_explains_before_asking(self):
        import contextlib
        import io
        from unittest import mock

        from guanjia import cli

        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("builtins.input", return_value="n"):
            proceed = cli.first_run_guide("http://127.0.0.1:8000")
        text = out.getvalue()
        self.assertFalse(proceed)
        self.assertIn("它需要一个后端", text)
        self.assertIn("注册令牌", text)          # 告诉他要问同事要什么
        self.assertIn("guanjia --login", text)   # 给出之后怎么回来

    def test_guide_accepts_empty_enter_as_yes(self):
        import contextlib
        import io
        from unittest import mock

        from guanjia import cli

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch("builtins.input", return_value=""):
            self.assertTrue(cli.first_run_guide("http://x"))

    def test_guide_survives_ctrl_c(self):
        import contextlib
        import io
        from unittest import mock

        from guanjia import cli

        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(cli.first_run_guide("http://x"))

    def test_readme_has_the_section_the_guide_points_at(self):
        """引导说「见项目主页的后端一节」——那一节必须真的存在，否则是空指路。"""
        from pathlib import Path as _P

        zh = _P("README.md").read_text(encoding="utf-8")
        en = _P("README.en.md").read_text(encoding="utf-8")
        self.assertIn("## 后端：它连的是什么", zh)
        self.assertIn("注册令牌", zh)
        self.assertIn("## The backend it talks to", en)


class DocsLinkTest(unittest.TestCase):
    """文档里的相对链接必须指向真实存在的文件。

    最容易悄悄烂掉的东西：挪个文件、改个名，链接就死了而没人发现。
    此前跨仓引用 ../Lilies/... 在仓库独立发布后会全部失效，
    整理 docs 结构时又一次性造出 3 条死链——所以固化成测试。
    """

    def test_no_broken_relative_links(self):
        import re
        from pathlib import Path as _P

        root = _P(__file__).resolve().parent.parent
        docs = list(root.glob("*.md")) + list((root / "docs").rglob("*.md"))
        broken = []
        for md in docs:
            for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)",
                                            md.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                if not (md.parent / target.split("#")[0]).resolve().exists():
                    broken.append(f"{md.relative_to(root)}: [{label}]({target})")
        self.assertEqual(broken, [], f"死链：{broken}")
        self.assertGreater(len(docs), 5, "文档没扫到，检查本身失效了")

    def test_no_cross_repo_references(self):
        """引用另一个仓库的路径，发布后必然是死链。"""
        from pathlib import Path as _P

        root = _P(__file__).resolve().parent.parent
        offenders = [
            str(md.relative_to(root))
            for md in list(root.glob("*.md")) + list((root / "docs").rglob("*.md"))
            if "../Lilies" in md.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


class RepoHygieneTest(unittest.TestCase):
    """开源仓库的基本件：存在、内容真实、别指向不存在的东西。"""

    def _root(self):
        from pathlib import Path as _P
        return _P(__file__).resolve().parent.parent

    def test_license_is_real(self):
        text = (self._root() / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Copyright", text)
        self.assertIn("WITHOUT WARRANTY", text.upper())

    def test_security_describes_the_actual_model(self):
        """安全说明要写这个工具真实的取舍，不是套话。"""
        text = (self._root() / "SECURITY.md").read_text(encoding="utf-8")
        for topic in ("会话令牌", "网页壳没有登录", "SSH 端口转发", "@"):
            self.assertIn(topic, text, f"SECURITY.md 少了 {topic}")

    def test_issue_templates_are_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("没装 pyyaml")
        for path in (self._root() / ".github/ISSUE_TEMPLATE").glob("*.yml"):
            with self.subTest(template=path.name):
                yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_bug_template_asks_for_doctor_output(self):
        """不问 doctor 输出的 bug 模板等于每个 issue 都要来回三轮。"""
        text = (self._root() / ".github/ISSUE_TEMPLATE/bug.yml").read_text(encoding="utf-8")
        self.assertIn("guanjia doctor", text)
        self.assertIn("required: true", text)

    def test_template_links_point_at_files_that_exist(self):
        """模板里写死了仓库内路径，文件挪了就是死链。"""
        import re
        from pathlib import Path as _P

        root = self._root()
        for path in (root / ".github/ISSUE_TEMPLATE").glob("*.yml"):
            for target in re.findall(r"blob/main/([\w./-]+)", path.read_text(encoding="utf-8")):
                with self.subTest(template=path.name, target=target):
                    self.assertTrue((root / target).exists(), f"{target} 不存在")
