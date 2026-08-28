"""guanjia CLI —— 终端里的工作流管家（招牌特性）。

薄 REPL：语言理解与全部工具执行都在远端服务器（/api/v1/assistant/agent），
本地只负责输入输出和一点点颜色。

用法：
    guanjia               # 读 ~/.bench.json（网页端登录过即有）
    guanjia --login       # 终端里登录/注册
直接说话即可（"跑一下GPU日报"/"有哪些工作流"/"给我做一个……的工作流"）。
命令：/today 统筹总览 · /wf 列表 · /remote 多远端 · /new · /login · /help · /quit
Tab 补全：/ 命令、/remote 子命令与档案名、工作流名（/wf 之后）。
"""

from __future__ import annotations

from pathlib import Path


from .argparse_zh import ChineseArgumentParser
import atexit
import getpass
import time

try:  # 方向键历史 + 跨会话持久（纯标准库，无 readline 的平台静默降级）
    import readline

    _HISTORY = Path.home() / ".guanjia_history"
    try:
        readline.read_history_file(_HISTORY)
    except OSError:
        pass
    readline.set_history_length(500)
    def _save_history() -> None:
        try:
            readline.write_history_file(_HISTORY)
        except OSError:
            pass          # HOME 只读时退出不该吐第二段栈

    atexit.register(_save_history)
except ImportError:
    readline = None  # type: ignore[assignment]
import re
import sys

from . import sessions
from .config import list_profiles, load_config, save_login, use_profile
from .remote import RemoteClient, RemoteError, RemoteUnreachable

G = "\033[32m"; C = "\033[36m"; D = "\033[2m"; B = "\033[1m"; R = "\033[31m"; N = "\033[0m"


_WF_CACHE: list[str] = []  # /wf 拉过一次即缓存，Tab 直接补工作流名
_SLASH = ("/today", "/wf", "/remote", "/new", "/login", "/help", "/quit")


def _completer(text: str, state: int):
    buf = readline.get_line_buffer() if readline else ""
    if buf.startswith("/remote "):
        rest = buf[len("/remote "):]
        if rest.startswith(("use ", "rm ")):
            _, profiles = list_profiles()
            cands = [name for name in profiles if name.startswith(text)]
        else:
            cands = [w for w in ("list", "use", "add", "rm") if w.startswith(text)]
    elif buf.startswith("/"):
        cands = [c for c in _SLASH if c.startswith(text)]
    else:
        cands = [w for w in _WF_CACHE if w and w.startswith(text)]
    return cands[state] if state < len(cands) else None


if readline:
    readline.set_completer_delims(" ")
    readline.set_completer(_completer)
    readline.parse_and_bind("tab: complete")


# 服务端会在出口剪掉这个内部标记；流式分片是逐字发出的，
# 客户端这边再挡一道，免得它在屏幕上一闪而过
_CONTEXT_MARK = re.compile(r"<上下文[^>]*/>\s*")
# 左右两侧都必须紧挨着非空白字符（CommonMark 的 flanking 规则）。
# 不加这条限制的话，Python 的 ** 会被当成加粗吃掉：
#   "2 ** 10 = 1024，2 ** 20"  →  "2 [粗] 10 = 1024，2 [复位] 20"
#   "{**a, **b}"               →  "{a, b}"
# 这是给开发者用的终端工具，把人要复制走的代码静默改错是最不能忍的一种。
_MD_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_MD_CODE = re.compile(r"`([^`]+)`")


def stream_chunk(pending: str, chunk: str) -> tuple[str, str]:
    """吃进一个流式分片，回 (现在能打印的文本, 还要攒着的尾巴)。

    单独拎出来是为了能测：这段逻辑原本长在 REPL 那个大函数里，
    接线自查时发现「把 render_md 换成直接 print，测试照样全绿」——
    判据有人守，接线没人守。

    有 markdown 标记或上下文标记的尾巴要攒到行尾再渲染，
    否则半个 ** 或半个 <上下文 会先冒到屏幕上。
    """
    pending += chunk
    out: list[str] = []
    while "\n" in pending:
        line, pending = pending.split("\n", 1)
        out.append(render_md(line) + "\n")
    if not ("*" in pending or "`" in pending or "<" in pending):
        out.append(pending)
        pending = ""
    return "".join(out), pending


