"""要不要上色，只判一次。

真机 2026-08-30 撞到的：`NO_COLOR=1 guanjia doctor | head` 照样吐出
`\x1b[32m✓\x1b[0m`。色码在三个模块里各写各的（contract、doctor、cli
各一套常量，加起来 96 处），而**没有任何一处问过"现在该上色吗"**——
管道里、重定向进文件里、NO_COLOR 环境变量下，一律照上。

这对一个要给别人用的命令行工具是硬伤：输出进不了 grep、进不了日志、
进不了 CI 的比对。NO_COLOR 是社区约定（no-color.org），认它是本分。
`guanjia today` 那条路碰巧没事——它把样式整个丢掉、永远打素色，
是 overview_view 里写明的设计（"REPL 要暗色、CLI 要素色"），不是这个问题。

判据放一处，三个模块拿同一份：关掉时这些函数回空串，
96 个调用点一个字都不用改。

**判据不在这个模块里验收**：常量是导入时算出来的，测试改完环境变量
再导入已经晚了。所以正经的那条测试是起子进程真跑一次
（tests/test_no_color_is_honoured.py），和 REPL 那条线一个路子。
"""

from __future__ import annotations

import os
import sys
from typing import Any


def use_color(stream: Any = None) -> bool:
    """现在该不该上色。

    优先级照社区惯例：NO_COLOR 一票否决（**只看设没设，不看值**，
    约定如此），FORCE_COLOR 一票通过（CI 里想留色的人要有出口），
    都没有就看输出是不是终端。
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:      # noqa: BLE001 - 拿不准就不上色：多余的色码比少了更烦人
        return False


def seq(code: str) -> str:
    """一个裸转义序列（当前缀/后缀用）。不上色时是空串。"""
    return f"\x1b[{code}m" if use_color() else ""


def paint(code: str, text: str) -> str:
    """把一小段文字整个上色。不上色时原样返回。"""
    return f"\x1b[{code}m{text}\x1b[0m" if use_color() else text
