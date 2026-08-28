# 文档索引

## 先读这些（用户向）

| 文档 | 回答什么问题 |
| --- | --- |
| [../README.md](../README.md) | 它是什么、能替我做什么、怎么装 |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | 想改代码：怎么跑起来、怎么验 |
| [known-limits.md](known-limits.md) | **它现在做不到什么** —— 装之前值得先看 |
| [alternatives.md](alternatives.md) | 和 aichat / n8n / windmill 有什么区别 |
| [design.md](design.md) | 界面与语气的取舍（改 UI 前对照着来） |

## 项目自己的记录（开发向）

| 文档 | 内容 |
| --- | --- |
| [roadmap.md](roadmap.md) | 做过什么、接下来打算做什么 |
| [../CHANGELOG.md](../CHANGELOG.md) | 每个版本改了什么 |
| [decisions/](decisions/) | 做过的技术决策与当时的理由 |
| [launch-draft.md](launch-draft.md) | 发布材料草稿（未发布） |

## 检查脚本

仓库里的三个脚本是可以直接跑的，出问题时比读文档快：

```bash
python3 scripts/smoke_cli.py --workflow <名字> --input "k=v"   # 各子命令真机冒烟
python3 scripts/check_cold_paths.py                            # 冷门环境自检（22 项）
python3 scripts/record_demo.py                                 # 重录 demo（见文件头）
```

每个脚本的文件头都写了**它为什么存在**——通常对应一次真实事故。
