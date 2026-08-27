"""demo 录制驱动：pexpect 假装真人打字，供 asciinema rec -c 调用。

演的是产品现在的招牌故事，而不是"能对话"：
    体检发现异常 → 在对话里问清原因 → 跑通拿到真数据。
CLI 段（doctor）与 REPL 段（对话）各一半——前者是"一眼知道平台状况"，
后者是"说人话拿到结果"，两根支柱各占一段。

用法（见 docs/naming-and-distribution.md 的传播清单）：
    asciinema rec docs/demo.cast -i 2 -c "python scripts/record_demo.py" --overwrite
    agg docs/demo.cast docs/demo.gif --font-size 15 --speed 1.2
需要已登录（guanjia --login）且远端有已发布工作流。

坑（踩过）：expect 的模式要用 "❯".encode("utf-8") 且不带尾随空格——
提示符里 ❯ 与空格之间夹着 ANSI 重置序列，带空格永远匹配不上。
"""

import os
import subprocess
import sys
import time

import pexpect

REPL_LINES = [
    "有哪些工作流？只要名字",
    "跑一下文本行数与净字数统计，text 用「甲\\n乙\\n丙」",
]


def type_out(child, text: str, delay: float = 0.045) -> None:
    for char in text:
        child.send(char.encode("utf-8"))
        time.sleep(delay)


def banner(text: str) -> None:
    """在录像里插一行说明，观众才知道每段在演什么。"""
    sys.stdout.write(f"\r\n\x1b[2m{text}\x1b[0m\r\n")
    sys.stdout.flush()
    time.sleep(1.0)


# ── 第一段：一眼知道平台状况 ─────────────────────────────────────────
banner("$ guanjia doctor")
subprocess.run([sys.executable, "-m", "guanjia", "doctor"],
               stdout=sys.stdout, stderr=subprocess.STDOUT, timeout=120)
time.sleep(1.6)

banner("$ guanjia today")
subprocess.run([sys.executable, "-m", "guanjia", "today"],
               stdout=sys.stdout, stderr=subprocess.STDOUT, timeout=120)
time.sleep(1.8)

# ── 第二段：说人话拿到结果 ───────────────────────────────────────────
banner("$ guanjia            # 对话管家")
child = pexpect.spawn(sys.executable, ["-m", "guanjia"], env={**os.environ}, timeout=300)
child.setwinsize(30, 100)
child.logfile_read = sys.stdout.buffer

child.expect("❯".encode("utf-8"))
for line in REPL_LINES:
    time.sleep(1.0)
    type_out(child, line)
    time.sleep(0.6)
    child.sendline("")
    child.expect("❯".encode("utf-8"), timeout=300)
time.sleep(1.5)
child.sendline("/quit")
child.expect(pexpect.EOF)
