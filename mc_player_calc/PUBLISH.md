# 发布到 GitHub 的完整操作手册

面向**第一次开源**的人写的，每一步都能照做。本机当前状态：**没装 git、没装 gh CLI**，
所以第 1 步是装工具。

---

## 0. 先想清楚三件事（花 10 分钟，省后面一堆麻烦）

### 0.1 仓库叫什么

**建议：`mc-server-player-cap`**

理由：短、好念、全小写加连字符（GitHub 惯例）、搜得到。
"player-cap" 是英文里"人数上限"的常用说法（cap = 上限）。

候选与取舍：

| 候选 | 评价 |
| --- | --- |
| `mc-server-player-cap` | ✅ 推荐。短、语义准、好搜 |
| `mc-player-calculator` | 也行，但"calculator"太泛，搜索结果里容易被淹没 |
| `minecraft-server-capacity` | 更正式，但长且偏学术 |
| `mc-bucket-capacity` | "木桶效应"是卖点，但没接触过的人看不出这是什么 |
| 中文名（如 `mc人数上限计算器`） | ❌ 不建议。URL 会变成百分号编码，很难分享 |

### 0.2 一句话简介（GitHub 仓库的 Description）

限制 **350 字符**，但列表页只显示前 ~120 字符，**所以重点必须放最前面**。

**推荐：英文优先**

```
Estimate how many players your Minecraft server can handle — mods, CPU, RAM, network, bottlenecked by the weakest link. Pure stdlib Python, zero dependencies, all data stays local.
```

**备选：中文优先**（主要面向中文服主社群时）

```
输入模组数量、CPU、内存、网络，用木桶效应估算你的 Minecraft 服务器能带多少人。零依赖、数据全在本地。English quick-start included.
```

**为什么推荐英文优先**：

1. GitHub 的搜索、Topics 页面、Trending 都是英文内容生态，英文简介更容易被分到
   `minecraft-server`、`self-hosted` 这类 topic 的推荐流里
2. 中文在列表页因字体宽度被截断得更早，前 120 字符能装的信息更少
3. 国内服主大多看得懂 "Minecraft server / CPU / RAM" 这几个词，不构成门槛

**项目里已做好的双语安排**：

| 文件 | 内容 |
| --- | --- |
| `README.md` | 完整中文文档（主文档），顶部有 `中文 \| [English](README.en.md)` 切换 |
| `README.en.md` | 英文快速上手：功能、四维度表、安装、测试命令、仓库结构，并指向中文详细文档 |

**两个不推荐的做法**：

- ❌ **把中英文塞进同一个 README**（前半中文后半英文）。文件会很长，
  两种语言的读者都要滚动半天才能找到自己的部分。
- ❌ **维护两份完整翻译**。详细文档（系数来源、校准流程）改动频繁，
  两份完整翻译必然有一份过期，**过期文档比没有文档更误导人**。
  英文版只做"快速上手 + 指向中文详细文档"，才是可持续的。

### 0.3 用什么许可

**已配好 MIT**（`LICENSE` 已就位）。**建议就用它，不要改。**

| 你的考虑 | MIT 的表现 |
| --- | --- |
| 服主拿去用 | ✅ 无附加条件，最容易传播 |
| 别人 fork 改进 | ✅ 允许，而且改进**有可能回流给你** |
| 你不想担法律责任 | ✅ 自带免责条款，你还额外写了"估算值不是实测保证" |
| 商业使用 | ✅ 允许。但你不打算卖，这条对你零成本 |

**顺手说清楚一个常见误区**——按错误的期待选许可是最亏的：

- 开源许可是**授权**（我允许你做什么），**不是约束**（你必须为我做什么）
- **没有任何主流开源许可能强制别人"回传数据"**
- 想强制衍生作品开源 → 用 GPL 系，但这样有些公司就不敢用了
- 想强制回传数据 → **做不到**。加了这种条款就不再是标准开源项目，很多人会直接避开
- 你真正在乎的"别人拿了数据不回报"，**许可解决不了，只能靠社群习惯**——
  在 README 里写一句"如果这些校准数据帮到了你，欢迎回传一份你自己的实测"就够了

**什么情况才该换**：

| 情况 | 该用什么 |
| --- | --- |
| 就是现在这样，让人随便用 | **MIT**（保持不动） |
| 担心别人拿去做商业闭源产品 | Apache-2.0（多专利授权）或 MPL-2.0（文件级 copyleft） |
| 希望所有衍生作品都必须开源 | GPL-3.0 |
| 以后想卖商业授权 | AGPL-3.0 或双许可（需另备商业许可文本） |

