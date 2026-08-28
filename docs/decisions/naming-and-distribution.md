# 命名与分发决策（2026-08-27）

依据实查调研（PyPI JSON API 逐名验证）：

- **bench 三处全撞弃用**：PyPI `bench` 被 2015 年死项目占死；`frappe-bench` 安装的
  命令就叫 `bench`（与 ERPNext 生态直接冲突）；brew `bench` 是 Haskell 基准工具。
- **定名 guanjia（管家）**：PyPI 404 可用；与产品概念零翻译损耗；
  "guanjia (管家) — your workflow butler" 是记忆点。备选（均 PyPI 可用）：
  worksmith（有商标撞车风险）、zongguan、gongfang。
- **生态位**（综述背书）：对话式终端智能体只管改代码；工作流引擎 CLI 只会同步部署；
  "说人话→持续运行的工作流"是空位，workflow orchestration 被 2025 终端智能体
  全景综述列为未充分探索缺口。
- **分发**：主推 `uv tool install guanjia` + `uvx guanjia` 免装试用（零依赖是王牌）；
  curl 一行脚本发布时补；brew 等有星再上。
- **传播清单**：首屏 tagline+demo 动图（内容必须是"一句话→工作流跑通"15 秒，
  不要拍成聊天 REPL）→ 一行安装 → 对比页；Show HN 周二至四 8-10AM PT，
  发帖 5 分钟内自评论补动机与细节，48 小时全回复。
