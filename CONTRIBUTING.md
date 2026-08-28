# 参与开发

先说结论：**没有后端也能改大部分东西**。真机相关的检查会明确告诉你它跳过了，
不会假装通过。

## 五分钟跑起来

```bash
git clone <repo> && cd guanjia
python3 -m guanjia --version          # 零依赖纯标准库，不用装任何东西
python3 -m unittest discover tests    # 全部测试，十几秒
python3 scripts/check_cold_paths.py   # 冷门环境自检（含网页壳 JS 语法）
```

两条都绿就说明环境没问题。**没有后端时这两条照样全绿**——
它们用的是内置的桩服务器，不碰网络。

## 有后端的话再跑这些

```bash
python3 -m guanjia --login                                   # 连上你的后端
python3 scripts/smoke_cli.py --workflow <名字> --input "k=v"  # 各子命令打真实后端
```

没登录时 `smoke_cli.py` 会**退出码 2 并说清楚跳过了什么**，
不会给你一个虚假的绿灯。这是刻意的：冒烟脚本自己撒谎比没有冒烟更糟。

## 改代码时的约定

**测试跟着走。** 新行为要有测试；修 bug 要先有一条能复现它的测试。
判断标准很简单：**把 bug 放回去，测试必须报错**——不然那条测试只是让人安心的摆设。
这个反向验证在本项目救过好几次场（有一次写完冒烟脚本自测，
把 bug 放回去竟然通过了，因为判据用的是启发式而不是对照权威来源）。

**冷门路径要真跑。** 单元测试的环境恰好是"正常"的那一种——有 readline、
有 tty、不在 SSH 里、HOME 可写。这些分支里藏过一个 `os` 未导入的 bug，
线上一直没炸，用户在 SSH 里跑就崩。改了跟环境相关的代码，跑一遍
`check_cold_paths.py`。

**界面改动对照 [docs/design.md](docs/design.md)。** 尤其这条：
颜色只用来表达状态，品牌不占颜色。

**不造代号。** 用户看得见的地方不要出现只有我们懂的名字。

## 提交前

```bash
python3 -m unittest discover tests    # 必须绿
python3 scripts/check_cold_paths.py   # 必须绿
```

注意这两条命令**不要放进管道**（`… | tail` 会用 tail 的退出码顶替失败码，
本项目为此吃过两次带病提交的亏）。

## 目录长什么样

```
guanjia/
  __main__.py     子命令分发（bare / web / today / run / rerun / export / import / …）
  cli.py          对话 REPL：招牌功能
  app.py          网页壳：本地 HTTP 服务 + 25 条路由
  runcmd.py       run / rerun / export / import 的命令行实现
  doctor.py       连接自检
  remote.py       与后端的唯一通道（urllib，零依赖）
  config.py       多远端档案
  sessions.py     会话本地存储
  plugins/        工作流与对话两个能力面
  web/            index.html / app.js / style.css（打包进 wheel）
docs/             见 docs/README.md 索引
scripts/          冒烟与自检脚本，每个文件头写着它为什么存在
tests/            全部零依赖；数量不写死在这里，写死就会过期
```

## 报问题

带上 `python3 -m guanjia doctor` 的输出——它会说清楚是配置、网络、
后端版本还是本地存储的问题，比"用不了"有用得多。
