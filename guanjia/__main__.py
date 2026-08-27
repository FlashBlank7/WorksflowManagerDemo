"""单命令入口：`guanjia` = 对话管家（招牌）；`guanjia web` = 本地网页壳。

    guanjia                 # 进入 CLI 管家 REPL
    guanjia --login         # 终端登录/注册
    guanjia web [--port N]  # 启动本地网页壳
    guanjia today           # 一眼统筹总览（不进 REPL）
    guanjia remote          # 多远端档案：list / use <名> / add <名> [服务器] / rm <名>
    guanjia doctor          # 连接自诊断：配置/可达/登录态/会话存储
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in ("--version", "-V"):
        from . import __version__
        print(f"guanjia {__version__}")
        return
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
        for f in d["recent_failures"][:5]:
            print(f"  ✕ {f['workflow']} @{f['at']}  run {f['run_id']}  {f['error'][:60]}")
        if d["recent_failures"]:
            print("  （想知道为什么失败：guanjia 里问「run <编号> 为什么失败」）")
        return
    if args and args[0] == "doctor":
        from .doctor import run as doctor_run
        sys.exit(doctor_run())
    if args and args[0] == "remote":
        from .config import drop_profile, list_profiles, use_profile
        sub = args[1] if len(args) > 1 else "list"
        if sub == "list":
            active, profiles = list_profiles()
            if not profiles:
                print("还没有远端档案。guanjia remote add <名字> <服务器地址>")
            for pn, pr in profiles.items():
                print(f"  {'●' if pn == active else '○'} {pn}  {pr.get('server','')}  {pr.get('user','')}")
        elif sub == "use" and len(args) > 2:
            try:
                pr = use_profile(args[2])
                print(f"已切到「{args[2]}」 {pr.get('server','')}")
            except KeyError:
                print(f"没有档案「{args[2]}」")
                sys.exit(1)
        elif sub == "add" and len(args) > 2:
            from .cli import login_flow
            try:
                login_flow(args[3] if len(args) > 3 else "http://127.0.0.1:8000", args[2])
            except Exception as error:  # noqa: BLE001
                print(f"登录失败：{error}")
                sys.exit(1)
        elif sub == "rm" and len(args) > 2:
            drop_profile(args[2])
            print(f"已删除档案「{args[2]}」")
        else:
            print("用法：guanjia remote [list | use <名> | add <名> [服务器] | rm <名>]")
        return
    from .cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
