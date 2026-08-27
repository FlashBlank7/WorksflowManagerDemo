"""bench CLI —— 终端里的工作流管家（招牌特性）。

薄 REPL：语言理解与全部工具执行都在远端服务器（/api/v1/assistant/agent），
本地只负责输入输出和一点点颜色。

用法：
    python3 -m bench.cli               # 读 ~/.bench.json（网页端登录过即有）
    python3 -m bench.cli --login       # 终端里登录/注册
直接说话即可（"跑一下GPU日报"/"有哪些工作流"/"给我做一个……的工作流"）。
命令：/today 统筹总览 · /wf 列表 · /login 重新登录 · /help · /quit
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .config import load_config
from .remote import RemoteClient, RemoteError

G = "\033[32m"; C = "\033[36m"; D = "\033[2m"; B = "\033[1m"; R = "\033[31m"; N = "\033[0m"


def say(text: str) -> None:
    print(f"{G}●{N} {text}")


def login_flow(server_default: str) -> RemoteClient:
    print(f"{B}连接远端平台{N}")
    server = input(f"  服务器 [{server_default}]: ").strip() or server_default
    mode = input("  登录(l) / 注册(r)? [l]: ").strip().lower() or "l"
    name = input("  用户名: ").strip()
    password = getpass.getpass("  密码: ")
    anon = RemoteClient(server, "")
    if mode.startswith("r"):
        reg = getpass.getpass("  注册令牌: ")
        result = anon.request("POST", "/api/v1/auth/register",
                              {"register_token": reg, "name": name, "password": password})
    else:
        result = anon.request("POST", "/api/v1/auth/login", {"name": name, "password": password})
    (Path.home() / ".bench.json").write_text(
        json.dumps({"server": server, "token": result["token"]}, ensure_ascii=False), encoding="utf-8")
    say(f"你好，{result['user']['name']}（{'管理员' if result['user']['role']=='admin' else '成员'}）")
    return RemoteClient(server, result["token"])


def main() -> None:
    parser = argparse.ArgumentParser(description="bench CLI — 工作流管家")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--server", default=None)
    args = parser.parse_args()
    cfg = load_config(args.server, None)
    remote: RemoteClient | None = None
    if not args.login and cfg["token"]:
        remote = RemoteClient(cfg["server"], cfg["token"])
        try:
            me = remote.request("GET", "/api/v1/me")["user"]
            say(f"你好，{me['name']}。我是工作流管家——直接说事，/help 看帮助。")
        except RemoteError:
            remote = None
    if remote is None:
        try:
            remote = login_flow(cfg["server"])
        except (RemoteError, KeyboardInterrupt, EOFError) as error:
            print(f"{R}登录失败：{error}{N}")
            sys.exit(1)

    history: list[dict] = []
    while True:
        try:
            text = input(f"{C}❯{N} ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not text:
            continue
        if text in ("/quit", "/q", "exit"):
            break
        if text == "/help":
            print(f"{D}直接用自然语言：跑一下GPU日报 / 有哪些工作流 / 昨天日报结果多少 /\n"
                  f"给我做一个「输入文本输出摘要」的工作流……\n"
                  f"命令：/today 统筹总览 · /wf 工作流列表 · /login 重新登录 · /quit 退出{N}")
            continue
        if text == "/login":
            try:
                remote = login_flow(remote.server)
            except Exception as error:  # noqa: BLE001
                print(f"{R}登录失败：{error}{N}")
            continue
        if text == "/today":
            try:
                d = remote.request("GET", "/api/v1/overview")
                rt = d["runs_today"]
                say(f"今日运行 {rt['total']}（✓{rt['succeeded']} ✕{rt['failed']} 进行中{rt['running']}）· "
                    f"已发布 {d['published_workflows']} · 生成中 {d['builds_active']}")
                for sch in d["schedules"]:
                    print(f"  {D}⏰ {sch['workflow']} 每天 {sch['at']} {sch['timezone']}"
                          f"（最近触发 {sch.get('last_fire_date') or '—'}）{N}")
                for f in d["recent_failures"][:3]:
                    print(f"  {R}✕ {f['workflow']} @{f['at']} {f['error'][:50]}{N}")
            except RemoteError as error:
                print(f"{R}{error}{N}")
            continue
        if text == "/wf":
            try:
                data = remote.request("POST", "/api/v1/assistant/agent",
                                      {"messages": [{"role": "user", "text": "列出已发布的工作流"}]})
                for action in data["actions"]:
                    print(f"  {D}⚙ {action['tool']} → {action['summary']}{N}")
                say(data["text"])
            except RemoteError as error:
                print(f"{R}{error}{N}")
            continue
        history.append({"role": "user", "text": text})
        print(f"{D}…{N}", end="\r", flush=True)
        try:
            data = remote.request("POST", "/api/v1/assistant/agent", {"messages": history[-12:]})
        except RemoteError as error:
            print(f"{R}远端出错：{error}{N}")
            history.pop()
            continue
        for action in data["actions"]:
            print(f"  {D}⚙ {action['tool']} → {action['summary']}{N}")
        say(data["text"])
        history.append({"role": "assistant", "text": data["text"]})


if __name__ == "__main__":
    main()
