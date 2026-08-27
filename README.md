# bench — 本地工作台（远端服务客户端）

本地电脑运行的壳：界面 + 插件注册。**所有能力由远端 Lilies 平台提供**——
一般任务（对话）、工作流生成（莉莉丝）、工作流运行与历史，本地不跑模型、
不执行工作流、不存业务数据。前作 deck（本地执行的播放器）已废弃，本项目
是客户端架构的重来。

## 北极星

甜蜜好用的工作流工具：**生成 + 统筹管理，CLI 对话管家是招牌特性**。持续开发。

## 安装与运行

```bash
uv tool install bench-workbench   # 或 pipx install bench-workbench（发布后）
bench                             # 对话管家 REPL（招牌）
bench --login                     # 终端登录/注册
bench today                       # 一眼统筹总览
bench web                         # 本地网页壳 http://127.0.0.1:7800
```

开发期从源码：`uv tool install --from ~/code/bench bench-workbench`。

首次打开是登录页：**注册 = 共享注册令牌 + 自定用户名密码**（首个注册者自动成为
管理员），登录后本地只存会话令牌（`~/.bench.json`），密码不落盘。

### CLI 管家（招牌）

```bash
python3 -m bench.cli            # 网页登录过直接用；否则 --login 终端登录
❯ 跑一下GPU日报，哪张卡显存最高
  ⚙ run_workflow → ✓ report=卡0｜…
● 卡1 和卡2 显存占用最高（94%）…
```

语言理解与全部工具执行都在远端（/api/v1/assistant/agent），CLI 是薄 REPL。

## 结构

- `bench/remote.py` — 远端唯一通道（urllib，零依赖）
- `bench/plugins/` — 插件层：`assistant`（一般任务）、`workflow`（生成+管理）
- `bench/app.py` — localhost 单页壳（对话 / 工作流两个视图）

## 尚未做

打包成桌面安装物（当前需要 Python3）、SSE 实时构建流（当前轮询）、
多远端配置、业主提问的应答通道（构建中 ask_owner 的回复入口）。
