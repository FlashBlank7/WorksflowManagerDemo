"""guanjia doctor：首跑连接自诊断。

配置 → 可达性 → 登录态 → 会话存储，逐项检查并给出人话结论与下一步命令。
退出码：0 全通过；1 有需要处理的问题。
"""

from __future__ import annotations

import time
import urllib.error

from . import sessions
from .config import list_profiles, load_config
from .remote import RemoteClient, RemoteError

OK = "\x1b[32m✓\x1b[0m"
BAD = "\x1b[31m✕\x1b[0m"
WARN = "\x1b[33m!\x1b[0m"


def run() -> int:
    cfg = load_config()
    _, profiles = list_profiles()
    problems: list[str] = []

    # 1 配置
    if profiles:
        note = "" if cfg["token"] else "（无令牌）"
        print(f"{OK} 配置：档案「{cfg['profile']}」 server={cfg['server']}{note}")
    else:
        print(f"{WARN} 配置：还没有档案，先用默认 {cfg['server']}")
    if not cfg["token"]:
        problems.append("没有会话令牌 → guanjia --login 登录/注册")

    # 2 可达性 + 延迟（匿名探测：4xx/5xx 也证明服务器活着）
    anon = RemoteClient(cfg["server"], "", timeout=6.0)
    t0 = time.monotonic()
    reachable = False
    try:
        anon.health()
        reachable = True
    except RemoteError:
        reachable = True
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

    # 4 会话存储
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
    print("一切正常。直接 guanjia 开聊。")
    return 0
