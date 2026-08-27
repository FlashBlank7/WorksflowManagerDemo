# Changelog

版本还未对外发布（PyPI 发布时从这里截取）。日期为完成日。

## 0.4.0 — 2026-08-28

看得清、追得到：

- **运行时间线**：详情页每条运行点开看全过程（节点耗时、错误标红）；
  平台新增有界事件列表端点 `/runs/{id}/events/list`
- **失败可感知（三层）**：平台全局 `ALERT_WEBHOOK_URL`（fire-and-forget，
  告警绝不影响运行）· Web 在场红点+浏览器通知 · 日报工作流一句话自举
- **近 7 日趋势**：overview 按日聚合，`guanjia today` 符号行 + Web 成败堆叠柱
- **Web 档案命名**：手动填写连接时可起名保存

## 0.3.0 — 2026-08-28

围绕「装上就顺手」的一轮：

- **多远端档案**：`~/.guanjia.json` 升级 profiles 格式（旧格式自动迁移），
  `guanjia remote list/use/add/rm`、REPL `/remote`、Web 登录页档案下拉（免密切换，
  令牌失效退回密码登录）；`GUANJIA_PROFILE` 临时指定
- **`guanjia run <工作流> [k=v…] [--json] [--wait N]`**：脚本/cron 的一次性出口，
  名字唯一子串解析、tty 交互补参、退出码 0/1/2/3
- **`guanjia doctor`**：连接自诊断（配置→可达+延迟→登录态→会话存储），
  人话结论 + 下一步命令
- **Tab 补全**：`eval "$(guanjia completion bash)"`（zsh 同理）；`run` 后补
  工作流名、`remote use/rm` 后补档案名
- **桌面壳**：`guanjia web --app` 独立窗口（chromium 系探测）/`--open`；
  评估结论见 docs/desktop-shell.md——不引桌面依赖
- **顶层 `--help`**：完整命令地图
- **回归测试套**：31 用例零依赖 unittest（config/sessions/doctor/run/completion/help），
  真 HTTP 桩覆盖成功/失效/不可达三态

## 0.2.0 — 2026-08-27

Web 壳与 CLI 补齐到同一能力面（六切片）：

- 前端资产化：内嵌巨串拆成 guanjia/web/ 真文件（打包内加载）
- Web 对话流式（SSE 经本地壳透传，失败自动回退）
- 生成跟踪 + 提问应答：对话内构建卡片，莉莉丝提问就地作答
- 会话持久化：`~/.guanjia/sessions/`，CLI 与 Web 共享
- 对话 markdown 渲染（表格/代码/列表/加粗，先转义后变换）
- 体验 pass：智能滚动、防双发、焦点管理、窄屏顶栏

## 0.1.0 — 2026-08-26

首个能用的整体：CLI 对话管家（流式 + 构建跟随 + 在场应答）、Web 壳
（登录/注册、对话、统筹面板、工作流表单自动渲染）、`guanjia today`、
共享注册令牌 + 自助注册（首位注册者为管理员）、零依赖纯标准库薄壳。
