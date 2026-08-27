"""单命令入口：`bench` = 对话管家（招牌）；`bench web` = 本地网页壳。

    bench                 # 进入 CLI 管家 REPL
    bench --login         # 终端登录/注册
    bench web [--port N]  # 启动本地网页壳
    bench today           # 一眼统筹总览（不进 REPL）
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "web":
        sys.argv = [sys.argv[0]] + args[1:]
        from .app import main as web_main
        web_main()
        return
    if args and args[0] == "today":
        from .config import load_config
        from .remote import RemoteClient, RemoteError
        cfg = load_config()
        try:
            d = RemoteClient(cfg["server"], cfg["token"]).request("GET", "/api/v1/overview")
        except RemoteError as error:
            print(f"远端不可达或未登录：{error}\n先运行 guanjia --login")
            sys.exit(1)
        rt = d["runs_today"]
        print(f"今日运行 {rt['total']}（✓{rt['succeeded']} ✕{rt['failed']}）· "
              f"已发布 {d['published_workflows']} · 生成中 {d['builds_active']}")
        for sch in d["schedules"]:
            print(f"  ⏰ {sch['workflow']} 每天 {sch['at']} {sch['timezone']}")
        return
    from .cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
