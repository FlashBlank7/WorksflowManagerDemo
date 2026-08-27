# bench — 本地工作台（远端服务客户端）

本地电脑运行的壳：界面 + 插件注册。**所有能力由远端 Lilies 平台提供**——
一般任务（对话）、工作流生成（莉莉丝）、工作流运行与历史，本地不跑模型、
不执行工作流、不存业务数据。前作 deck（本地执行的播放器）已废弃，本项目
是客户端架构的重来。

## 运行

```bash
python3 -m bench.app --server http://<平台地址>:8000 --token <API_TOKEN>
# 打开 http://127.0.0.1:7800
```

配置也可写 `~/.bench.json`：`{"server": "http://…:8000", "token": "…"}`。

## 结构

- `bench/remote.py` — 远端唯一通道（urllib，零依赖）
- `bench/plugins/` — 插件层：`assistant`（一般任务）、`workflow`（生成+管理）
- `bench/app.py` — localhost 单页壳（对话 / 工作流两个视图）

## 尚未做

打包成桌面安装物（当前需要 Python3）、SSE 实时构建流（当前轮询）、
多远端配置、业主提问的应答通道（构建中 ask_owner 的回复入口）。
