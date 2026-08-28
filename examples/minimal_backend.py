#!/usr/bin/env python3
"""能让 guanjia 跑起来的最小后端——用来证明那份接口清单确实够用。

guanjia 一直说「只经 HTTP 说话，换谁实现都行」。这个文件是那句话的证据：
零依赖、单文件、内存里假装有两个工作流，`guanjia doctor --contract` 全绿，
`guanjia today` 和 `guanjia run` 都能跑。

它**不是**产品，是给自己实现后端的人当骨架和对照：
每个处理函数上面写着 guanjia 拿这块数据干什么、少了会怎样。

    python3 examples/minimal_backend.py            # 监听 127.0.0.1:8801
    guanjia remote add mini http://127.0.0.1:8801
    guanjia --login                                # 令牌随便填，见下
    guanjia doctor --contract

登录：任何用户名 + 任何密码都发令牌（这是玩具，不是认证）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8801
TOKEN = "mini-token"


def _now(offset_minutes: int = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(minutes=offset_minutes)).isoformat(timespec="seconds")


# 假装的两个工作流。start 节点的 inputs 就是 guanjia run 会问你要的东西。
APPS = [
    {
        "id": "app-hello", "name": "打招呼", "description": "把名字变成一句问候",
        "requirement": "给一个名字，回一句问候", "active_version": 1,
        "inputs": [{"name": "name", "type": "string", "example": "小明"}],
        "outputs": ["greeting"],
    },
    {
        "id": "app-count", "name": "数数", "description": "数一段文字有几个字",
        "requirement": "给一段文字，回字数", "active_version": 1,
        "inputs": [{"name": "text", "type": "string", "example": "一二三"}],
        "outputs": ["count"],
    },
]
RUNS: list[dict] = []


def _snapshot(app: dict) -> dict:
    """guanjia 从发布版快照里读 start 节点的 inputs，用来做类型转换与必填校验。

    少了这块：`guanjia run` 没法把命令行的字符串转成 array/number，
    也没法在发请求前拦住「少给了必填参数」。
    """
    return {"snapshot": {"name": app["name"], "workflow": {"nodes": [
        {"id": "start", "type": "start", "config": {"inputs": app["inputs"]}},
        {"id": "end", "type": "end",
         "config": {"outputs": {key: "string" for key in app["outputs"]}}},
    ], "edges": []}}, "revision": 1, "version": 1}


def _run(app: dict, inputs: dict) -> dict:
    if app["id"] == "app-hello":
        outputs = {"greeting": f"你好，{inputs.get('name', '朋友')}！"}
    else:
        outputs = {"count": len(str(inputs.get("text", "")))}
    # 字段名照契约来：guanjia 从这里取 run_id（写这个例子时正是在这栽的）
    run = {"run_id": f"run-{len(RUNS) + 1:04d}",
           "id": f"run-{len(RUNS) + 1:04d}", "application_id": app["id"],
           "status": "succeeded", "outputs": outputs, "error": "",
           "created_at": _now(), "version": 1}
    RUNS.append(run)
    return run


class Handler(BaseHTTPRequestHandler):
    server_version = "guanjia-minimal/1.0"

    # ── 路由表：键是正则，值是处理函数 ─────────────────────────────
    def routes(self):
        return [
            # 认得出你是谁。guanjia doctor 用它判断登录态是否还有效。
            (r"^/api/v1/me$", "GET", lambda m, b: {
                "user": {"id": "u1", "name": "demo", "role": "admin"}}),

            # 工作流清单。这是最要紧的一个——没有它 guanjia 基本没法用。
            (r"^/api/v1/applications$", "GET", lambda m, b: [
                {"id": a["id"], "name": a["name"], "description": a["description"],
                 "requirement": a["requirement"], "active_version": a["active_version"]}
                for a in APPS]),

            # 单个工作流的详情。guanjia rerun 用它取当前名字——
            # 缺了不会炸（那边包了 try/except），只是重跑时名字空着。
            (r"^/api/v1/applications/([^/]+)$", "GET", lambda m, b: {
                k: _app(m.group(1))[k]
                for k in ("id", "name", "description", "requirement", "active_version")}),

            # 历史版本清单。没有它就谈不上回滚。
            (r"^/api/v1/applications/([^/]+)/versions$", "GET", lambda m, b: [
                {"version": _app(m.group(1))["active_version"],
                 "created_at": "2026-01-01T00:00:00+00:00"}]),

            # 发布版快照：run 的类型转换与必填校验都读这里
            (r"^/api/v1/applications/([^/]+)/draft$", "GET",
             lambda m, b: _snapshot(_app(m.group(1)))),
            (r"^/api/v1/applications/([^/]+)/versions/latest$", "GET",
             lambda m, b: _snapshot(_app(m.group(1)))),

            # 运行历史。guanjia 的「最近跑得怎么样」读它。
            (r"^/api/v1/applications/([^/]+)/runs$", "GET",
             lambda m, b: [r for r in RUNS if r["application_id"] == m.group(1)]),

            # 发起一次运行。同步返回结果即可，guanjia 会等。
            (r"^/api/v1/applications/([^/]+)/runs$", "POST",
             lambda m, b: _run(_app(m.group(1)), (b or {}).get("inputs") or {})),
            (r"^/api/v1/runs/([^/]+)$", "GET",
             lambda m, b: next(r for r in RUNS if r["run_id"] == m.group(1))),

            # today 面板的全部数字。recent_failures 里的 error 请给**人话**：
            # guanjia 原样显示，写英文栈里的原始报错业主看不懂。
            (r"^/api/v1/overview$", "GET", lambda m, b: {
                "date_utc": _now()[:10],
                "runs_today": {"total": len(RUNS), "succeeded": len(RUNS),
                               "failed": 0, "running": 0},
                "published_workflows": len(APPS),
                "builds_active": 0,
                "schedules": [],
                "recent_failures": [],
                "week": [],
            }),

            # 以下都是**可选**的：没有就静默降级，不会报错。
            (r"^/api/v1/health-report$", "GET", lambda m, b: {
                "counts": {"broken": 0, "stale": 0, "waiting": 0, "ok": len(APPS)},
                "items": [], "days": 7}),
            (r"^/api/v1/scheduler/health$", "GET", lambda m, b: {
                "running": True, "alive": True, "last_tick_at": _now(),
                "seconds_since_tick": 1.0, "poll_seconds": 30.0,
                "tick_count": 1, "restart_count": 0, "last_error": ""}),
            (r"^/api/v1/applications-archived$", "GET", lambda m, b: []),
            (r"^/api/v1/applications-archivable$", "GET", lambda m, b: []),

            # 登录/注册：玩具实现，任何账号都发同一个令牌
            (r"^/api/v1/auth/(login|register)$", "POST", lambda m, b: {
                "user": {"id": "u1", "name": str((b or {}).get("name") or "demo"),
                         "role": "admin", "status": "active"},
                "token": TOKEN}),

            # 对话管家。真后端在这里跑智能体循环；这里只回一句实话。
            (r"^/api/v1/assistant/agent$", "POST", lambda m, b: {
                "actions": [],
                "text": "这是最小后端，没有接语言模型——"
                        "它只为验证接口清单是否够用。工作流列表和运行都是真的。"}),
        ]

    # ── 下面是管道，跟契约无关 ─────────────────────────────────────
    def _respond(self, code: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method: str):
        if not self.path.startswith("/api/v1/auth/") and self.path != "/health":
            auth = self.headers.get("Authorization") or ""
            if not auth.startswith("Bearer "):
                return self._respond(401, {"detail": "缺少令牌"})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return self._respond(400, {"detail": "请求体不是合法 JSON"})
        path = self.path.split("?", 1)[0]
        for pattern, verb, fn in self.routes():
            match = re.match(pattern, path)
            if match and verb == method:
                try:
                    return self._respond(200, fn(match, body))
                except StopIteration:
                    return self._respond(404, {"detail": "没有这条记录"})
                except KeyError as error:
                    return self._respond(404, {"detail": str(error)})
        self._respond(404, {"detail": f"没有这个接口：{method} {path}"})

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._respond(200, {"status": "ok"})
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path}")


def _app(app_id: str) -> dict:
    for app in APPS:
        if app["id"] == app_id or app["name"] == app_id:
            return app
    raise KeyError(f"没有这个工作流：{app_id}")


if __name__ == "__main__":
    print(f"最小后端在 http://127.0.0.1:{PORT}（Ctrl-C 停）")
    print(f"  guanjia remote add mini http://127.0.0.1:{PORT}")
    print("  guanjia --login        # 用户名密码随便填")
    print("  guanjia doctor --contract")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
