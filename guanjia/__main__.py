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
  guanjia doctor [--contract]               连接自诊断；--contract 查后端接口齐不齐
  guanjia completion bash|zsh               Tab 补全：eval \"$(guanjia completion bash)\"
  guanjia --version                         版本

REPL 里：直接说人话；命令 /today /wf /remote /new /login /help /quit。
哪里不对：guanjia doctor。"""


# 所有子命令。打错时用它给提示，也用它挡住 argparse 的英文报错。
KNOWN_COMMANDS = frozenset({
    "web", "today", "run", "rerun", "remote", "doctor",
    "export", "import", "completion", "help",
})


def _connection_args(prog: str, argv: list[str]) -> dict:
    """解析 --server / --token / --profile，别的参数一律拒绝。

    2026-08-29 实测：`guanjia today --server http://别的机器` **一声不吭**地
    照旧查了本机——today 和 doctor 那两条分支压根不解析参数，
    用户敲什么都被默默吞掉。于是屏幕上是一份看起来正常的报表，
    而它来自另一台机器。**默默忽略比直接报错糟得多**：
    报错用户会改，忽略他不会知道。
    （run / rerun / export 早就会说「不认识这些参数」，
      只有这两条分支漏了——又是同一个闸没装满出口。）
    """
    from .argparse_zh import ChineseArgumentParser

    parser = ChineseArgumentParser(prog=prog, description="连接参数")
    parser.add_argument("--server", help="后端地址（不给就用当前档案里的）")
    parser.add_argument("--token", help="访问令牌（不给就用当前档案里的）")
    parser.add_argument("--profile", help="用哪个远端档案")
    parsed = parser.parse_args(argv)
    return {"server": parsed.server, "token": parsed.token, "profile": parsed.profile}


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
        from .remote import RemoteClient, RemoteError, next_step
        cfg = load_config(**_connection_args("guanjia today", args[1:]))
        try:
            d = RemoteClient(cfg["server"], cfg["token"]).request("GET", "/api/v1/overview")
        except RemoteError as error:
            print(f"{error}\n{next_step(error, has_token=bool(cfg['token']))}")
            sys.exit(1)
        rt = d["runs_today"]
        running = rt.get("running", 0)
        print(f"今日运行 {rt['total']}（✓{rt['succeeded']} ✕{rt['failed']}"
              + (f" ⋯{running}" if running else "") + "）· "
              f"已发布 {d['published_workflows']} · 生成中 {d['builds_active']}")
        week = d.get("week") or []
        if week:
            def _cell(day):
                other = day.get("other", 0)
                total = day["ok"] + day["fail"] + other
                if not total:
                    return "·"
                if not day["ok"] and not day["fail"]:
                    return "○"          # 跑了但都没出结果（排队/进行中/暂停）
                if day["fail"] > day["ok"]:
                    return "✕"
                return "△" if day["fail"] else "✓"
            print("  近7日 " + " ".join(f"{w['date'][5:]}{_cell(w)}" for w in week)
                  + "  （✓全成 △有失败 ✕失败居多 ○未出结果 ·无运行）")
        for sch in d["schedules"]:
            print(f"  ⏰ {sch['workflow']} 每天 {sch['at']} {sch['timezone']}")
        if d["recent_failures"]:
            # 这一栏是「最近」不是「今天」——顶上写着今日运行，不说清楚会被当成今天的
            print("  最近的失败：")
        from .failures import summarize, more_kinds_note
        for f in d["recent_failures"][:5]:
            head, tail = summarize(f)
            print(f"  ✕ {head}")
            print(f"      {tail}")
        note = more_kinds_note(d, shown=5)
        if note:
            print(f"  {note}")
        if d["recent_failures"]:
            print("  （想知道为什么失败：guanjia 里问「run <编号> 为什么失败」）")
        try:
            report = RemoteClient(cfg["server"], cfg["token"]).request(
                "GET", "/api/v1/health-report")
            bad = [i for i in report.get("items", []) if i.get("state") != "ok"]
            for item in bad[:5]:
                mark = "✕" if item["state"] == "broken" else "⏸"
                print(f"  {mark} {item['workflow']}：{item['reason']}")
        except RemoteError:
            pass  # 老远端没有体检端点：不影响 today 主体
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
        from .config import load_config
        rest = [a for a in args[1:] if a != "--contract"]
        cfg = load_config(**_connection_args("guanjia doctor", rest))
        if "--contract" in args[1:]:
            from .contract import run as contract_run
            sys.exit(contract_run(cfg))
        from .doctor import run as doctor_run
        sys.exit(doctor_run(cfg))
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
                # 只说"没有"不给出路。用户记错名字时最需要的就是那份清单。
                from .config import list_profiles
                _, profiles = list_profiles()      # 回的是 (当前档案, 全部档案)
                names = sorted(profiles)
                print(f"没有档案「{args[2]}」。"
                      + (f"现有的：{'、'.join(names)}" if names
                         else "一个档案都还没有——用 guanjia remote add <名字> 加一个"))
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
    # 打错子命令时别把 argparse 的英文用法吐给用户。
    # 之前 `guanjia 蛤蟆` 回的是：
    #   usage: python -m guanjia [-h] [--login] [--server SERVER]
    #   python -m guanjia: error: unrecognized arguments: 蛤蟆
    # 一句中文没有，也没说清有哪些命令——而 HELP 里全都写着。
    # 不以 - 开头的第一个参数只可能是子命令，能在这里判掉。
    if args and not args[0].startswith("-") and args[0] not in KNOWN_COMMANDS:
        near = [c for c in KNOWN_COMMANDS if c.startswith(args[0][:2])]
        print(f"没有「{args[0]}」这个命令。"
              + (f"你是想说 {'、'.join(near)}？" if near else ""))
        print(f"可用的：{'、'.join(sorted(KNOWN_COMMANDS))}")
        print("完整用法：guanjia --help；直接敲 guanjia 进对话。")
        sys.exit(2)
    from .cli import main as cli_main
    cli_main()


def _run_cli() -> None:
    """入口的最后一道兜底：任何没接住的异常都不该以栈回溯见用户。

    2026-08-29 实测：让后端回一个形状不对的 200（比如 {}），
    `guanjia today` 当场抛 KeyError: 'runs_today' 加一整屏回溯。
    客户端里对远端返回值的直取下标有 224 处，逐个改 .get() 既大又会
    把真实信号一起吞掉——所以在边界上兜一次，一个地方盖住全部。

    分三类说话，因为用户要做的事不一样：
      · 缺字段 / 类型不对 → 后端形状不对，去 doctor --contract 自查
      · Ctrl-C            → 他自己按的，安静退出
      · 其余              → 说清楚是意料之外，并给出自查入口
    """
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        print(f"后端返回的数据和 guanjia 预期的形状对不上（{type(error).__name__}: {error}）。\n"
              f"用 guanjia doctor --contract 看是哪个接口缺了什么。")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - 兜底就是要接住一切
        print(f"出了意料之外的问题：{error}\n"
              f"哪里不对可以自查：guanjia doctor")
        sys.exit(1)


if __name__ == "__main__":
    _run_cli()
