"""单命令入口：`guanjia` = 对话管家（招牌）；`guanjia web` = 本地网页壳。

    guanjia                 # 进入 CLI 管家 REPL
    guanjia --login         # 终端登录/注册
    guanjia web [--port N]  # 启动本地网页壳
    guanjia today           # 一眼统筹总览（不进 REPL）
    guanjia remote          # 多远端档案：list / use <名> / add <名> [服务器] / rm <名>
    guanjia doctor          # 连接自诊断：配置/可达/登录态/会话存储
    guanjia run <工作流>    # 直接跑一个已发布工作流（k=v 传参，--json 机器读）
    guanjia completion bash|zsh   # 补全脚本：eval "$(guanjia completion bash)"
"""

from __future__ import annotations

import sys


HELP = """guanjia（管家）— 终端里说人话，远端工厂造出能跑、有定时、可监控的工作流

用法：
  guanjia                                   对话管家 REPL（招牌）
  guanjia --login                           终端登录/注册（注册令牌 + 自定用户名密码）
  guanjia web [--port N] [--open|--app]     本地网页壳（--app 独立窗口）
  guanjia today                             一眼统筹总览：今日运行/定时/失败
  guanjia run <工作流> [k=v…] [--json] [--wait N]
                                            直接跑一个已发布工作流（脚本/cron 用）
  guanjia remote [list|use <名>|add <名> [服务器]|rm <名>]
                                            多远端档案切换
  guanjia rerun <run前缀>                   用原输入重跑一次运行
  guanjia export <工作流> [-o 文件]         导出可搬运的快照 JSON
  guanjia import <文件> [--name] [--no-publish]  导入快照为新工作流
  guanjia doctor                            连接自诊断：配置→可达→登录态→存储
  guanjia completion bash|zsh               Tab 补全：eval \"$(guanjia completion bash)\"
  guanjia --version                         版本

REPL 里：直接说人话；命令 /today /wf /remote /new /login /help /quit。
哪里不对：guanjia doctor。"""


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print(HELP)
        return
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
        week = d.get("week") or []
        if week:
            def _cell(day):
                total = day["ok"] + day["fail"]
                if not total:
                    return "·"
                if day["fail"] > day["ok"]:
                    return "✕"
                return "△" if day["fail"] else "✓"
            print("  近7日 " + " ".join(f"{w['date'][5:]}{_cell(w)}" for w in week)
                  + "  （✓全成 △有失败 ✕失败居多 ·无运行）")
        for sch in d["schedules"]:
            print(f"  ⏰ {sch['workflow']} 每天 {sch['at']} {sch['timezone']}")
        for f in d["recent_failures"][:5]:
            print(f"  ✕ {f['workflow']} @{f['at']}  run {f['run_id']}  {f['error'][:60]}")
        if d["recent_failures"]:
            print("  （想知道为什么失败：guanjia 里问「run <编号> 为什么失败」）")
        return
    if args and args[0] == "completion":
        from .completion import main as completion_main
        sys.exit(completion_main(args[1:]))
    if args and args[0] == "_wf-names":
        from .completion import print_workflow_names
        print_workflow_names()
        return
    if args and args[0] == "_profile-names":
        from .completion import print_profile_names
        print_profile_names()
        return
    if args and args[0] == "run":
        from .runcmd import main as run_main
        sys.exit(run_main(args[1:]))
    if args and args[0] == "rerun":
        from .runcmd import rerun_main
        sys.exit(rerun_main(args[1:]))
    if args and args[0] == "export":
        from .runcmd import export_main
        sys.exit(export_main(args[1:]))
    if args and args[0] == "import":
        from .runcmd import import_main
        sys.exit(import_main(args[1:]))
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
