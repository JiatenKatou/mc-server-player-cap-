# 文件清单

- 版本：0.1.0
- 生成时间：2026-10-14 11:38:16
- 文件总数：48
- Python 代码行数合计：8653

分层：`1 配置 → 2 数据 → 3 解析 → 4 计算 → 5 呈现 → 6 界面 → 7 校准 → 8 验证`
依赖方向只能从高层指向低层；**不要出现低层反向 import 高层**。

## 1 配置层（系数）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/config.py` | 243 | ★ 木桶四个维度的全部可调系数 + CPU-Z 标定参数。改系数只改这里 |
| `mc_player_calc/cooling.py` | 207 | ★ 散热系数表（桌面散热器/笔记本模具/导热耗材）与移动端后缀规则 |
| `mc_player_calc/modpack.py` | 271 | ★ 整合包档案：一个包一套系数（校准值 / 预填值 / 兜底折算） |

## 2 数据层（CPU 库与标尺）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/cpu_data.py` | 580 | ★ CPU 型号库、CPU-Z↔指数换算、桌面/移动端识别、自定义型号存储与模糊匹配 |

## 3 解析层

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/parser.py` | 342 | 输入解析（内存/带宽/CPU/散热），把随手写的字符串变成结构化数值 |

## 4 计算层（木桶内核）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/engine.py` | 451 | ★ 木桶效应计算内核：四个维度、散热衰减、瓶颈判定、优化建议 |

## 5 呈现层（文本）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/report.py` | 82 | 纯文本报告渲染（网页明细 / CLI 输出 / GUI 明细共用） |

## 6 界面层（命令行）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/cli.py` | 632 | 命令行入口（带参数 / 交互问答 / --add-cpu / --feedback） |

## 6 界面层（桌面窗口）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/gui.py` | 962 | tkinter 桌面窗口（含 CPU 录入弹窗、反馈弹窗、测速按钮） |

## 6 界面层（网页服务）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/web.py` | 785 | ★ 本地网页服务：http.server + JSON 接口（options/calc/cooling/open-url/cpu/feedback） |

## 7 校准层（数据收集）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/feedback.py` | 933 | ★ 信息反馈收集：校验、存储、玩法系数汇总、agent 交付文件导出 |

## 7 校准层（系数反推）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/calibrate.py` | 441 | ★ 用实测数据反推 CPU 承载系数；能直接读反馈导出的 Markdown |

## 8 验证层

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `mc_player_calc/reset.py` | 437 | ★ 恢复默认：按类别清本地状态，先备份、可整组撤销 |
| `mc_player_calc/selftest.py` | 788 | 框架自检（170+ 断言） |

