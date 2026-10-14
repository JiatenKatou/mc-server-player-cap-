# 文件清单

- 版本：0.1.0
- 生成时间：2026-10-14 11:21:28
- 文件总数：46
- Python 代码行数合计：8370

分层：`1 配置 → 2 数据 → 3 解析 → 4 计算 → 5 呈现 → 6 界面 → 7 校准 → 8 验证`
依赖方向只能从高层指向低层；**不要出现低层反向 import 高层**。

## 1 配置层（系数）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/config.py` | 236 | ★ 木桶四个维度的全部可调系数 + CPU-Z 标定参数。改系数只改这里 |
| `mc_player_calc/cooling.py` | 200 | ★ 散热系数表（桌面散热器/笔记本模具/导热耗材）与移动端后缀规则 |
| `mc_player_calc/modpack.py` | 264 | ★ 整合包档案：一个包一套系数（校准值 / 预填值 / 兜底折算） |

## 2 数据层（CPU 库与标尺）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/cpu_data.py` | 573 | ★ CPU 型号库、CPU-Z↔指数换算、桌面/移动端识别、自定义型号存储与模糊匹配 |

## 3 解析层

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/parser.py` | 335 | 输入解析（内存/带宽/CPU/散热），把随手写的字符串变成结构化数值 |

## 4 计算层（木桶内核）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/engine.py` | 444 | ★ 木桶效应计算内核：四个维度、散热衰减、瓶颈判定、优化建议 |

## 5 呈现层（文本）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/report.py` | 75 | 纯文本报告渲染（网页明细 / CLI 输出 / GUI 明细共用） |

## 6 界面层（命令行）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/cli.py` | 625 | 命令行入口（带参数 / 交互问答 / --add-cpu / --feedback） |

## 6 界面层（桌面窗口）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/gui.py` | 955 | tkinter 桌面窗口（含 CPU 录入弹窗、反馈弹窗、测速按钮） |

## 6 界面层（网页服务）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/web.py` | 778 | ★ 本地网页服务：http.server + JSON 接口（options/calc/cooling/open-url/cpu/feedback） |

## 7 校准层（数据收集）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/feedback.py` | 926 | ★ 信息反馈收集：校验、存储、玩法系数汇总、agent 交付文件导出 |

## 7 校准层（系数反推）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/calibrate.py` | 434 | ★ 用实测数据反推 CPU 承载系数；能直接读反馈导出的 Markdown |

