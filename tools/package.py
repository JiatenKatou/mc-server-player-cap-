"""打包：生成交接文档与一个干净的 zip（排除用户数据与缓存）。

    python tools/package.py                 # 生成清单 + 打包
    python tools/package.py --no-zip        # 只生成文档

产物：
    HANDOFF.md          交接说明（给下一个 agent）
    FILE_MANIFEST.md    文件清单（用途、行数、改动建议）
    dist/mc_player_calc-<版本>-<日期>.zip
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# 打进包里的内容（源码 + 文档 + 工具 + 示例）
INCLUDE_DIRS = ["mc_player_calc", "tools", "docs", ".github"]
INCLUDE_FILES = [
    "README.md", "README.en.md", "AGENTS.md", "HANDOFF.md", "FILE_MANIFEST.md",
    "PUBLISH.md", "LICENSE", "COPYRIGHT",
    "anchors.example.json", ".gitignore",
    "启动计算器.ps1", "启动计算器.cmd",
    "桌面窗口版.ps1", "桌面窗口版.cmd",
    "命令行.ps1", "命令行.cmd",
]
# 明确排除：用户数据、缓存、产物、测试临时目录
EXCLUDE_NAMES = {
    "__pycache__", ".browser-profile", "dist",
    "custom_cpus.json", "feedback.json", "behavior_multiplier.json",
    "modpack_profiles.json",
    "params_override.json", "anchors.json", "feedback_agent.md",
    "feedback.csv", "feedback_export.json",
    "_smoketest_tmp", "_selftest_feedback", "_selftest_modpack", "_selftest_reset",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip", ".bak"}

# 文件用途说明（给接手的人看）
PURPOSES = {
    "mc_player_calc/config.py": "★ 木桶四个维度的全部可调系数 + CPU-Z 标定参数。改系数只改这里",
    "mc_player_calc/cooling.py": "★ 散热系数表（桌面散热器/笔记本模具/导热耗材）与移动端后缀规则",
    "mc_player_calc/cpu_data.py": "★ CPU 型号库、CPU-Z↔指数换算、桌面/移动端识别、自定义型号存储与模糊匹配",
    "mc_player_calc/parser.py": "输入解析（内存/带宽/CPU/散热），把随手写的字符串变成结构化数值",
    "mc_player_calc/engine.py": "★ 木桶效应计算内核：四个维度、散热衰减、瓶颈判定、优化建议",
    "mc_player_calc/report.py": "纯文本报告渲染（网页明细 / CLI 输出 / GUI 明细共用）",
    "mc_player_calc/web.py": "★ 本地网页服务：http.server + JSON 接口（options/calc/cooling/open-url/cpu/feedback）",
    "mc_player_calc/web/index.html": "网页前端结构（计算表单 + CPU 录入器 + 反馈收集面板）",
    "mc_player_calc/web/app.js": "网页前端逻辑（散热联动、结果渲染、录入器、反馈表单与导出）",
    "mc_player_calc/web/style.css": "网页样式（深色主题）",
    "mc_player_calc/gui.py": "tkinter 桌面窗口（含 CPU 录入弹窗、反馈弹窗、测速按钮）",
    "mc_player_calc/cli.py": "命令行入口（带参数 / 交互问答 / --add-cpu / --feedback）",
    "mc_player_calc/calibrate.py": "★ 用实测数据反推 CPU 承载系数；能直接读反馈导出的 Markdown",
    "mc_player_calc/modpack.py": "★ 整合包档案：一个包一套系数（校准值 / 预填值 / 兜底折算）",
    "mc_player_calc/reset.py": "★ 恢复默认：按类别清本地状态，先备份、可整组撤销",
    "tools/check_web_ids.py": "前端静态检查：JS 引用的 id 是否都在 HTML 里",
    "tools/check_readme_links.py": "文档检查：README 的站内锚点与相对链接是否有效",
    "LICENSE": "GNU GPL v3.0 官方原文（不可修改）",
    "COPYRIGHT": "项目声明 + GPLv3 第 7 节附加条款（估算声明/署名/修改标注）",
    "tools/add_license_headers.py": "给源文件加 GPL 声明头（幂等，支持预演）",
    "mc_player_calc/feedback.py": "★ 信息反馈收集：校验、存储、玩法系数汇总、agent 交付文件导出",
    "mc_player_calc/selftest.py": "框架自检（170+ 断言）",
    "mc_player_calc/__main__.py": "入口路由：无参数=网页版，--gui=桌面窗口，其它=CLI",
    "README.md": "★ 面向使用者的完整说明（中文主文档，先读第 1、2、7、11 节）",
    "README.en.md": "英文快速上手（功能/安装/测试/结构，详细文档指向中文）",
    "AGENTS.md": "★ 面向 AI agent 的项目说明与硬约束",
    "HANDOFF.md": "★ 交接说明：现状、决策理由、待办、怎么验证",
    "PUBLISH.md": "★ 发布到 GitHub 的操作手册（仓库名/简介/Topics/Release 文案）",
    "FILE_MANIFEST.md": "本清单：每个文件干什么、多少行、能不能改",
    "anchors.example.json": "校准锚点格式示例（真实数据应存为 anchors.json，不入库）",
    "tools/web_smoketest.py": "网页接口自测（真的起服务器打 HTTP，含反馈 API）",
    "tools/gui_smoketest.py": "桌面窗口联动与无裁切自测",
    "tools/capture_gui.py": "开发辅助：抓窗口截图给文档用（PrintWindow）",
    "docs/screenshot.png": "桌面窗口截图（桌面模式）",
    "docs/screenshot_mobile.png": "桌面窗口截图（移动端 CPU + 散热联动）",
    "启动计算器.ps1": "本地网页版启动器（推荐入口，UTF-8 BOM）",
    "启动计算器.cmd": "本地网页版启动器（ASCII 兜底，双击可用）",
    "桌面窗口版.ps1": "桌面窗口启动器",
    "桌面窗口版.cmd": "桌面窗口启动器（ASCII 兜底）",
    "命令行.ps1": "命令行启动器",
    "命令行.cmd": "命令行启动器（ASCII 兜底）",
}

LAYERS = {
    "mc_player_calc/config.py": "1 配置层（系数）",
    "mc_player_calc/cooling.py": "1 配置层（系数）",
    "mc_player_calc/cpu_data.py": "2 数据层（CPU 库与标尺）",
    "mc_player_calc/parser.py": "3 解析层",
    "mc_player_calc/engine.py": "4 计算层（木桶内核）",
    "mc_player_calc/report.py": "5 呈现层（文本）",
    "mc_player_calc/web.py": "6 界面层（网页服务）",
    "mc_player_calc/gui.py": "6 界面层（桌面窗口）",
    "mc_player_calc/cli.py": "6 界面层（命令行）",
    "mc_player_calc/calibrate.py": "7 校准层（系数反推）",
    "mc_player_calc/modpack.py": "1 配置层（系数）",
    "mc_player_calc/reset.py": "8 验证层",
    "mc_player_calc/feedback.py": "7 校准层（数据收集）",
    "mc_player_calc/selftest.py": "8 验证层",
}


def iter_files():
    """按打包规则遍历要纳入的文件。"""
    seen = set()
    for name in INCLUDE_FILES:
        p = ROOT / name
        if p.is_file():
            seen.add(p)
            yield p
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel_parts = set(p.relative_to(ROOT).parts)
            if rel_parts & EXCLUDE_NAMES:
                continue
            if p.suffix in EXCLUDE_SUFFIXES or p.name in EXCLUDE_NAMES:
                continue
            if p in seen:
                continue
            seen.add(p)
            yield p


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except (UnicodeDecodeError, OSError):
        return 0


def write_manifest(files, version: str) -> Path:
    lines = ["# 文件清单", ""]
    lines.append(f"- 版本：{version}")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 文件总数：{len(files)}")
    total_lines = sum(count_lines(p) for p in files if p.suffix == ".py")
    lines.append(f"- Python 代码行数合计：{total_lines}")
    lines.append("")
    lines.append("分层：`1 配置 → 2 数据 → 3 解析 → 4 计算 → 5 呈现 → 6 界面 → 7 校准 → 8 验证`")
    lines.append("依赖方向只能从高层指向低层；**不要出现低层反向 import 高层**。")
    lines.append("")

    by_layer: dict[str, list[Path]] = {}
    others: list[Path] = []
    for p in files:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        layer = LAYERS.get(rel)
        (by_layer.setdefault(layer, []).append(p) if layer else others.append(p))

    for layer in sorted(k for k in by_layer if k):
        lines.append(f"## {layer}")
        lines.append("")
        lines.append("| 文件 | 行数 | 用途 |")
        lines.append("| --- | --- | --- |")
        for p in sorted(by_layer[layer]):
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            lines.append(f"| `{rel}` | {count_lines(p)} | {PURPOSES.get(rel, '—')} |")
        lines.append("")

    lines.append("## 其它（文档 / 启动器 / 前端 / 测试 / 截图）")
    lines.append("")
    lines.append("| 文件 | 行数 | 用途 |")
    lines.append("| --- | --- | --- |")
    for p in sorted(others):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        lines.append(f"| `{rel}` | {count_lines(p)} | {PURPOSES.get(rel, '—')} |")
    lines.append("")
    lines.append("## 校验值（前 12 位 SHA-256）")
    lines.append("")
    lines.append("| 文件 | 字节 | SHA-256 |")
    lines.append("| --- | --- | --- |")
    for p in sorted(files):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        lines.append(f"| `{rel}` | {p.stat().st_size} | `{sha256(p)}` |")
    lines.append("")
    path = ROOT / "FILE_MANIFEST.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_suite(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{exc}"
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-2:])
    return proc.returncode == 0, tail


def collect_test_baseline() -> str:
    """跑一遍测试，把结果写进交接文档（下一个 agent 可对照）。"""
    py = sys.executable
    suites = [
        ("内核自检", [py, "-m", "mc_player_calc.selftest"]),
        ("网页接口自测", [py, "tools/web_smoketest.py"]),
        ("桌面窗口自测", [py, "tools/gui_smoketest.py"]),
        ("前端静态检查", [py, "tools/check_web_ids.py"]),
        ("文档链接检查", [py, "tools/check_readme_links.py"]),
    ]
    lines = ["| 测试 | 命令 | 本次结果 | 输出末尾 |", "| --- | --- | --- | --- |"]
    for name, cmd in suites:
        ok, tail = run_suite(cmd)
        shown = " ".join(cmd[1:]) if cmd[0] == py else " ".join(cmd)
        tail = tail.replace("|", "\\|").replace("\n", " / ")
        lines.append(f"| {name} | `python {shown}` | {'通过' if ok else '**失败**'} | {tail} |")
    return "\n".join(lines)


def inject_baseline(text: str, baseline: str) -> tuple:
    """把测试基线写进 HANDOFF.md。

    注意：第一次是替换 `<!-- TEST_BASELINE -->` 占位符，之后就**没有占位符了**。
    早期版本只处理占位符，导致"第一次之后基线再也不更新"——
    而这份基线存在的意义正是"每次打包都反映当前测试状态"。
    所以现在认三种锚点：占位符 / 已有的基线表格块 / 小节标题。
    返回 (新文本, 是否改动了)。
    """
    marker = "<!-- TEST_BASELINE -->"
    if marker in text:
        return text.replace(marker, baseline), True

    # 已有基线表格：整块替换（表头 + 分隔 + 若干数据行）
    pattern = re.compile(
        r"\| 测试 \| 命令 \| 本次结果 \| 输出末尾 \|\n"
        r"\| --- \| --- \| --- \| --- \|\n"
        r"(?:\|[^\n]*\|\n?)*")
    new, n = pattern.subn(lambda _m: baseline + "\n", text, count=1)
    if n:
        return new, True

    anchor = "### 本次交付时的测试基线"
    if anchor in text:
        return text.replace(anchor, f"{anchor}\n\n{baseline}"), True
    return text, False


def main() -> int:
    ap = argparse.ArgumentParser(description="打包项目并生成交接文档")
    ap.add_argument("--no-zip", action="store_true", help="只生成文档，不压缩")
    args = ap.parse_args()

    from mc_player_calc import __version__

    files = sorted(iter_files())
    manifest = write_manifest(files, __version__)
    print(f"文件清单已生成：{manifest.name}（{len(files)} 个文件）")

    baseline = collect_test_baseline()
    print("测试基线已采集")

    # 把测试基线写入 HANDOFF.md（每次打包都刷新，不是只写第一次）
    handoff = ROOT / "HANDOFF.md"
    if handoff.is_file():
        text = handoff.read_text(encoding="utf-8")
        updated, changed = inject_baseline(text, baseline)
        if changed:
            handoff.write_text(updated, encoding="utf-8")
            print("已刷新 HANDOFF.md 里的测试基线")
        else:
            print("⚠ 没找到测试基线的位置，HANDOFF.md 未更新（请检查该小节标题）")

    if args.no_zip:
        return 0

    # 打包：重新收集一次文件（此时 MANIFEST 已是最新），并去重
    files = sorted(iter_files())
    included = {str(p.relative_to(ROOT)) for p in files}
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    zip_path = dist / f"mc_player_calc-{__version__}-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=str(Path("mc_player_calc") / p.relative_to(ROOT)))
        extra = [("FILE_MANIFEST.md", manifest)]
        if handoff.is_file():
            extra.append(("HANDOFF.md", handoff))
        agents = ROOT / "AGENTS.md"
        if agents.is_file():
            extra.append(("AGENTS.md", agents))
        for rel, path in extra:
            if rel in included:          # 已经在 INCLUDE_FILES 里，别写两次
                continue
            zf.write(path, arcname=str(Path("mc_player_calc") / rel))
    size_kb = zip_path.stat().st_size / 1024
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    print(f"打包完成：{zip_path}")
    print(f"  {size_kb:.1f} KB，{len(names)} 个条目")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