## 其它（文档 / 启动器 / 前端 / 测试 / 截图）

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| `.github/ISSUE_TEMPLATE/bug.yml` | 65 | — |
| `.github/ISSUE_TEMPLATE/config.yml` | 12 | — |
| `.github/ISSUE_TEMPLATE/data.yml` | 71 | — |
| `.gitignore` | 25 | — |
| `AGENTS.md` | 109 | ★ 面向 AI agent 的项目说明与硬约束 |
| `anchors.example.json` | 6 | 校准锚点格式示例（真实数据应存为 anchors.json，不入库） |
| `COPYRIGHT` | 78 | 项目声明 + GPLv3 第 7 节附加条款（估算声明/署名/修改标注） |
| `docs/screenshot.png` | 0 | 桌面窗口截图（桌面模式） |
| `docs/screenshot_mobile.png` | 0 | 桌面窗口截图（移动端 CPU + 散热联动） |
| `FILE_MANIFEST.md` | 166 | 本清单：每个文件干什么、多少行、能不能改 |
| `HANDOFF.md` | 274 | ★ 交接说明：现状、决策理由、待办、怎么验证 |
| `LICENSE` | 674 | GNU GPL v3.0 官方原文（不可修改） |
| `mc_player_calc/__init__.py` | 44 | — |
| `mc_player_calc/__main__.py` | 43 | 入口路由：无参数=网页版，--gui=桌面窗口，其它=CLI |
| `mc_player_calc/web/app.js` | 802 | 网页前端逻辑（散热联动、结果渲染、录入器、反馈表单与导出） |
| `mc_player_calc/web/index.html` | 284 | 网页前端结构（计算表单 + CPU 录入器 + 反馈收集面板） |
| `mc_player_calc/web/style.css` | 379 | 网页样式（深色主题） |
| `PUBLISH.md` | 500 | ★ 发布到 GitHub 的操作手册（仓库名/简介/Topics/Release 文案） |
| `README.en.md` | 124 | 英文快速上手（功能/安装/测试/结构，详细文档指向中文） |
| `README.md` | 734 | ★ 面向使用者的完整说明（中文主文档，先读第 1、2、7、11 节） |
| `tools/add_license_headers.py` | 103 | 给源文件加 GPL 声明头（幂等，支持预演） |
| `tools/capture_gui.py` | 143 | 开发辅助：抓窗口截图给文档用（PrintWindow） |
| `tools/check_readme_links.py` | 95 | 文档检查：README 的站内锚点与相对链接是否有效 |
| `tools/check_web_ids.py` | 87 | 前端静态检查：JS 引用的 id 是否都在 HTML 里 |
| `tools/gui_smoketest.py` | 118 | 桌面窗口联动与无裁切自测 |
| `tools/package.py` | 329 | — |
| `tools/verify_package.py` | 114 | — |
| `tools/web_smoketest.py` | 423 | 网页接口自测（真的起服务器打 HTTP，含反馈 API） |
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
| `AGENTS.md` | 6832 | `badaa8965e39` |
| `anchors.example.json` | 526 | `5d28b27a7590` |
| `COPYRIGHT` | 5279 | `8696e318b5dc` |
| `docs/screenshot.png` | 242219 | `78fb5bbea69e` |
| `docs/screenshot_mobile.png` | 256698 | `72ef713675d2` |
| `FILE_MANIFEST.md` | 8225 | `6d56d8d1b6b6` |
| `HANDOFF.md` | 16205 | `176c7def8141` |
| `LICENSE` | 35145 | `c017bccf97bb` |
| `mc_player_calc/__init__.py` | 1662 | `d00ecb0c1ee0` |
| `mc_player_calc/__main__.py` | 1558 | `a5762fb298ea` |
| `mc_player_calc/calibrate.py` | 19822 | `0a3bd69043d8` |
| `mc_player_calc/cli.py` | 29893 | `a9539a18a284` |
| `mc_player_calc/config.py` | 10426 | `0a44a98946e4` |
| `mc_player_calc/cooling.py` | 9000 | `7a79e5a1f7dc` |
| `mc_player_calc/cpu_data.py` | 24314 | `5a615477deb9` |
| `mc_player_calc/engine.py` | 20499 | `f26875f96022` |
| `mc_player_calc/feedback.py` | 44233 | `bee46f937df2` |
| `mc_player_calc/gui.py` | 48504 | `73f67212cd57` |
| `mc_player_calc/modpack.py` | 10225 | `6fa4818c7b13` |
| `mc_player_calc/parser.py` | 14373 | `131c2a68cae3` |
| `mc_player_calc/report.py` | 3538 | `c03b03756d00` |
| `mc_player_calc/reset.py` | 17987 | `99628344ac25` |
| `mc_player_calc/selftest.py` | 41564 | `16876a5fca90` |
| `mc_player_calc/web/app.js` | 30040 | `6be5e028c642` |
| `mc_player_calc/web/index.html` | 11911 | `16efda1fd760` |
| `mc_player_calc/web/style.css` | 7130 | `beaa3cbbf708` |
| `mc_player_calc/web.py` | 33900 | `e8f7ef099263` |
| `PUBLISH.md` | 19001 | `814c5ad302f2` |
| `README.en.md` | 5988 | `fcf4895442ff` |
| `README.md` | 41594 | `242f0da72b11` |
| `tools/add_license_headers.py` | 3553 | `5a57d92504e6` |
| `tools/capture_gui.py` | 5140 | `a69429b954c3` |
| `tools/check_readme_links.py` | 3897 | `a82d1f5eaeff` |
| `tools/check_web_ids.py` | 3422 | `7a3d40180976` |
| `tools/gui_smoketest.py` | 4021 | `26f3831d58d2` |
| `tools/package.py` | 15510 | `72db4bffeaa1` |
| `tools/verify_package.py` | 4504 | `74a139c9d69e` |
| `tools/web_smoketest.py` | 23140 | `0459a32498ef` |
| `启动计算器.cmd` | 836 | `1f04e9fcd462` |
| `启动计算器.ps1` | 1308 | `0819bbe5b9e9` |
| `命令行.cmd` | 638 | `1a2d053f4df3` |
| `命令行.ps1` | 698 | `b2d3b9feb574` |
| `桌面窗口版.cmd` | 621 | `0691aa03b608` |
| `桌面窗口版.ps1` | 589 | `5032c3acc204` |