## 8 验证层

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/reset.py` | 430 | ★ 恢复默认：按类别清本地状态，先备份、可整组撤销 |
| `mc_player_calc/selftest.py` | 781 | 框架自检（170+ 断言） |

## 其它（文档 / 启动器 / 前端 / 测试 / 截图）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `.github/ISSUE_TEMPLATE/bug.yml` | 65 | — |
| `.github/ISSUE_TEMPLATE/config.yml` | 12 | — |
| `.github/ISSUE_TEMPLATE/data.yml` | 71 | — |
| `.gitignore` | 25 | — |
| `AGENTS.md` | 103 | ★ 面向 AI agent 的项目说明与硬约束 |
| `anchors.example.json` | 6 | 校准锚点格式示例（真实数据应存为 anchors.json，不入库） |
| `docs/screenshot.png` | 0 | 桌面窗口截图（桌面模式） |
| `docs/screenshot_mobile.png` | 0 | 桌面窗口截图（移动端 CPU + 散热联动） |
| `FILE_MANIFEST.md` | 164 | 本清单：每个文件干什么、多少行、能不能改 |
| `HANDOFF.md` | 273 | ★ 交接说明：现状、决策理由、待办、怎么验证 |
| `LICENSE` | 30 | MIT 许可证（含「估算值不是实测保证」的补充说明） |
| `mc_player_calc/__init__.py` | 20 | — |
| `mc_player_calc/__main__.py` | 36 | 入口路由：无参数=网页版，--gui=桌面窗口，其它=CLI |
| `mc_player_calc/web/app.js` | 802 | 网页前端逻辑（散热联动、结果渲染、录入器、反馈表单与导出） |
| `mc_player_calc/web/index.html` | 284 | 网页前端结构（计算表单 + CPU 录入器 + 反馈收集面板） |
| `mc_player_calc/web/style.css` | 379 | 网页样式（深色主题） |
| `PUBLISH.md` | 456 | ★ 发布到 GitHub 的操作手册（仓库名/简介/Topics/Release 文案） |
| `README.en.md` | 113 | 英文快速上手（功能/安装/测试/结构，详细文档指向中文） |
| `README.md` | 714 | ★ 面向使用者的完整说明（中文主文档，先读第 1、2、7、11 节） |
| `tools/capture_gui.py` | 136 | 开发辅助：抓窗口截图给文档用（PrintWindow） |
| `tools/check_readme_links.py` | 88 | 文档检查：README 的站内锚点与相对链接是否有效 |
| `tools/check_web_ids.py` | 80 | 前端静态检查：JS 引用的 id 是否都在 HTML 里 |
| `tools/gui_smoketest.py` | 111 | 桌面窗口联动与无裁切自测 |
| `tools/package.py` | 320 | — |
| `tools/verify_package.py` | 107 | — |
| `tools/web_smoketest.py` | 416 | 网页接口自测（真的起服务器打 HTTP，含反馈 API） |
| `启动计算器.cmd` | 24 | 本地网页版启动器（ASCII 兜底，双击可用） |
| `启动计算器.ps1` | 27 | 本地网页版启动器（推荐入口，UTF-8 BOM） |
| `命令行.cmd` | 20 | 命令行启动器（ASCII 兜底） |
| `命令行.ps1` | 15 | 命令行启动器 |
| `桌面窗口版.cmd` | 19 | 桌面窗口启动器（ASCII 兜底） |
| `桌面窗口版.ps1` | 14 | 桌面窗口启动器 |

## 校验值（前 12 位 SHA-256）

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `.github/ISSUE_TEMPLATE/bug.yml` | 1590 | `5c4746b044cc` |
| `.github/ISSUE_TEMPLATE/config.yml` | 726 | `e380559d9e42` |
| `.github/ISSUE_TEMPLATE/data.yml` | 2286 | `03f43e0f5adc` |
| `.gitignore` | 554 | `82e2e2d070c5` |
| `AGENTS.md` | 6298 | `1e02619c0a16` |
| `anchors.example.json` | 526 | `5d28b27a7590` |
| `docs/screenshot.png` | 242219 | `78fb5bbea69e` |
| `docs/screenshot_mobile.png` | 256698 | `72ef713675d2` |
| `FILE_MANIFEST.md` | 8056 | `28c44fec1b72` |
| `HANDOFF.md` | 16101 | `7188b6bd97b9` |
| `LICENSE` | 1546 | `7f4f2be18f3d` |
| `mc_player_calc/__init__.py` | 522 | `abcd96bff66b` |
| `mc_player_calc/__main__.py` | 1157 | `f9ec55ae8fcd` |
| `mc_player_calc/calibrate.py` | 19023 | `05bcb6a75d1f` |
| `mc_player_calc/cli.py` | 28903 | `7087007d116d` |
| `mc_player_calc/config.py` | 9825 | `20297032cb0e` |
| `mc_player_calc/cooling.py` | 8435 | `af7c86f5f932` |
| `mc_player_calc/cpu_data.py` | 23376 | `a5f2781ad0eb` |
| `mc_player_calc/engine.py` | 19690 | `8d9f2109d286` |
| `mc_player_calc/feedback.py` | 42942 | `e2af109a8c49` |
| `mc_player_calc/gui.py` | 47184 | `9c972334a994` |
| `mc_player_calc/modpack.py` | 9596 | `7c20729e165d` |
| `mc_player_calc/parser.py` | 13673 | `7d841068fe4a` |
| `mc_player_calc/report.py` | 3098 | `47b71f4c223b` |
| `mc_player_calc/reset.py` | 17192 | `d368f806134f` |
| `mc_player_calc/selftest.py` | 40418 | `016adb997909` |
| `mc_player_calc/web/app.js` | 30040 | `6be5e028c642` |
| `mc_player_calc/web/index.html` | 11911 | `16efda1fd760` |
| `mc_player_calc/web/style.css` | 7130 | `beaa3cbbf708` |
| `mc_player_calc/web.py` | 32757 | `8bbf7d4d730e` |
| `PUBLISH.md` | 16671 | `188ee2771e9e` |
| `README.en.md` | 5398 | `94fbf67243f8` |
| `README.md` | 40345 | `114ac8d7ed6d` |
| `tools/capture_gui.py` | 4639 | `8b30a80784e1` |
| `tools/check_readme_links.py` | 3444 | `d10228cde659` |
| `tools/check_web_ids.py` | 2977 | `45d9e41b932a` |
| `tools/gui_smoketest.py` | 3545 | `a6babe123d97` |
| `tools/package.py` | 14642 | `35a68e8fdb9f` |
| `tools/verify_package.py` | 4032 | `efebc6b1179e` |
| `tools/web_smoketest.py` | 22359 | `a041326a4557` |
| `启动计算器.cmd` | 836 | `1f04e9fcd462` |
| `启动计算器.ps1` | 1308 | `0819bbe5b9e9` |
| `命令行.cmd` | 638 | `1a2d053f4df3` |
| `命令行.ps1` | 698 | `b2d3b9feb574` |
| `桌面窗口版.cmd` | 621 | `0691aa03b608` |
| `桌面窗口版.ps1` | 589 | `5032c3acc204` |
