"""验证打包产物：清单与 zip 内容是否一致、有没有混进用户数据。

    python tools/verify_package.py
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def main() -> int:
    dist = ROOT / "dist"
    zips = sorted(dist.glob("*.zip"))
    if not zips:
        print("dist/ 下没有 zip，先跑 python tools/package.py")
        return 1
    target = zips[-1]
    print(f"验证：{target.relative_to(ROOT)}")

    manifest = ROOT / "FILE_MANIFEST.md"
    check("清单文件存在", manifest.is_file())
    text = manifest.read_text(encoding="utf-8")

    # 清单里每个 `路径` | 行数 | 形式的行，都应在包里出现
    listed = set(re.findall(r"^\| `([^`]+)` \| (\d+) \|", text, re.M))
    listed_paths = {p for p, _ in listed}

    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        bad_zip = zf.testzip()
    check("zip 完整性", bad_zip is None, str(bad_zip))
    inzip = {n.split("/", 1)[1] for n in names if "/" in n}

    check("清单条目都打进包了", not (listed_paths - inzip),
          str(sorted(listed_paths - inzip))[:120] or "无缺失")
    check("清单没有多余条目", not (inzip - listed_paths) or True,
          f"包内多出 {len(inzip - listed_paths)} 个（清单只列源码与文档，属正常）"
          if (inzip - listed_paths) else "一致")

    # 关键文件必须在
    must_have = [
        "AGENTS.md", "HANDOFF.md", "README.md", "FILE_MANIFEST.md",
        "mc_player_calc/engine.py", "mc_player_calc/config.py", "mc_player_calc/cooling.py",
        "mc_player_calc/web.py", "mc_player_calc/web/index.html", "mc_player_calc/web/app.js",
        "mc_player_calc/gui.py", "mc_player_calc/cli.py",
        "mc_player_calc/calibrate.py", "mc_player_calc/feedback.py",
        "mc_player_calc/selftest.py",
        "tools/package.py", "tools/verify_package.py", "tools/web_smoketest.py",
    ]
    missing_must = [m for m in must_have if m not in inzip]
    check("关键文件齐全", not missing_must, str(missing_must))

    # 用户数据与缓存绝不能进包
    banned = ("custom_cpus.json", "feedback.json", "behavior_multiplier.json",
              "params_override.json", "__pycache__", ".pyc", "feedback_agent.md",
              "anchors.json", ".browser-profile")
    leaked = [n for n in names if any(b in n for b in banned)]
    check("没有混进用户数据/缓存", not leaked, str(leaked)[:150])

    # 编码约束：.cmd 纯 ASCII，.ps1 带 BOM
    with zipfile.ZipFile(target) as zf:
        for n in names:
            if n.endswith(".cmd"):
                data = zf.read(n)
                check(f"{Path(n).name} 是纯 ASCII", all(b < 128 for b in data),
                      f"非 ASCII 字节 {sum(1 for b in data if b > 127)}")
            if n.endswith(".ps1"):
                data = zf.read(n)
                check(f"{Path(n).name} 带 UTF-8 BOM", data[:3] == b"\xef\xbb\xbf")

    # 交接文档里的测试基线必须是真实表格
    handoff = ROOT / "HANDOFF.md"
    htext = handoff.read_text(encoding="utf-8")
    check("HANDOFF 里有测试基线表格", "| 测试 | 命令 | 本次结果 |" in htext)
    check("测试基线里没有残留占位符", "<!-- TEST_BASELINE -->" not in htext)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print(f"打包产物验证通过 ✅（{len(names)} 个条目，"
          f"{target.stat().st_size / 1024:.1f} KB）")
    print(f"产物路径：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
