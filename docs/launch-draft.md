# 首发材料草稿（Show HN / V2EX / 掘金）

> 依据 docs/naming-and-distribution.md 的传播清单。发布时机：GitHub 仓库公开后。

## Show HN 标题（候选，忌最高级形容词）

1. `Show HN: Guanjia – tell your terminal what you need, get a running workflow`
2. `Show HN: Guanjia (管家) – a workflow butler CLI, self-hosted backend`

## 首条自评论（发帖 5 分钟内补，动机+细节+求反馈）

Hi HN — guanjia (管家, "butler" in Chinese) is a thin CLI over a self-hosted
workflow platform. You describe what you need in plain language; a server-side
agent builds an actual workflow (schema-validated nodes, acceptance tests
anchored to real numbers from your sample data), publishes it, and it keeps
running on schedule.

Why another agent CLI: coding agents produce code; workflow engines' CLIs do
YAML sync. We wanted "say it → it exists and keeps running". Some design
choices we'd love feedback on:

- The agent loop runs server-side; the CLI is a dumb REPL. Every tool action
  is audited — the client cannot fake results.
- Builds are incremental API operations, never one-shot JSON generation.
  Malformed proposals are rejected at the boundary and retried (we measure
  this rejection rate — it's how weak models stay usable).
- Zero-dependency pure-Python client; `uvx guanjia` to try without install.

Stack: FastAPI + SQLite backend (self-hosted), DeepSeek/any OpenAI-compatible
model, local models via vLLM supported.

## 中文社区帖（V2EX/掘金）要点

- 标题：「说一句话，得到一个每天 8 点自动跑的工作流——开源了一个终端工作流管家」
- 首屏放 demo GIF；强调自托管、审计台账、验收测试锚定真实数字；
- 结尾附"和 aichat/n8n 的区别"表（摘自 alternatives.md）。

## 发布检查单

- [ ] GitHub 仓库公开 + topics（cli, workflow, agent, self-hosted, llm）
- [ ] PyPI 发布 0.1.0（uv publish）
- [ ] README 英文段落（安装+定位，中英双语首屏）
- [ ] 周二至周四 8-10AM PT 发 Show HN，48 小时内全回复