对一个"靠收数据才能变准"的工具来说，**上面那些更严的许可都会降低服主愿意试用的概率**，
而你现在最需要的恰恰是有人愿意试、愿意回传数据。**所以 MIT 是最优解。**

> ⚠ 一个实务提醒：**换许可不等于能收回已发布的版本**。MIT 是不可撤销的——
> 一旦按 MIT 发布，任何人都可以永久按 MIT 使用**那个版本**。
> 所以这个决定必须在第一次发布前做对。

---

## 1. 安装工具

### 1.1 装 Git for Windows

打开 PowerShell，执行：

```powershell
winget install --id Git.Git -e --source winget
```

装完**关掉当前 PowerShell 再重新打开**（PATH 才会生效），然后验证：

```powershell
git --version
```

> 如果 `winget` 也没有，去 https://git-scm.com/download/win 下载安装包，
> 一路默认下一步即可。安装时**不要**改默认编辑器为 Vim（新手容易卡住），
> 建议选 Notepad 或 VS Code。

### 1.2 装 GitHub CLI（可选，但强烈建议）

它能让你不用打开浏览器就能建仓库、改仓库信息：

```powershell
winget install --id GitHub.cli -e --source winget
```

重新打开 PowerShell 后登录：

```powershell
gh auth login
```

选择顺序：`GitHub.com` → `HTTPS` → `Login with a web browser`，
然后照提示复制那个一次性码、在浏览器里粘贴授权。

### 1.3 配置 Git 身份（**必做，否则提交记录是错的**）

```powershell
git config --global user.name "你的名字或昵称"
git config --global user.email "你的邮箱"
```

> ⚠ 这里的邮箱会**公开出现在每一次提交记录里**。如果不想暴露常用邮箱，
> 在 GitHub 的 Settings → Emails 里打开 "Keep my email addresses private"，
> 它会给你一个 `xxxxx@users.noreply.github.com` 形式的地址，用那个。

再设两个让中文不出乱码的选项：

```powershell
git config --global core.quotepath false
git config --global i18n.commitEncoding utf-8
```

---

## 2. 提交代码到本地仓库

在项目目录里执行（PowerShell 逐行跑）：

```powershell
cd "C:\Users\田所浩二\Documents\deepseek-harness\default-workspace"

git init
git add .
git status
```

**关键：`git status` 一定要看一眼**，确认这几件事：

- ✅ 有 `README.md`、`LICENSE`、`mc_player_calc/`、`tools/`、`.github/`
- ❌ **没有** `dist/`、`__pycache__/`、`*.bak`
- ❌ **没有** `feedback.json`、`custom_cpus.json`、`behavior_multiplier.json`、
  `modpack_profiles.json`（这些是你的个人数据，`.gitignore` 已经挡住了）
- ❌ **没有** `_selftest_*`、`_smoketest_tmp`（测试临时目录）

确认干净后提交：

```powershell
git commit -m "feat: Minecraft 服务器人数上限计算器 v0.1.0

按木桶效应（CPU / 内存 / 网络 / 模组负载取最小值）估算服务器承载人数。

- 三种界面共用一套内核：本地网页版 / tkinter 桌面窗口 / 命令行
- 纯 Python 标准库实现，零第三方依赖
- 散热系数：桌面散热器；移动端按模具 x 导热耗材
- CPU-Z 单核跑分标尺 + 自定义 CPU 型号录入器
- 整合包「一个包一套系数」，按包名校准
- 服主反馈收集 -> 汇总 -> 反哺系数，支持导出给 agent 的数据文件
- 恢复默认：先备份可整组撤销
"
```

把默认分支改成 `main`（GitHub 现在的惯例）：

```powershell
git branch -M main
```

---

## 3. 在 GitHub 上建仓库

### 方式 A：用 gh CLI（一条命令）

```powershell
gh repo create mc-server-player-cap --public --source=. --remote=origin --push `
  --description "输入模组数量、CPU、内存、网络，用木桶效应估算你的 Minecraft 服务器能带多少人。纯 Python 标准库、零依赖、数据全在本地。"
