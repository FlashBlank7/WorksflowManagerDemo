# 首发材料草稿（Show HN / V2EX / 掘金）

> 依据 docs/naming-and-distribution.md 的传播清单。发布时机：GitHub 仓库公开后。
> 最后对齐：0.6.1（2026-08-28）。**帖子里的每个数字都必须是当时跑出来的真实值**，
> 不要抄这里的旧数——它们是写稿时的真值，发布前重新测一遍再填。

## Show HN 标题（候选，忌最高级形容词）

1. `Show HN: Guanjia – tell your terminal what you need, get a running workflow`
2. `Show HN: Guanjia (管家) – a workflow butler CLI, self-hosted backend`

## 首条自评论（发帖 5 分钟内补：动机 + 具体设计 + 求反馈）

Hi HN — guanjia (管家, "butler") is a thin CLI over a self-hosted workflow
platform. You describe what you need in plain language; a server-side agent
builds an actual workflow (schema-validated nodes, acceptance tests anchored to
real numbers from your sample data), publishes it, and it keeps running on
schedule.

Why another agent CLI: coding agents produce code; workflow engines' CLIs do
YAML sync. We wanted "say it → it exists and keeps running".

What I'd actually like feedback on:

- **The agent loop runs server-side; the CLI is a dumb REPL.** Every tool call
  is audited — the client cannot fake results. Downside: you must self-host the
  backend. Is that trade the right one for this kind of tool?
- **Builds are incremental validated operations, never one-shot JSON.**
  Malformed proposals get rejected at the boundary and retried. This is what
  makes small/cheap models usable; we measure the rejection rate as a signal.
- **It can repair its own workflows.** When a published workflow starts
  failing, the health check names it with the reason, and you can say "X is
  broken, fix it" — the builder works on the *existing* draft rather than
  regenerating. In one real case it found a deeper root cause than the error
  message pointed at.
- **The block library decides how good the builder can be.** Concrete example:
  the formula engine had no string functions, so "count lines in this text"
  had no deterministic path — the builder spent 24 minutes exploring dead ends
  and fell back to asking an LLM to count (non-deterministic *and* billed per
  run). Adding `trim/split/count` took the same build down to 40 seconds.
  A/B write-up in the repo. I think this generalizes: for agent-built systems,
  capability gaps in the primitives cost more than model quality does.

Stack: FastAPI + SQLite backend (self-hosted), DeepSeek / any OpenAI-compatible
model, local models via vLLM. Client is zero-dependency pure Python —
`uvx guanjia` to try without installing.

Known limits (in the repo's known-defects doc, not hidden): single model
provider, training support is one narrow case, no mobile testing, and the
"enterprise" story is a self-hosted deployment rather than anything managed.

## 中文社区帖（V2EX / 掘金）要点

- 标题：「说一句话，得到一个每天 8 点自动跑的工作流——开源了一个终端工作流管家」
- 首屏放 demo GIF（现在演的是 doctor → today → 对话跑通的完整故事）
- 三段结构：
  1. **它是什么**：说人话 → 得到活的工作流；本地零依赖薄壳 + 自托管远端
  2. **坏了怎么办**：体检点名（跑不通 / 定时没开火，带原因）→ 对话里说"帮我修"
     → 莉莉丝在原工作流上改并补验收用例。这段最好放真实截图
  3. **为什么值得看**：积木能力决定搭建质量的 A/B（24.4 分钟 → 40 秒），
     以及"客户端不可能伪造结果"的审计设计
- 结尾附「和 aichat / n8n 的区别」表（摘自 alternatives.md）

## 发布前必须重跑的验证（数字要真）

```bash
# 平台侧
.venv/bin/pytest tests/ -q                      # 记录通过数
.venv/bin/python scripts/smoke_concierge.py --run-workflow <名字> --inputs "..."
# 客户端
python3 -m unittest discover tests              # 记录通过数
python3 scripts/smoke_cli.py --workflow <名字> --input "..."
# 打包
uv build && 干净 venv 装 wheel 后跑 --version / --help
```

## 发布检查单

- [ ] GitHub 仓库公开 + topics（cli, workflow, agent, self-hosted, llm）
- [ ] README 中英双份、demo GIF 能在 GitHub 上正常播放（<500KB）
- [ ] CHANGELOG 定稿到发布版本，known-defects 诚实列出边界
- [ ] PyPI 发布并实测 `uvx guanjia --version`
- [ ] 一键体验路径可用：注册令牌 + 自助注册的说明写清楚
- [ ] 帖子里的每个数字重新测过（测试数、A/B 秒数、体积）
- [ ] 准备好回答："为什么要自托管？"「和 n8n 有什么不同？」
      "小模型真的能搭出可用的工作流吗？"（有 A/B 和实验记录可引）

## 写稿时的真值（2026-08-28，仅供参考，发布前重测）

| 项 | 值 |
| --- | --- |
| 平台测试 | 591 通过 |
| 客户端测试 | 82 通过 |
| demo GIF | 401 KB |
| 真机已发布工作流 | 14 |
| 公式字符串 A/B | 24.4 分钟 → 40 秒（36×） |
| 自愈实测 | 6 次全败的工作流 → v3，两次真跑成功 |
| 两轮多智能体审计 | 41 智能体 · 32 条候选 · 30 条确证并修复 |
