"""截字符串只有一个规矩：截了要说。

2026-08-30 这一天在两个仓里数出七处「干净地砍掉」：平台的 _brief_error
（110 字）、平台告警（500）、平台动作行（30）、客户端失败行（60）、
网页壳（60）、`guanjia run` 的产出与报错（500 / 300）、体检的跳过原因（160）。
每一处单看都无所谓，合起来是同一句话：**看的人分不出这是全文还是半截**。

而这条线上最能照着做的一句常常在末尾——平台那边量过，227 条失败里
超过 500 字的 4 条，被砍掉的尾巴恰好是「要么让节点 X 真正产出…」。

所以规矩收在这一处：短的原样返回，长的缀一个省略号。
不解决"看不到全文"，但至少让人知道**有全文**。
"""

from __future__ import annotations

from typing import Any


def clip(text: Any, limit: int) -> str:
    """长过 limit 就截，并缀上省略号。省略号加在 limit 之外，不挤掉正文。"""
    body = "" if text is None else str(text)
    return body if len(body) <= limit else body[:limit] + "…"