# 构建状态的中文说法。状态码是给机器看的，别印给人——
# 2026-08-29 之前这里印的是 `building · 修订 3`、`构建结束（needs_attention）`。
# 服务端同一天把状态码从各条出口都堵掉了，客户端这两处漏着。
BUILD_WORDS = {
    "queued": "排队中", "building": "搭建中", "running": "搭建中",
    "published": "已发布", "ready": "搭好了", "cancelled": "已放弃",
    "failed": "没搭成", "needs_attention": "停下来等你说话",
}


def render_md(line: str) -> str:
    """把模型写的 markdown 渲染成终端能看的样子。

    网页壳的 md() 做同一件事（改一边记得同步另一边）：
    终端里不渲染的话，**加粗** 就是四个星号，看着像坏了。
    """
    line = _CONTEXT_MARK.sub("", line)
    line = _MD_BOLD.sub(f"{B}\\1{N}", line)
    return _MD_CODE.sub(f"{D}\\1{N}", line)


def say(text: str) -> None:
    print(f"{G}●{N} {text}")


def follow_build(remote: RemoteClient, build_id: str) -> None:
    """招牌时刻：生成提交后原地跟踪到发布。Ctrl+C 只停止跟踪，构建仍在远端继续。"""

    from .plugins import workflow

    print(f"  {D}跟踪构建 {build_id[:8]}…（Ctrl+C 停止跟踪，不影响远端）{N}")
    last = ""
    misses = 0            # 远端抖一下不该让整个 REPL 带栈退出
    try:
        while True:
            try:
                status = workflow.build_status(remote, build_id)
                misses = 0
            except (RemoteError, OSError) as error:
                misses += 1
                if misses >= 3:
                    say(f"跟踪中断（{error}）——构建仍在远端进行，"
                        "稍后 /today 或直接问我进度。")
                    return
                time.sleep(4)
                continue
            line = f"{BUILD_WORDS.get(status['status'], '进行中')} · 修订 {status.get('revision') or 0}"
            if status.get("narration"):
                line += f" · {status['narration'][:56]}"
            if line != last:
                print(f"  {D}⏳ {line}{N}")
                last = line
            if status["status"] in ("published", "ready", "needs_attention", "failed", "cancelled"):
                if status.get("published_version"):
                    say(f"搭好了！已发布 v{status['published_version']}——直接说「跑一下」就能用。")
                elif status.get("pending_question"):
                    say(f"构建时遇到一个问题，需要你确认：{status['pending_question']}")
                    try:
                        answer = input(f"{C}❓{N} ").strip()
                    except (KeyboardInterrupt, EOFError):
                        print()
                        say("先不回答也行——之后说「继续刚才的构建」再答。")
                        return
                    if answer:
                        try:
                            remote.request(
                                "POST", f"/api/v1/builds/{build_id}/resume",
                                {"message": answer})
                        except (RemoteError, OSError) as error:
                            # 别让用户刚敲的答案凭空蒸发
                            say(f"转交失败（{error}）。你刚才的回答是：")
                            print(f"  {D}{answer}{N}")
                            say("远端恢复后说「继续刚才的构建」再贴一次。")
                            return
                        say("已转交，继续跟踪。")
                        continue
                    say("空回答未发送——之后说「继续刚才的构建」再答。")
                else:
                    tail = f"：{status['error']}" if status.get("error") else ""
                    say(f"构建结束（{BUILD_WORDS.get(status['status'], '情况不明')}{tail}）——说「继续刚才的构建」可续跑。")
                return
            time.sleep(5)
    except KeyboardInterrupt:
        print()
        print(f"{D}已停止跟踪（构建仍在远端进行，/today 或直接问我进度）{N}")


