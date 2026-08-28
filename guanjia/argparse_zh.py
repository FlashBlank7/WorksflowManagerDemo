"""说人话的 argparse。

标准 argparse 缺参数时吐的是：

    usage: guanjia run [-h] [--json] [--wait WAIT] [--follow] name [pairs ...]
    guanjia run: error: the following arguments are required: name

一句中文没有，而 `guanjia run` 不带参数是最常见的一种误操作。
这里把 error() 换掉：说清缺了什么、怎么补，再把原用法附在后面
（用法行里有 --json --wait 这些，还是有用的）。
"""

from __future__ import annotations

import argparse
import re
import sys

# argparse 的英文报错 → 人话
_PATTERNS = (
    (r"the following arguments are required: (.+)",
     "还缺参数：{0}"),
    (r"unrecognized arguments: (.+)",
     "不认识这些参数：{0}"),
    (r"argument (\S+): invalid (\w+) value: (.+)",
     "参数 {0} 要填{1}，你给的是 {2}"),
    (r"argument (\S+): expected one argument",
     "参数 {0} 后面要跟一个值"),
    (r"invalid choice: (.+?) \(choose from (.+)\)",
     "{0} 不是可选值；可选的是 {1}"),
)


# 类型名也是给机器看的：用户不该看到 float / int。
_TYPE_WORDS = {"float": "数字", "int": "整数", "str": "文字"}


class ChineseArgumentParser(argparse.ArgumentParser):
    def _describe(self, dest: str) -> str:
        """参数名后面补上它的说明——「name」本身对用户没有意义。"""
        for action in self._actions:
            if action.dest == dest or dest in (action.option_strings or []):
                if action.help:
                    # 用「——」而不是再套一层括号：说明里本来就常带括号，
                    # 嵌起来是「name（工作流名字（支持唯一子串）或 id）」，没法读
                    return f"{dest} —— {action.help}"
        return dest

    def error(self, message: str) -> None:  # type: ignore[override]
        said = message
        for pattern, template in _PATTERNS:
            match = re.search(pattern, message)
            if not match:
                continue
            parts = list(match.groups())
            if template.startswith("还缺参数"):
                parts[0] = "、".join(self._describe(d.strip())
                                     for d in parts[0].split(","))
            if len(parts) > 1:
                parts[1] = _TYPE_WORDS.get(parts[1], parts[1])
            said = template.format(*parts)
            break
        print(f"{self.prog}：{said}", file=sys.stderr)
        print(self.format_usage().strip(), file=sys.stderr)
        sys.exit(2)

