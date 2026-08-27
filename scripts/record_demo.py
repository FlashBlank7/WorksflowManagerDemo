"""demo 录制驱动：pexpect 假装真人打字，供 asciinema rec -c 调用。

用法（见 docs/naming-and-distribution.md 的传播清单）：
    GUANJIA_SERVER=… GUANJIA_TOKEN=… asciinema rec docs/demo.cast -i 2 \
        -c "python scripts/record_demo.py" --overwrite
"""

import os
import sys
import time

import pexpect

LINES = [
    "有哪些工作流？",
    "跑一下GPU日报，哪张卡显存占用最高？",
]

child = pexpect.spawn("guanjia", env={**os.environ}, timeout=240)
child.setwinsize(28, 96)
child.logfile_read = sys.stdout.buffer

child.expect("❯".encode("utf-8"))
for line in LINES:
    time.sleep(1.0)
    for ch in line:
        child.send(ch.encode("utf-8"))
        time.sleep(0.05)
    time.sleep(0.6)
    child.sendline("")
    child.expect("❯".encode("utf-8"), timeout=240)
time.sleep(1.2)
child.sendline("/quit")
child.expect(pexpect.EOF)
