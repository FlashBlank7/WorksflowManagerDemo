"""guanjia doctor：首跑连接自诊断。

配置 → 可达性 → 登录态 → 会话存储，逐项检查并给出人话结论与下一步命令。
退出码：0 全通过；1 有需要处理的问题。
"""

from __future__ import annotations

import time
import urllib.error

from . import sessions
from .config import list_profiles, load_config
from .remote import RemoteClient, RemoteError, RemoteUnreachable

from .cut import clip
from .palette import paint

# 上色与否由 palette 统一判（NO_COLOR / 非终端 一律不上色）
OK = paint("32", "✓")
BAD = paint("31", "✕")
WARN = paint("33", "!")


def _scheduler_health(cfg: dict) -> tuple[dict | None, str]:
    """查平台调度器的死活。回 (结果, 没查成的原因)。

    原因要分开说。第一版一律回 None，打出来的是
    「没验（远端没有这个接口，多半是旧版本）」——
    可 401 的时候接口明明在，只是没登录。用户照着这句去升级后端，
    白费半天工夫。诊断工具给错方向比不给方向更糟。
    """
    try:
        return RemoteClient(cfg["server"], cfg["token"], timeout=8.0).request(
            "GET", "/api/v1/scheduler/health"), ""
    except RemoteError as error:
        if error.status in (401, 403):
            return None, "还没登录，查不了"
        if error.status in (404, 405):
            return None, "远端没有这个接口，多半是旧版本"
        return None, f"远端答了 {error.status}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "连不上远端"


