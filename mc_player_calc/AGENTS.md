# AGENTS.md — 给 AI agent 的项目说明

本文件是这个仓库的**入口约束**。动手前请读完本文件，再看 `HANDOFF.md`（交接说明）。

## 这是什么

**Minecraft 服务器人数上限计算器**：输入模组数量、CPU 型号、内存、网络状况，
按**木桶效应**（四个维度取最小值）估算服务器能带多少人。

- 纯 Python 标准库实现，**零第三方依赖**
- 三种界面共用一套计算内核：本地网页版（默认）/ tkinter 桌面窗口 / 命令行
- 全部数据存本地，不上传任何东西

## 硬约束（不要违反）

1. **零依赖**：不要引入 pip 包。需要 HTTP 就用 `http.server`，需要前端就用原生 JS。
   确有必要时先问用户。
2. **单一内核**：网页、桌面窗口、命令行必须共用 `parser` / `engine` / `report`。
   任何"在某个界面里单独算一遍"的写法都是错的——`tools/web_smoketest.py` 里有断言守这条。
3. **分层依赖只能向下**：
   `1 配置(config,cooling) → 2 数据(cpu_data) → 3 解析(parser) → 4 计算(engine) → 5 呈现(report) → 6 界面(web,gui,cli) → 7 校准(calibrate,feedback)`
   不要出现低层反向 import 高层（有必要的延迟 import 请写在函数内部并加注释）。
4. **系数外置**：任何"经验值/标定值"都必须放在 `config.py` 或 `cooling.py`，
   不许写死在计算逻辑里。改系数不应该改代码。
5. **两套 CPU 标尺别混用**：界面/用户输入用 **CPU-Z 单核分**，
   `engine.py` 内部用**指数**；转换只走 `cpu_data.cpu_cpuz_to_index()` /
   `cpu_index_to_cpuz()`。
6. **用户数据不入库、不打包**：`custom_cpus.json`、`feedback.json`、
   `behavior_multiplier.json`、`modpack_profiles.json`、`params_override.json`、
   `anchors.json`、`feedback_agent.md`、`dist/` 都在 `.gitignore` 里。
7. **文件编码**：`.cmd` 启动器必须是**纯 ASCII**（cmd 会按 ANSI 解析，中文会报错）；
   `.ps1` 启动器必须是 **UTF-8 with BOM**（Windows PowerShell 5.1 的要求）；
   其余源码统一 UTF-8，中文注释不加 BOM。

## 代码地图（详见 `FILE_MANIFEST.md`）

```
mc_player_calc/
├─ config.py      ★ 木桶四维度全部可调系数 + CPU-Z 标定参数
├─ cooling.py     ★ 散热系数表（桌面散热器 / 笔记本模具 / 导热耗材）+ 移动端后缀规则
├─ cpu_data.py    ★ CPU 库 + CPU-Z↔指数换算 + 桌面/移动端识别 + 自定义型号存储
├─ parser.py      输入解析（内存 / 带宽 / CPU / 散热 / 整合包名）
├─ engine.py      ★ 木桶计算内核（四维度 + 散热衰减 + 瓶颈判定 + 优化建议）
├─ report.py      文本报告渲染
├─ web.py         ★ 本地网页服务（http.server + JSON 接口）
├─ web/           网页前端（index.html / app.js / style.css，原生 JS）
├─ gui.py         tkinter 桌面窗口
├─ cli.py         命令行
├─ calibrate.py   ★ 用实测数据反推 CPU 承载系数
├─ modpack.py     ★ 整合包档案：一个包一套系数（校准值 / 预填值 / 兜底折算）
├─ feedback.py    ★ 信息反馈收集（校验 / 存储 / 玩法汇总 / 按包汇总 / agent 交付文件）
├─ reset.py       恢复默认：按类别清本地状态，先备份、可整组撤销
└─ selftest.py    框架自检（210+ 断言）
```

## 整合包系数（很容易搞反，重点看）

`config.behavior_multiplier["整合包"]` **不是**整合包的实际系数，只是兜底基准。
真实系数走 `modpack.py`，优先级：该包校准值 → 该包预填值 → 兜底折算
（`1.6 × 玩法类型 × 进度阶段`）。

**语义：系数是「每模组的负载倍数」，越大 = 越吃资源 = 承载越低。**
所以"作者优化差的包"最终会拿到一个**更大**的系数。写测试和断言时别搞反。

按包校准与按 CPU 校准有个关键差异：CPU 校准时若瓶颈是模组天花板要**跳过**
（避免两个杠杆互相污染）；但按包校准时**模组天花板正是要量的东西**——
所以 `feedback.summarize_packs()` 里只有内存/网络瓶颈会被跳过。

包名是**自由文本**，任何界面都不要做成"只能选预设"的下拉框；
匹配用 `modpack.normalize_pack()`（只比字母数字与中文，先精确再双向包含）。

常用命令：

```bash
python -m mc_player_calc.selftest        # 内核自检（210+ 断言）
python tools/web_smoketest.py            # 网页接口自测（真起服务打 HTTP）
python tools/gui_smoketest.py            # 桌面窗口自测
python tools/check_web_ids.py            # 前端静态检查（JS 引用的 id 是否都在 HTML 里）
python tools/check_readme_links.py       # 文档检查（锚点与相对链接是否有效）
python tools/package.py                  # 生成清单 + 打包（顺带跑测试）
python -m mc_player_calc                 # 启动本地网页版
```

## 改代码前请确认

- 你改的是**系数**还是**逻辑**？只改系数的话，动 `config.py` / `cooling.py`，别碰 `engine.py`。
- 你改的逻辑会影响**四个维度中的哪一个**？瓶颈判定是取最小值，影响面可能超出预期。
- 加新维度时：在 `engine.py` 写一个 `_xxx_factor()`，加进 `calculate()` 的 `factors` 列表即可，
  瓶颈判定、报告、三种界面会自动涵盖（不需要改界面代码）。

## 提交前必做

1. **五套检查全绿**：内核自检 / 网页接口自测 / 桌面窗口自测 / 前端静态 id 检查 / 文档链接检查。
2. 改了前端就再跑一次 `tools/check_web_ids.py`（JS 里 `$('id')` 都要在 HTML 里存在）。
3. 改了默认系数，同步更新 `README.md` 第 2 节的"来源与可信度"表格。
4. 改了本地状态文件（新增/改名），必须同步更新 `reset.py` 的 `ITEMS` 与 `.gitignore`，
   否则"恢复默认"会漏掉它——`selftest.test_reset` 会兜住这类遗漏。
5. 重新 `python tools/package.py`。

## 需要拿主意时

`HANDOFF.md` 第 7 节写了用户的偏好。总的原则：**先修用户点名的问题**，
顺手发现的真 bug 一起修但要说明；**不确定就直说、直接问**，不要猜着改系数。