def first_run_guide(server_default: str) -> bool:
    """从没配过的人：先讲清它要什么，再问要不要现在填。

    返回 True 表示用户愿意继续登录，False 表示先退出去准备后端。
    """
    print(f"""{B}管家（guanjia）{N} —— 在终端里说人话，让远端把工作流搭出来并一直跑。

{B}它需要一个后端。{N}本机只是壳：不跑模型、不存业务数据，
所有能力来自你自己部署的工作流平台——这样审计才完整，客户端也无法伪造结果。

{D}还没有后端？{N}
  · 自己部署一个（见项目主页的「后端」一节），或
  · 问已经在用的同事要：{B}服务器地址 + 注册令牌{N}，两样就够

{D}已经有了？{N}下面填两行就能开始。也可以随时 Ctrl+C 退出，
之后用 {B}guanjia --login{N} 再来。
""")
    try:
        answer = input("  现在就填吗？[Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return answer in ("", "y", "yes", "是")


def login_flow(server_default: str, profile: str | None = None) -> RemoteClient:
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
    pname = save_login(server, result["token"], result["user"]["name"], profile)
    say(f"你好，{result['user']['name']}（{'管理员' if result['user']['role']=='admin' else '成员'}）· 远端档案「{pname}」")
    return RemoteClient(server, result["token"])


def main() -> None:
    parser = ChineseArgumentParser(description="guanjia CLI — 工作流管家")
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
        except RemoteUnreachable as error:
            # 平台没起来 ≠ 令牌失效：把人推进登录流程只会更糊涂
            print(f"{R}{error}{N}\n先确认远端平台在跑，或用 guanjia doctor 自查。")
            sys.exit(1)
        except RemoteError:
            remote = None   # 令牌失效才重新登录
    if remote is None:
        _, profiles = list_profiles()
        if not profiles and not args.login:
            # 从没配过：先讲清楚它要什么，别一上来就问"服务器地址"
            if not first_run_guide(cfg["server"]):
                print(f"{D}准备好后端后，运行 guanjia --login 继续。{N}")
                return
        try:
            remote = login_flow(cfg["server"])
        except (RemoteError, KeyboardInterrupt, EOFError) as error:
            print(f"{R}登录失败：{error}{N}")
            sys.exit(1)

    sid = sessions.latest_id() or sessions.new_session()
    stored = sessions.load(sid)
    history: list[dict] = [m for m in (stored or {}).get("messages", [])
                           if not m.get("kind") and m.get("text")]
    if history:
        print(f"{D}（继续上次对话「{(stored or {}).get('title','')}」，/new 开新对话）{N}")
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
        if text == "/new":
            sid = sessions.new_session()
            history = []
            say("新对话开始。")
            continue
        if text == "/help":
            print(f"{D}直接用自然语言：跑一下GPU日报 / 有哪些工作流 / 昨天日报结果多少 /\n"
                  f"给我做一个「输入文本输出摘要」的工作流……\n"
                  f"命令：/today 统筹总览 · /wf 工作流列表 · /remote 多远端切换 · /new 新对话 ·\n/login 重新登录 · /quit 退出 · Tab 可补全命令/档案/工作流名{N}")
            continue
        if text == "/remote" or text.startswith("/remote "):
            parts = text.split()
            active, profiles = list_profiles()
            if len(parts) == 1 or parts[1] == "list":
                if not profiles:
                    print(f"{D}还没有远端档案。/remote add <名字> <服务器地址> 新增。{N}")
                for pn, pr in profiles.items():
                    print(f"  {'●' if pn == active else '○'} {pn}  {pr.get('server','')}  {pr.get('user','')}")
                continue
            if parts[1] == "use" and len(parts) > 2:
                try:
                    pr = use_profile(parts[2])
                except KeyError:
                    print(f"{R}没有档案「{parts[2]}」{N}")
                    continue
                remote = RemoteClient(pr["server"], pr.get("token", ""))
                try:
                    me = remote.request("GET", "/api/v1/me")["user"]
                    say(f"已切到「{parts[2]}」（{pr['server']}），你好，{me['name']}。")
                except RemoteError:
                    say(f"已切到「{parts[2]}」，令牌失效，需要重新登录。")
                    try:
                        remote = login_flow(pr["server"], parts[2])
                    except Exception as error:  # noqa: BLE001
                        print(f"{R}登录失败：{error}{N}")
                continue
            if parts[1] == "add" and len(parts) > 2:
                try:
                    remote = login_flow(parts[3] if len(parts) > 3 else remote.server, parts[2])
                except Exception as error:  # noqa: BLE001
                    print(f"{R}登录失败：{error}{N}")
                continue
            print(f"{D}用法：/remote · /remote use <名> · /remote add <名> [服务器]{N}")
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
                if d["recent_failures"]:
                    print(f"  {D}最近的失败：{N}")   # 不是今天的，别让上面那行带偏
                for f in d["recent_failures"][:3]:
                    times = f" ×{f['count']}" if f.get("count", 1) > 1 else ""
                    print(f"  {R}✕ {f['workflow']}{times} @{f['at']} {f['error'][:50]}{N}")
            except RemoteError as error:
                print(f"{R}{error}{N}")
            continue
        if text == "/wf":
            try:
                from .plugins import workflow as wf
                items = wf.list_workflows(remote)
                published = [w for w in items if w["published"]]
                _WF_CACHE[:] = [w["name"] for w in published]
                for w in published:
                    print(f"  {G}▸{N} {w['name']} {D}v{w['version']}{N}")
                say(f"{len(published)} 个已发布（共 {len(items)} 个）——想跑哪个直接说。")
            except RemoteError as error:
                print(f"{R}{error}{N}")
            continue
        history.append({"role": "user", "text": text})
        actions, final, streamed = [], "", False
        pending = ""   # 攒着可能跨分片的 markdown 标记
        try:
            in_text = False
            for event in remote.stream("/api/v1/assistant/agent/stream", {"messages": history[-12:]}):
                kind = event.get("type")
                if kind == "delta" and event.get("text"):
                    if not in_text:
                        print(f"{G}●{N} ", end="", flush=True)
                        in_text = True
                    chunk, pending = stream_chunk(pending, event["text"])
                    if chunk:
                        print(chunk, end="", flush=True)
                    streamed = True
                elif kind == "action":
                    if in_text:
                        print()
                        in_text = False
                    actions.append(event)
                    # 优先用服务端给的中文名；老服务端没有 label，退回 tool
                    name = event.get("label") or event.get("tool")
                    print(f"  {D}⚙ {name} → {event.get('summary')}{N}")
                elif kind == "final":
                    final = event.get("text", "")
                    if pending:
                        print(render_md(pending), end="")
                        pending = ""
                    if in_text:
                        print()
                        in_text = False
                elif kind == "error":
                    raise RemoteError(500, event.get("text", ""))
        except RemoteError:
            try:  # 老服务端回退：非流式
                data = remote.request("POST", "/api/v1/assistant/agent", {"messages": history[-12:]})
                actions, final = data["actions"], data["text"]
                for action in actions:
                    name = action.get("label") or action.get("tool")
                    print(f"  {D}⚙ {name} → {action['summary']}{N}")
            except RemoteError as error:
                print(f"{R}远端出错：{error}{N}")
                history.pop()
                continue
        if final and not streamed:
            say(final)
        # 带上动作痕迹：下一轮的「它」「那个」要靠它解析
        history.append({"role": "assistant", "text": final,
                        "actions": [{k: v for k, v in a.items()
                                     if k in ("tool", "workflow", "name", "app_id",
                                              "build_id", "summary")}
                                    for a in actions][-4:]})
        if not sessions.save(sid, history):
            print(f"{D}（会话没能存到 {sessions.DIR}——这轮对话不会保留）{N}")
        for action in actions:
            if action.get("tool") == "generate_workflow" and action.get("build_id"):
                follow_build(remote, action["build_id"])
                break


if __name__ == "__main__":
    main()
