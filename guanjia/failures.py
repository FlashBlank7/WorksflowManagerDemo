"""失败清单怎么写给人看。

/api/v1/overview 的 recent_failures 是**按原因合并**过的：一行代表
「某工作流因为某个原因失败过 N 次」，count 是合计，at 是最近那一次。

原来三处出口都写成 `工作流 ×13 @2026-08-28T10:03:36`。
这行字有歧义，而且是会被读错的那种：13 和一个具体时刻贴在一起，
读起来像"那天失败了 13 次"或"那一刻失败了 13 次"。
真值是"这个毛病前后一共 13 次，最近的一次在那个时刻"。

同一个歧义先在服务端被抓到过——管家把 count 读成了当天的次数，
于是给模型的那一份把字段改成了「这个原因一共出现过几次」
「最近一次失败在」。但 CLI、REPL、网页三处照旧，
也就是说**闸只装在一个出口上**。这个模块就是那个共用的出口。

放在一处还有个好处：以后措辞要改，改一次三处都跟着变。
"""

from __future__ import annotations


def _when(at: str) -> str:
    """2026-08-28T10:03:36+00:00 → 08-28 10:03。读不动就原样返回。"""
    text = str(at or "").strip()
    if len(text) >= 16 and text[4] == "-" and text[10:11] in ("T", " "):
        return f"{text[5:10]} {text[11:16]}"
    return text or "时间不详"


def summarize(failure: dict) -> tuple[str, str]:
    """一条失败 → (主行, 细节行)。细节行可能为空串。

    主行放**人最关心的两样**：哪个工作流、什么毛病。
    次数和时刻挪到细节行并各自带上说明词，谁也贴不到谁身上。
    """
    workflow = str(failure.get("workflow") or "某个工作流")
    error = str(failure.get("error") or "").strip() or "没有留下原因"
    # 截了要说。这一行放不下长报错，但**干净地砍掉**会让人分不出
    # 这是全文还是半截话——而这条线上最能照着做的一句常常在末尾
    # （平台那边 2026-08-30 也是同一个毛病，同一天一起修的）。
    head = f"{workflow}  {error if len(error) <= 60 else error[:60] + '…'}"

    count = failure.get("count") or 1
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 1
    when = _when(failure.get("at") or "")
    run_id = str(failure.get("run_id") or "")
    tail = f"最近一次 {when}" if count <= 1 else f"同样的毛病 {count} 次，最近一次 {when}"
    if run_id:
        tail += f" · run {run_id}"
    return head, tail


def more_kinds_note(overview: dict, *, shown: int) -> str:
    """列表截了就说一句，没截就返回空串。

    面板一屏只放得下几行，而"几行"很容易被读成"就这些"——
    第 6 种毛病可能才是要命的那个。远端给了总数
    （recent_failures_total）就照它说；老远端没有这个字段时，
    只能拿手里这批的条数保守判断，判不出来就不吭声：
    **宁可不说，也不能说错**，谎报"没有更多"比不提更糟。
    """
    rows = overview.get("recent_failures") or []
    total = overview.get("recent_failures_total")
    if not isinstance(total, int):
        total = len(rows)          # 老远端：至少别把手里这批说漏了
    hidden = total - min(shown, len(rows))
    if hidden <= 0:
        return ""
    return f"（还有 {hidden} 种别的毛病没列出来）"
