# guanjia（管家）

> **在终端里说人话，让它替你把工作流搭出来、并且一直跑下去。**
> guanjia (管家) — your workflow butler in the terminal.

用一句话描述要什么，得到的不是一段代码，而是**一个已经在跑的东西**：
有版本、有定时、失败了会告诉你、坏了能在对话里修。

```text
❯ 每天早上8点生成服务器GPU状态日报
  ⚙ generate_workflow → ⚙ 构建已提交
● 已经开始搭了。搭好后它会出现在你的工作流列表里，每天 8:00 自动运行。

❯ 跑一下GPU日报，哪张卡显存占用最高
  ⚙ run_workflow → ✓ report=卡0｜NVIDIA RTX 6000 Ada…
● 卡1 和卡2 显存占用最高（94%）——都是 vLLM 占的。
```

![guanjia demo](docs/demo.gif)

*真实录屏：`doctor` 一眼看平台状况 → `today` 看今日与七日趋势 → 对话里问工作流、跑一个拿到真数据。重录：见 `scripts/record_demo.py` 文件头。*

## 先说清楚：它需要一个后端

guanjia 本身是**薄客户端**——不跑模型、不存业务数据，装上它并不会凭空多出
一个工作流平台。所有能力来自一个你自己部署（或同事已经部署好）的后端。

这个取舍换来的是：智能体循环与每次工具调用都在服务端并入审计台账，
**客户端无法伪造结果**。代价也直说：没有托管版，先有后端才能开始。
接口清单与获取方式见[后端一节](#后端它连的是什么)。

## 为什么是它

对话式终端智能体（aichat / gptme / open-interpreter）只管改代码、操作电脑，
执行完就结束；工作流引擎的 CLI（n8n / windmill / temporal）面向已经会写
YAML 的工程师。**"说人话 → 得到一个持续运行的东西"这条线是空的。**

- **生成**：说需求 → 后端自动搭建、测试、发布。交付物是能跑的工作流，
  不是一段让你自己去接的代码
- **统筹**：`guanjia today` 一眼看今日运行、定时任务、失败聚合与七日趋势
- **发现与修复**：体检点名坏掉或停摆的工作流并说清原因；
  在对话里说一句「X 坏了帮我修」，它在原工作流上改而不是推倒重来
- **薄壳**：纯标准库零依赖，本地不跑模型、不存业务数据

## 安装

```bash
uv tool install guanjia    # 推荐
pipx install guanjia       # 或者
uvx guanjia --version      # 只想看看装没装上
```

装好之后直接敲 `guanjia`——**没有配过后端的话它会先告诉你需要什么**，
而不是一上来问你要服务器地址。

## 使用

```bash
guanjia            # 对话管家 REPL（招牌）
guanjia --login    # 终端登录/注册（注册 = 团队注册令牌 + 自定用户名密码）
guanjia today      # 不进 REPL，一眼统筹总览
guanjia web        # 本地网页壳 http://127.0.0.1:7800（--app 独立窗口 · --open 开浏览器）
guanjia remote     # 多远端档案：list / use <名> / add <名> [服务器] / rm <名>
guanjia doctor     # 哪里不对一查便知：配置 → 可达 → 登录态 → 会话存储
guanjia run GPU日报 --json   # 脚本/cron 直接跑工作流：名字子串即可，退出码可判
eval "$(guanjia completion bash)"   # Tab 补全（zsh 同理），run 后直接补工作流名
guanjia export GPU日报 && guanjia import GPU日报.guanjia.json --name 副本   # 搬运工作流
```

- **对话即操作**：流式回答；生成工作流时构建进度卡片就地跟踪，构建智能体提问直接在对话里答
- **会话持久化**：CLI 与 Web 共享 `~/.guanjia/sessions/`，重启接着聊，`/new` 开新对话
- **多远端**：公司/家里/测试环境各存一个档案，`/remote use` 一键切（env `GUANJIA_PROFILE` 可临时指定）
- **Web 壳同权同源**：登录、流式对话、markdown 渲染、构建跟踪、统筹面板、工作流表单自动渲染

首次使用注册：管理员给你团队的注册令牌，用户名密码自己定，**首个注册者自动成为管理员**。
本地只存会话令牌（`~/.guanjia.json`），密码不落盘。

## 后端：它连的是什么

guanjia 是**薄客户端**——不跑模型、不存业务数据。所有能力（构建智能体、
工作流运行时、定时调度、审计台账、用户体系）来自一个你自己部署的工作流平台。
这个取舍换来两件事：审计完整，且客户端无法伪造结果。

代价也说清楚：**没有托管版，你得先有一个后端**。

**已经有人在用了？** 找管理员要两样东西就够：

```
服务器地址（例：https://workflow.你的公司.com）
注册令牌（团队共享，用来自助注册账号）
```

然后 `guanjia --login`，用户名密码自己定。**首个注册者自动成为管理员。**

**要自己搭？** 后端需要提供这套 HTTP 接口（guanjia 只依赖它们）：

| 用途 | 接口 |
| --- | --- |
| 身份 | `POST /api/v1/auth/register` · `POST /api/v1/auth/login` · `GET /api/v1/me` |
| 对话 | `POST /api/v1/assistant/agent`（+ `/stream` 走 SSE） |
| 工作流 | `GET /api/v1/applications` · `/{id}/draft` · `/{id}/runs` · `POST /{id}/runs` |
| 构建 | `POST /{id}/builds` · `GET /api/v1/builds/{id}` · `POST /{id}/resume` |
| 统筹 | `GET /api/v1/overview` · `/api/v1/health-report` · `/api/v1/scheduler/health` |

带 `/health-report`、`/scheduler/health`、运行产物、有界事件列表的后端能让
guanjia 显示更多信息；**没有这些接口的老后端会静默降级而不是报错**，
详见[已知边界](docs/known-limits.md)。

参考实现是一个 FastAPI + SQLite 的自托管平台（构建智能体驱动 DeepSeek
或任何 OpenAI 兼容模型，也支持本机 vLLM）。想要现成的部署方式，
在 issue 里说一声——这部分正在整理成可独立发布的形态。

## 坏了能发现，也能修

**体检**：`guanjia doctor` 会点名坏掉（窗口内全败／最近连败）和停摆（有定时却没运行）
的工作流，带上最近一次失败原因；同一份体检在 `guanjia today`、Web 统筹页、
对话里（问「有什么坏了吗」）都看得到。

**修复**：对话里说「X 坏了帮我修」——构建智能体在**原工作流上**改（读现有草稿，
不推倒重来），把失败原因当线索定位，补上覆盖该故障的验收用例，通过后重新发布。
实测中它会顺带找出报错没指出的关联缺陷。

**告警**：三层，按需取用：

1. **离场**：平台 `.env` 设 `ALERT_WEBHOOK_URL=<钉钉/飞书/Slack incoming webhook>`，
   任何工作流运行失败即推 `{workflow, run_id, error, at}`（3s 超时，告警绝不影响运行）；
2. **在场**：Web 壳开着时自动轮询，新失败 → 统筹入口红点 + 浏览器通知；
3. **日报**：对话里说「给我建一个每天 9 点的失败摘要工作流，失败数>0 时列出
   工作流名和错误」——构建智能体直接搭一个。

## 与近邻的区别

| 工具 | 它做的 | guanjia 的不同 |
| --- | --- | --- |
| aichat / gptme | 终端对话，改代码、跑命令 | 对话产出的是**持续运行的工作流**，不是一次性执行 |
| n8n / windmill CLI | 工作流引擎的运维同步面 | 我们的 CLI 是**对话式**的，生成和管理都说人话 |
| claude-code 类 | 编码智能体 | 面向**业务交付物**（报表/对账/监控），不是代码库 |

## 架构（本地薄壳 + 远端工厂）

```text
guanjia CLI / Web（本地，零依赖纯标准库）
   │  唯一通道：HTTPS + 会话令牌
   ▼
工作流平台（你自己部署）：构建智能体 · 运行时 · 定时调度 · 审计台账 · 用户体系
```

语言理解与全部工具执行都在服务端（`/api/v1/assistant/agent`），CLI 是薄 REPL——
所以审计完整、客户端无法伪造结果。

## English

**guanjia** (管家, *butler*) — tell your terminal what you need, get a workflow
that actually runs, on schedule, with audit trails.

Unlike coding agents (which produce code) or workflow engines' CLIs (which sync
YAML), guanjia's deliverable is a *living workflow*: you describe a business
need in plain language, a server-side agent builds it on a self-hosted platform
— schema-validated nodes, acceptance tests anchored to real numbers from your
sample data — publishes it, and it keeps running.

