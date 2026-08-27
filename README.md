# guanjia（管家）

> **终端里说人话，远端工厂替你造出能跑、有定时、可监控的工作流。**
> guanjia (管家) — your workflow butler in the terminal.

```text
❯ 每天早上8点生成服务器GPU状态日报
  ⚙ generate_workflow → ⚙ 构建已提交
● 莉莉丝已开工。搭好后它会出现在你的工作流列表里，每天 8:00 自动运行。

❯ 跑一下GPU日报，哪张卡显存占用最高
  ⚙ run_workflow → ✓ report=卡0｜NVIDIA RTX 6000 Ada…
● 卡1 和卡2 显存占用最高（94%）——都是 vLLM 占的。
```

<!-- TODO: 15 秒 demo 动图：一句话 → 远端生成 → 工作流真的跑起来 -->

## 为什么是它

对话式终端智能体（aichat/gptme/open-interpreter）只管改代码和操作电脑；
工作流引擎的 CLI（n8n/windmill/temporal）只会 YAML 和同步部署。
**"说人话 → 得到一个持续运行的工作流"这条线是空的**——guanjia 补的就是这个：

- **生成**：自然语言需求 → 远端莉莉丝自动搭建、测试、发布（不是生成代码给你抄，是交付能跑的东西）
- **统筹**：`guanjia today` 一眼今日运行/定时任务/失败聚合
- **薄壳**：本地零依赖纯 Python，不跑模型、不存业务数据，一切能力来自你自托管的远端平台

## 安装

```bash
uv tool install guanjia    # 推荐
uvx guanjia                # 不装直接试
pipx install guanjia       # 或者
```

## 使用

```bash
guanjia            # 对话管家 REPL（招牌）
guanjia --login    # 终端登录/注册（注册 = 团队注册令牌 + 自定用户名密码）
guanjia today      # 不进 REPL，一眼统筹总览
guanjia web        # 本地网页壳 http://127.0.0.1:7800
```

首次使用注册：管理员给你团队的注册令牌，用户名密码自己定，**首个注册者自动成为管理员**。
本地只存会话令牌（`~/.guanjia.json`），密码不落盘。

## 与近邻的区别

| 工具 | 它做的 | guanjia 的不同 |
| --- | --- | --- |
| aichat / gptme | 终端对话，改代码、跑命令 | 对话产出的是**持续运行的工作流**，不是一次性执行 |
| n8n / windmill CLI | 工作流引擎的运维同步面 | 我们的 CLI 是**对话式**的，生成和管理都说人话 |
| claude-code 类 | 编码智能体 | 面向**业务交付物**（报表/对账/监控），不是代码库 |

## 架构（本地薄壳 + 远端工厂）

```text
guanjia CLI/Web（本地，零依赖）
   │  唯一通道：HTTPS + 会话令牌
   ▼
Lilies 平台（自托管远端）：莉莉丝生成 · 工作流运行时 · 定时调度 · 审计台账 · 用户体系
```

语言理解与全部工具执行都在服务端（`/api/v1/assistant/agent`），CLI 是薄 REPL——
所以审计完整、客户端无法伪造结果。

## 开发

```bash
uv tool install --from ~/code/bench guanjia   # 源码安装
python3 -m guanjia                            # 或直接跑
```

MIT License.