```

这条命令会**建仓库 + 加 remote + 推送**一次完成。然后跳到第 4 步。

### 方式 B：网页建（更直观，推荐第一次用）

1. 打开 https://github.com/new
2. **Repository name** 填 `mc-server-player-cap`
3. **Description** 粘贴第 0.2 节那句
4. 选 **Public**
5. **⚠ 不要勾** "Add a README file" / "Add .gitignore" / "Choose a license"
   —— 你本地都有了，勾了会产生冲突
6. 点 **Create repository**
7. 页面会显示推送命令，照着跑：

```powershell
git remote add origin https://github.com/你的用户名/mc-server-player-cap.git
git push -u origin main
```

**第一次推送会弹窗要你登录 GitHub**，选 "Sign in with your browser" 最省事。
（如果反复要密码，说明需要用 Personal Access Token 而不是账号密码——
用 `gh auth login` 过的会省掉这步。）

---

## 4. 填仓库的"门面"信息

建完仓库后，点仓库名旁边的 **⚙️ About**（右上角齿轮），填这几项：

### 4.1 Description

见第 0.2 节（网页建仓库时填过就不用重复）。

### 4.2 Website

有的话填（比如你以后做了网页版 demo）；没有就留空。

### 4.3 Topics（**很重要，决定别人能不能搜到你**）

在 About 面板的 Topics 里逐个添加：

```
minecraft
minecraft-server
server-capacity
performance
benchmark
python
tkinter
zero-dependency
capacity-planning
modded-minecraft
paper-mc
forgemc
self-hosted
chinese
```

> Topics 要小写、用连字符。加满 10-15 个不丢人，Facebook/Google 都在用。
> 这几个是最能带来自然流量的：`minecraft-server`、`server-capacity`、`self-hosted`。

### 4.4 勾上 "Releases" 之外的都不要动

- ✅ Releases（你要发版本）
- ❌ Packages、Environments 用不到

---

## 5. 发第一个 Release

Release 是别人"下载来用"的入口，比让他们点 "Code → Download ZIP" 友好得多。

```powershell
git tag -a v0.1.0 -m "首个版本：木桶效应人数估算 + 散热 + 整合包档案 + 反馈收集"
git push origin v0.1.0
```

然后网页上：仓库 → 右侧 **Releases** → **Draft a new release** →
选 `v0.1.0` 标签 → 标题填 `v0.1.0 — 首个可用版本` → 描述直接粘贴下面这段：

```markdown
## 这是什么

输入**模组数量 → CPU 型号 → 内存 → 网络状况**，按**木桶效应**（四个维度取最小值）
估算你的 Minecraft 服务器大概能带多少人。

## 亮点

- **零依赖**：纯 Python 标准库，不用装任何包，双击启动器就能用
- **三种界面，同一套内核**：本地网页版（推荐）/ 桌面窗口 / 命令行，结论必然一致
- **数据全在本地**：不联网、不上传、没有账号
- **散热系数**：桌面按散热器；移动端按"模具 × 导热耗材"
- **CPU-Z 标尺**：界面用你熟悉的 CPU-Z 单核分，也能自己录入型号
- **整合包一个包一套系数**：作者优化差别很大，所以按包名分别校准
- **反馈能反哺**：服主填的实测数据会用来校准系数，可导出成给 AI 读的文件

## 安装

需要 Python 3.10+（3.12 更好）。**不需要 pip install 任何东西。**

- 下载源码 → 双击 `启动计算器.cmd`（网页版）
- 或双击 `桌面窗口版.cmd`（桌面窗口）
- 或命令行：`python -m mc_player_calc --help`

## ⚠ 重要：这是估算工具

CPU 维度的核心系数（基准承载人数、多核收益、容量幂）目前是**估算值**，
没有充分实测支撑。**请勿当作服务器采购或容量承诺的依据。**

内存与网络维度有公开实测口径可核对；散热系数是相对基准。
详细来源与可信度见 README 第 2 节。

**如果你有实测数据，欢迎开 issue 提交**——工具里能一键导出给你我双方都能读的数据文件，
这正是把估算系数换成真实值的途径。
```

把 zip 拖进 release 的附件区（用 `dist/` 里那个，或让 README 引导他们下源码）。

---

## 6. 发布后立刻做的几件事

### 6.1 自己先点一遍 README 里的链接

GitHub 上 README 渲染和本地看不一样，重点检查：

- `docs/screenshot*.png` 能不能显示（图挂了最影响第一印象）
- 代码块有没有被错误解析
- 相对链接（如 `docs/screenshot.png`）对不对

### 6.2 把 `config.yml` 里的占位链接换成真实地址

`.github/ISSUE_TEMPLATE/config.yml` 里现在是 `https://github.com`（占位），
换成你的仓库地址，否则那三个"联系我们"链接会跳到 GitHub 首页。