```bash
uv tool install guanjia    # or: pipx install guanjia
guanjia                    # chat REPL — the signature feature
guanjia today              # one-glance ops: today's runs, schedules, failures
guanjia web                # local web shell (same account, streaming chat, dashboards)
guanjia remote             # multiple backend profiles: list / use / add / rm
guanjia doctor             # connectivity self-check with plain-language fixes
guanjia run <name> --json  # run a published workflow from scripts/cron
```

Sessions persist locally (`~/.guanjia/sessions/`, shared between CLI and web);
build progress and the builder's clarifying questions surface right in the chat.

Design choices worth knowing:

- **Thin client**: pure-Python, zero dependencies; the agent loop and every
  tool call run server-side and are audited — the client cannot fake results.
- **Honest by construction**: builds are incremental validated operations
  (never one-shot JSON), empty upstreams produce honest empty results, and
  the agent answers with numbers traceable to the ledger.
- **Self-hosted backend**: your models (DeepSeek or any OpenAI-compatible,
  local vLLM supported), your data, your audit log.

See [docs/alternatives.md](docs/alternatives.md) for detailed comparisons.

## 开发

```bash
python3 -m guanjia                    # 零依赖纯标准库，clone 下来就能跑
python3 -m unittest discover tests    # 103 个测试，十几秒
python3 scripts/check_cold_paths.py   # 冷门环境自检，22 项
```

**没有后端也能改大部分东西**，上面两条检查照样全绿（用的是内置桩服务器）。
详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

MIT License. · [English README](README.en.md) · [和近邻的详细对比](docs/alternatives.md) · [已知边界](docs/known-limits.md)