def run(cfg: dict | None = None) -> int:
    # cfg 由调用方传进来，是为了让 `guanjia doctor --server 别的机器` 真的
    # 查那台机器。以前这里硬调 load_config()，命令行上写的地址被默默吞掉，
    # 于是"自诊断"诊断的是另一台机器——诊断工具给错对象比不给更糟。
    cfg = cfg if cfg is not None else load_config()
    _, profiles = list_profiles()
    problems: list[str] = []
    # 没查成的部件单独记一笔。**「没查」和「查过没事」必须长得不一样**——
    # 不然最后那句「一切正常」是在替没查过的部分打包票。
    unchecked: list[str] = []

    # 1 配置
    if profiles:
        note = "" if cfg["token"] else "（无令牌）"
        print(f"{OK} 配置：档案「{cfg['profile']}」 server={cfg['server']}{note}")
    else:
        print(f"{WARN} 配置：还没有档案，先用默认 {cfg['server']}")
    if not cfg["token"]:
        if profiles:
            problems.append("没有会话令牌 → guanjia --login 登录/注册")
        else:
            # 全新用户：他缺的不是令牌，是还不知道这工具要连什么
            problems.append("还没连过后端：guanjia 是薄客户端，需要一个工作流平台。"
                            "有地址和注册令牌就 guanjia --login；没有就先部署一个"
                            "（见项目主页「后端」一节）")

    # 2 可达性 + 延迟（匿名探测：4xx/5xx 也证明服务器活着）
    anon = RemoteClient(cfg["server"], "", timeout=6.0)
    t0 = time.monotonic()
    reachable = False
    try:
        anon.health()
        reachable = True
    except RemoteUnreachable as error:
        # 必须排在 RemoteError 前面：它是子类，顺序反了就会把"连不上"报成"有响应"
        print(f"{BAD} 可达性：{error}")
        problems.append("确认远端平台已启动、地址端口没写错（guanjia remote 查看档案）")
    except RemoteError as error:
        reachable = True
        if "不是 JSON" in str(error):
            print(f"{BAD} 可达性：{cfg['server']} 有东西在应答，但不像 guanjia 平台")
            problems.append("地址可能指错了：核对 guanjia remote 里的 server")
            reachable = False
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        print(f"{BAD} 可达性：连不上 {cfg['server']} —— {reason}")
        problems.append("确认远端平台已启动、地址端口没写错（guanjia remote 查看档案）")
    if reachable:
        ms = (time.monotonic() - t0) * 1000
        print(f"{OK} 可达性：{cfg['server']} 有响应（{ms:.0f} ms）")

    # 3 登录态
    if reachable and cfg["token"]:
        try:
            me = RemoteClient(cfg["server"], cfg["token"], timeout=8.0).request(
                "GET", "/api/v1/me")["user"]
            role = "管理员" if me.get("role") == "admin" else "成员"
            print(f"{OK} 登录态：{me.get('name', '?')}（{role}）")
        except RemoteError as error:
            if error.status == 401:
                print(f"{BAD} 登录态：令牌已失效（401）")
                problems.append("重新登录：guanjia --login（REPL 里 /login 也行）")
            else:
                print(f"{BAD} 登录态：远端返回 {error.status}")
                problems.append(f"远端异常，看服务端日志：{error}")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"{BAD} 登录态：请求失败 —— {error}")
            problems.append("网络中途断了，重试一次 guanjia doctor")

    # 4 调度器：**不管工作流健不健康都查一次**
    #
    # 原先只在"已经有工作流误点（stale）"时才查。可调度器刚死、还没到
    # 任何定时点的时候，一个工作流都不会 stale——于是 doctor 什么也没查，
    # 却在最后打出「一切正常」。而定时不开火恰恰是那种无声的故障：
    # 用户不会收到任何提示，只是报表再也不来了。
    #
    # 诊断工具最不该做的事，就是在没查过某个部件的情况下宣布全好。
    sched: dict | None = None
    if reachable and cfg["token"]:
        sched, why = _scheduler_health(cfg)
        if sched is None:
            print(f"{WARN} 调度器：没验（{why}）")
            unchecked.append("调度器")
        elif sched.get("alive"):
            behind = sched.get("seconds_since_tick")
            # 「活着」不等于「所有定时都开火了」。某个工作流每轮都被跳过
            # （版本查不到、配置坏了、建运行失败）时，调度器照样心跳、
            # 照样报活着，而那个定时任务在无声地不跑。
            # 打 ✓ 等于替它瞒着——诊断工具最不该做的就是这个。
            skipped = (sched.get("last_error") or "").strip()
            mark = WARN if skipped else OK
            print(f"{mark} 调度器在跑（{behind:.0f}s 前刚轮询过）"
                  if isinstance(behind, (int, float)) else f"{mark} 调度器在跑")
            if skipped:
                print(f"  但有定时没能开火：{clip(skipped, 160)}")
                problems.append("有定时任务每轮都被跳过——"
                                "看上面那条原因，多半是它的发布版或配置有问题")
        else:
            since = sched.get("seconds_since_tick")
            detail = (sched.get("last_error") or "").strip()
            print(f"{BAD} 调度器停了："
                  + (f"上次轮询在 {since:.0f}s 前" if isinstance(since, (int, float))
                     else "从没轮询过")
                  + (f"；{detail}" if detail else ""))
            problems.append("定时任务不会开火了：重启平台服务，"
                            "或看服务端日志里 scheduler.failed 事件")

    # 5 工作流健康（登录成功才查）
    if reachable and cfg["token"]:
        try:
            report = RemoteClient(cfg["server"], cfg["token"], timeout=10.0).request(
                "GET", "/api/v1/health-report")
            counts = report.get("counts") or {}
            bad = [i for i in report.get("items", []) if i.get("state") != "ok"]
            # 发布了却一次都没跑过的，四个状态里落在"正常"那一格——
            # 它确实没坏，但"正常"是个结论，而这种工作流一条证据都没有。
            # 服务端单列了一格 never_ran；这里不读它的话，doctor 会跟着
            # 报"都正常"，和面板犯同一个错。
            # （老服务端没有这个键，取不到就当空，不影响。）
            never_ran = report.get("never_ran") or []
            if not bad:
                print(f"{OK} 工作流健康：{counts.get('ok', 0)} 个已发布工作流都正常")
            else:
                summary = " · ".join(
                    f"{label} {counts[key]}"
                    for key, label in (("broken", "坏"), ("stale", "停"), ("waiting", "等"))
                    if counts.get(key))
                print(f"{WARN} 工作流健康：{len(bad)} 个要看看（{summary}）")
                for item in bad[:5]:
                    print(f"    · {item['workflow']}：{item['reason']}")
                # 两种状态是两回事，别给同一条建议：
                # broken 是跑起来出错，stale 是压根没跑（定时没开火）
                if any(item.get("state") == "broken" for item in bad):
                    problems.append("跑不通的那几个：在对话里说「<名字> 坏了帮我修」，"
                                    "构建智能体会在原工作流上改")
                if any(item.get("state") == "waiting" for item in bad):
                    # 还在跑不是问题，说一句免得用户以为要动手
                    print("    （「等」的那些还在跑或等人工确认，不用管）")
                if any(item.get("state") == "stale" for item in bad):
                    # 调度器上面已经查过一次了，这里只据结果给建议，不重复打印
                    if sched is None:
                        problems.append("没按时开火的那几个：先手动跑一次确认工作流本身"
                                        "没问题（guanjia run <名字>）")
                    elif sched.get("alive"):
                        problems.append("调度器是活的，但上面那些没按时开火——"
                                        "多半是工作流的定时配置改过没发布：先 guanjia run "
                                        "手动跑一次，再在对话里确认它的定时设置")
                    # 调度器已经报停了的话，上面那条 problems 就是根因，不用再加
            if never_ran:
                names = "、".join(never_ran[:3])
                more = f" 等 {len(never_ran)} 个" if len(never_ran) > 3 else ""
                print(f"{WARN} 其中 {names}{more} 还没跑过，好不好还看不出来")
                problems.append("没跑过的那几个：跑一次试试——"
                                "`guanjia run <名字> 参数=值`，"
                                "或者在对话里说「跑一下 <名字>」")
        except (RemoteError, urllib.error.URLError, TimeoutError, OSError) as error:
            # **说出来**。原来是光秃秃一个 pass：体检接口一旦答不了
            # （网络抖一下、后端 500、没登录），这一整段就无声跳过，
            # 而最后照样打「一切正常」——正是这个文件反复写的那件事：
            # 诊断工具最不该在没查过某个部件的情况下宣布全好。
            # 调度器那一段一直是对的（sched is None 时打「没验（原因）」），
            # 就这一段漏了。同一个判据没铺满所有出口，今天第 N 次。
            #
            # 仍然不算 problems：老远端确实没有这个接口，那不是用户的错。
            # 但"没查"和"查过没事"必须长得不一样。
            if isinstance(error, RemoteError) and error.status in (404, 405):
                why = "远端没有这个接口，多半是旧版本"
            elif isinstance(error, RemoteError) and error.status in (401, 403):
                why = "还没登录，查不了"
            elif isinstance(error, RemoteError):
                why = f"远端答了 {error.status}"
            else:
                why = "连不上远端"
            print(f"{WARN} 工作流健康：没验（{why}）")
            unchecked.append("工作流健康")

    # 5 会话存储
    try:
        sessions.DIR.mkdir(parents=True, exist_ok=True)
        probe = sessions.DIR / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        count = len(list(sessions.DIR.glob("*.json")))
        print(f"{OK} 会话存储：{sessions.DIR}（{count} 个会话）")
    except OSError as error:
        print(f"{BAD} 会话存储：{sessions.DIR} 不可写 —— {error}")
        problems.append("检查该目录的权限/磁盘空间")

    print()
    if problems:
        print("下一步：")
        for item in problems:
            print(f"  · {item}")
        return 1
    if unchecked:
        # 没发现问题 ≠ 一切正常。差别就在这句话上。
        print(f"没发现问题，但{'、'.join(unchecked)}没查成——别当成全好。")
        return 0
    print("一切正常。直接 guanjia 开聊。")
    return 0
