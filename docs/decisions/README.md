# 技术决策记录

做过的选择与**当时的理由**。之所以留着，是因为半年后回头看
「为什么不用 X」比「我们用了 Y」更有用——尤其是当有人来提
「你们为什么不加个 --host 就完事」这类问题时。

| 决策 | 结论 |
| --- | --- |
| [desktop-shell.md](desktop-shell.md) | 不引桌面框架依赖，`web --app` 用 chromium 独立窗口 |
| [failure-alerts.md](failure-alerts.md) | 失败告知走三层：离场 webhook / 在场通知 / 日报工作流；否决本地常驻轮询 |
| [naming-and-distribution.md](naming-and-distribution.md) | 命名与分发渠道的选择 |
