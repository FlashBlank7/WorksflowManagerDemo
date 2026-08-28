# 桌面壳评估（v0.3 结论，2026-08-27）

## 结论：不引桌面依赖，`guanjia web --app` 用 chromium 系独立窗口

| 方案 | 代价 | 得到 | 判定 |
| --- | --- | --- | --- |
| **chromium `--app=URL`**（已实现） | 零依赖，~20 行 | 无地址栏独立窗口，任务栏独立图标 | ✅ v0.3 采用 |
| 纯浏览器标签页（现状保留） | 零 | 够用，服务器/远程场景唯一选择 | ✅ 默认行为不变 |
| pywebview | Linux 拖 pygobject/Qt 系统包，破坏"纯 Python 零依赖"卖点 | 原生窗口、托盘 | ⏸ 若 v0.4+ 要托盘/通知，作 `guanjia[desktop]` 可选 extra |
| tauri | 整条 Rust+Node 构建链，另一个发行世界 | 最佳桌面品质、自带更新器 | ⏸ 仅当做独立桌面发行版时立项 |
| Electron | 100MB+ 运行时 | 同 tauri 而更重 | ❌ 排除 |

## 理由

1. 产品卖点是**本地薄壳零依赖**——桌面壳不能反过来变成最重的一层；
2. guanjia 的界面本来就是本地 HTTP 页面，chromium `--app` 已经给出 90% 的"桌面感"；
3. bagpipe 这类无显示环境是主力部署场景，桌面壳必须是可选路径，不能进默认链路。

## 用法

```bash
guanjia web --open   # 启动后用默认浏览器打开
guanjia web --app    # 独立窗口（探测 chromium/chrome/edge/brave，找不到退回 --open）
```

无显示环境下两个 flag 都静默退化，服务照常监听。
