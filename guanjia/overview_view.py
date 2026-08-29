"""「今日统筹」那一屏，只写一份。

`guanjia today` 和 REPL 里的 `/today` 各自渲染过一遍同一份 overview，
于是**慢慢长歪了**（2026-08-29 对比）：

  guanjia today 有、REPL 没有：近 7 日趋势条、体检里不正常的那几条、
                              失败列 5 条（REPL 3 条）、"为什么失败"的下一步提示、
                              进行中为 0 时不显示那一栏
  REPL 有、guanjia today 没有：定时的"最近触发"日期

也就是说**招牌的那条路（REPL）反而少了最有用的一块**（趋势条和体检）。
两份各改各的，谁也不知道对方少了什么——failures.py 当初被抽出来就是
这个理由，那段注释写着"以后措辞要改，改一次三处都跟着变"。

这里回同一份行，样式交给调用方：REPL 要暗色、CLI 要素色，
但**内容必须一致**。每行是 (样式, 文本)，样式取
"" 正常 / "dim" 次要 / "bad" 报错色。
"""

from __future__ import annotations

from typing import Any

from .failures import more_kinds_note, summarize

Line = tuple[str, str]


def _cell(day: dict[str, Any]) -> str:
    other = day.get("other", 0)
    total = day["ok"] + day["fail"] + other
    if not total:
        return "·"
    if not day["ok"] and not day["fail"]:
        return "○"          # 跑了但都没出结果（排队/进行中/暂停）
    if day["fail"] > day["ok"]:
        return "✕"
    return "△" if day["fail"] else "✓"


def render(overview: dict[str, Any], *, failures_shown: int = 5,
           health: dict[str, Any] | None = None) -> list[Line]:
    """把 overview（可选加体检）渲染成一屏。

    failures_shown 留成参数：REPL 里屏幕短，列 3 条；命令行列 5 条。
    这是**展示密度**的差别，不是内容的差别——内容两边必须一样。
    """
    runs = overview["runs_today"]
    running = runs.get("running", 0)
    lines: list[Line] = [(
        "",
        f"今日运行 {runs['total']}（✓{runs['succeeded']} ✕{runs['failed']}"
        + (f" ⋯{running}" if running else "")
        + f"）· 已发布 {overview['published_workflows']} "
          f"· 生成中 {overview['builds_active']}",
    )]

    week = overview.get("week") or []
    if week:
        lines.append((
            "dim",
            "  近7日 " + " ".join(f"{w['date'][5:]}{_cell(w)}" for w in week)
            + "  （✓全成 △有失败 ✕失败居多 ○未出结果 ·无运行）",
        ))

    for schedule in overview.get("schedules") or []:
        fired = schedule.get("last_fire_date") or "—"
        lines.append((
            "dim",
            f"  ⏰ {schedule['workflow']} 每天 {schedule['at']} "
            f"{schedule['timezone']}（最近触发 {fired}）",
        ))

    failures = overview.get("recent_failures") or []
    if failures:
        # 这一栏是「最近」不是「今天」——顶上写着今日运行，不说清楚会被当成今天的
        lines.append(("dim", "  最近的失败："))
    for item in failures[:failures_shown]:
        head, tail = summarize(item)
        lines.append(("bad", f"  ✕ {head}"))
        lines.append(("dim", f"      {tail}"))
    note = more_kinds_note(overview, shown=failures_shown)
    if note:
        lines.append(("dim", f"  {note}"))

    for item in [i for i in (health or {}).get("items", [])
                 if i.get("state") != "ok"][:5]:
        mark = "✕" if item["state"] == "broken" else "⏸"
        lines.append(("bad", f"  {mark} {item['workflow']}：{item['reason']}"))
    # 发布了却一次都没跑过的单独说：它们没坏，但也没有任何证据说明它好
    never_ran = (health or {}).get("never_ran") or []
    if never_ran:
        names = "、".join(never_ran[:3])
        more = f" 等 {len(never_ran)} 个" if len(never_ran) > 3 else ""
        lines.append(("dim", f"  ⃝ {names}{more} 还没跑过，好不好还看不出来"))

    if failures:
        lines.append(("dim", "  （想知道为什么失败：guanjia 里问「run <编号> 为什么失败」）"))
    return lines
