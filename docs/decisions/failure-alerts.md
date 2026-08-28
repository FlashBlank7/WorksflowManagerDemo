# 失败可感知：调研结论（v0.4 ②，2026-08-28）

问题：定时工作流半夜失败，用户第二天才在 today 里看见。要主动告知。

## 四条路线的权衡

| 路线 | 判定 | 理由 |
| --- | --- | --- |
| **A. 平台全局告警 webhook** | ✅ 主路径 | 能力在远端、无本地常驻、覆盖所有客户端；URL 指向钉钉/飞书/Slack incoming webhook 或自建收口，企业版好落地 |
| **B. 本地 `today --watch` 常驻轮询** | ❌ 否决 | 破薄壳"本地不常驻不存业务"底线；终端一关就瞎 |
| **C. 摘要工作流自举** | ✅ 过渡/补充 | 零平台改动：用平台自己的 schedule_trigger 让构建智能体搭「每日失败摘要」工作流（对话里一句话即可）；非实时，但今天就能用 |
| **D. Web 在场通知** | ✅ 增强 | 页面开着时 overview 轮询发现新失败 → 浏览器 Notification + 侧栏红点；本地零依赖，覆盖"盯着看"场景 |

## 实现定案

**A（平台侧，一个 tick）**
- `Settings.alert_webhook_url`（env `ALERT_WEBHOOK_URL`，默认空=关闭）
- 挂点：workflow_runtime 运行收尾 `status="failed"` 处，fire-and-forget POST
  `{"kind":"run_failed","workflow":名,"application_id","run_id","error","at"}`
- 纪律：3s 超时、异常只记日志——**告警失败绝不影响运行本身**；正式运行才发
  （构建/测试运行不发）
- 验证：本地 stub HTTP 收一发真失败运行

**D（guanjia Web 侧，一个 tick）**
- 已在统筹页的轮询里比对 `recent_failures` 新增项；新失败 → 侧栏「统筹」项红点
  + `Notification`（权限被拒静默）

**C（文档即交付）**
- README/对话提示语：「给我建一个每天 9 点的失败摘要工作流，失败数>0 时列出
  工作流名和错误」——构建智能体可直接搭。

不做的：per-app 独立 webhook（等真实需求）、邮件通道（自建 SMTP 负担，webhook 网关可代转）。
