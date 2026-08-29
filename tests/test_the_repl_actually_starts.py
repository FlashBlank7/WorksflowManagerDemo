"""招牌那条路（REPL）此前没有任何端到端测试。

cli.py 441 行，是这个项目的招牌——用户敲 `guanjia` 进来的就是它。
而 tests 里没有一条真的把它启动起来过：改动它只能靠肉眼看
（2026-08-29 我把 `/today` 换成共享渲染器时，就是手动跑了一遍才敢信）。

这里把它当**真程序**跑：子进程、真 stdin、一个真 HTTP 桩后端。
测的是用户进来头十秒会碰到的东西——起得来、认得出命令、
渲染成形、退得干净、后端出问题时不甩 traceback。

不测对话内容：那要真模型。这条线专门守"壳"。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class StubApi(BaseHTTPRequestHandler):
    """只答 REPL 开场会问的那几个端点。"""

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._json(200, {"ok": True})
        elif path == "/api/v1/me":
            self._json(200, {"user": {"name": "管理员", "role": "admin"}})
        elif path == "/api/v1/overview":
            self._json(200, {
                "date_utc": "2026-08-29",
                "runs_today": {"total": 2, "succeeded": 2, "failed": 0, "running": 0},
                "published_workflows": 1,
                "builds_active": 0,
                "week": [{"date": "2026-08-29", "ok": 2, "fail": 0, "other": 0}],
                "schedules": [{"workflow": "日报", "at": "08:00",
                               "timezone": "Asia/Shanghai",
                               "last_fire_date": "2026-08-29"}],
                "recent_failures": [],
                "recent_failures_total": 0,
            })
        elif path == "/api/v1/health-report":
            self._json(200, {"days": 7, "counts": {"ok": 1},
                             "items": [], "never_ran": []})
        elif path == "/api/v1/applications":
            self._json(200, [{"id": "a1", "name": "日报", "active_version": 1}])
        else:
            self._json(404, {"detail": "nope"})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def backend():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def _run_repl(backend: str, typed: str, *, home: Path,
              timeout: float = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "GUANJIA_SERVER": backend,
        "GUANJIA_TOKEN": "t",
        "HOME": str(home),           # 别碰真实档案和会话
        "PYTHONPATH": str(ROOT),
        "NO_COLOR": "1",
    })
    return subprocess.run([sys.executable, "-m", "guanjia"], input=typed,
                          capture_output=True, text=True, cwd=ROOT,
                          env=env, timeout=timeout)


@pytest.fixture
def home():
    with tempfile.TemporaryDirectory() as made:
        yield Path(made)


class TestItStartsAndStops:
    def test_it_greets_and_exits_cleanly(self, backend, home):
        done = _run_repl(backend, "/quit\n", home=home)
        assert done.returncode == 0, done.stderr
        assert "管家" in done.stdout, done.stdout

    def test_end_of_input_is_not_a_crash(self, backend, home):
        """管道喂完就关——不能因此吐 traceback。"""
        done = _run_repl(backend, "", home=home)
        assert "Traceback" not in done.stderr, done.stderr

    def test_no_traceback_ever_reaches_the_user(self, backend, home):
        done = _run_repl(backend, "/today\n/wf\n/quit\n", home=home)
        assert "Traceback" not in done.stdout + done.stderr


class TestTheCommandsRender:
    def test_today_shows_the_week_chart(self, backend, home):
        """`/today` 少了趋势条正是 2026-08-29 修的那个——钉住它。"""
        done = _run_repl(backend, "/today\n/quit\n", home=home)
        assert "今日运行 2" in done.stdout, done.stdout
        assert "近7日" in done.stdout, done.stdout

    def test_today_shows_when_the_schedule_last_fired(self, backend, home):
        done = _run_repl(backend, "/today\n/quit\n", home=home)
        assert "最近触发 2026-08-29" in done.stdout, done.stdout

    def test_help_lists_the_commands(self, backend, home):
        done = _run_repl(backend, "/help\n/quit\n", home=home)
        assert "/today" in done.stdout and "/quit" in done.stdout

    def test_an_unknown_slash_command_is_not_swallowed(self, backend, home):
        """乱敲一个 /xxx 不能既不报错也不回应——那样用户不知道发生了什么。"""
        done = _run_repl(backend, "/nonsense-command\n/quit\n", home=home)
        assert done.returncode == 0
        assert done.stdout.strip(), "一个字都没回"


class TestABrokenBackendDoesNotBreakTheShell:
    def test_a_dead_backend_is_said_plainly_and_it_exits(self, home):
        """后端不在时它**不进壳**，直接说清楚再退——这是对的。

        我原来断言"壳也得能进"，那是我的偏好不是缺陷：
        REPL 的全部用处就是跟平台说话，后端不在时把人放进一个
        敲什么都失败的壳里更糟。所以这条改成钉真实行为：
        话说清楚、给下一步、退出码非零、**不甩 traceback**。
        """
        done = _run_repl("http://127.0.0.1:1", "/quit\n", home=home)
        assert "Traceback" not in done.stdout + done.stderr
        assert done.returncode != 0
        assert "连不上" in done.stdout + done.stderr

    def test_it_tells_you_what_to_do_next(self, home):
        """只说"连不上"不够——用户下一步该干什么要写出来。"""
        done = _run_repl("http://127.0.0.1:1", "/quit\n", home=home)
        body = done.stdout + done.stderr
        assert "doctor" in body or "确认" in body, body