### 6.3 加一个仓库 Social Preview 图（可选但很值）

仓库 → Settings → 拉到最下 **Social preview** → 上传 `docs/screenshot.png`。
这样别人在社交媒体/群里分享链接时会有预览图，点击率差很多。

### 6.4 想清楚要不要中文优先

现在 README 是纯中文。这没错——你的目标用户是中文 MC 服主社群。
但如果想同时吸引国外用户，可以：

- 保留 `README.md` 为中文
- 加一个 `README.en.md`（英文版），在中文 README 顶部加一行
  `English | [中文](README.md)`

**别一上来就做双语**，先把中文版发出去收反馈。

---

## 7. 第一次开源会遇到的几个问题（提前打预防针）

### 7.1 一定会有人问"你这数字准吗"

**这是最容易被质疑的点，也是我建议你主动先说的点。**

README 里已经写了"CPU 系数是估算值"，这是对的，别改。有人质疑时，
标准回答就一句：**"对，CPU 锚点是估的，所以我在收实测数据来校准，欢迎你提交一份。"**
这个态度比辩护"我的模型很科学"有用得多。

### 7.2 会有人提"为什么不用 XX 框架/库"

比如"为什么不用 Flask""为什么不用 React"。README 里已经写了理由
（服主要装依赖太麻烦），直接引用即可。这是**设计选择**，不是疏漏。

### 7.3 会有人想加功能

用 Issue 管理，别在聊天里答应。看到好建议就开个 issue 打 `enhancement` 标签，
这样别人也能看到进度，你也不会忘。

### 7.4 关于"数据回传"

你收数据靠 Issue，所以要**主动降低门槛**：
- README 第 14 节已经引导了流程
- Issue 模板已经做了引导和口径确认
- 如果有人懒得填表，**让他直接把 spark 报告截图发来也行**——数据不完整比没有好

---

## 8. 完整命令速查（装好 git 之后照抄）

```powershell
# 1. 进目录
cd "C:\Users\田所浩二\Documents\deepseek-harness\default-workspace"

# 2. 初始化并检查
git init
git add .
git status                        # ★ 仔细看，确认没有个人数据和 dist/

# 3. 提交
git commit -m "feat: Minecraft 服务器人数上限计算器 v0.1.0"
git branch -M main

# 4. 建仓库并推送（二选一）
#   A. gh CLI：
gh repo create mc-server-player-cap --public --source=. --remote=origin --push `
  --description "输入模组数量、CPU、内存、网络，用木桶效应估算你的 Minecraft 服务器能带多少人。纯 Python 标准库、零依赖、数据全在本地。"
#   B. 网页建好仓库后：
git remote add origin https://github.com/你的用户名/mc-server-player-cap.git
git push -u origin main

# 5. 打标签发版本
git tag -a v0.1.0 -m "首个版本"
git push origin v0.1.0

# 6. 以后每次改完代码
git add .
git commit -m "fix: 修正 XXX"
git push
```

---

## 9. 关于"以后怎么写提交信息"

不用很严格，但建议用这个简单约定（Conventional Commits 的中文简化版）：

| 前缀 | 用途 | 例子 |
| --- | --- | --- |
| `feat:` | 新功能 | `feat: 支持按整合包名校准系数` |
| `fix:` | 修 bug | `fix: 包名未归一化导致样本被拆散` |
| `docs:` | 只改文档 | `docs: 补充散热系数的来源说明` |
| `refactor:` | 重构不改行为 | `refactor: 抽出 reset 模块` |
| `test:` | 只改测试 | `test: 补恢复默认的撤销用例` |

好处是以后 issue 里讨论、或者别人看历史时，一眼就知道每次改了什么。

---

## 10. 最后一件事：发布前跑一遍检查

```powershell
python -m mc_player_calc.selftest        # 内核自检
python tools/web_smoketest.py            # 网页接口
python tools/gui_smoketest.py            # 桌面窗口
python tools/check_web_ids.py            # 前端静态检查
```

**四套全绿再发**。仓库里已经写了"提交前必做"这一节（`AGENTS.md`），
以后你自己或别人来改也会照着做。
