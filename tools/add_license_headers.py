"""给所有 Python 源文件加上简短的 GPL 声明头（幂等）。

GPL 的 "How to Apply These Terms" 建议在每个源文件开头声明许可与免责。
本项目把**完整声明**放在 `mc_player_calc/__init__.py` 与 `COPYRIGHT`，
其余文件只用两行指向它们——既满足要求，又不会让每个文件顶部堆 15 行样板。

    python tools/add_license_headers.py            # 预演
    python tools/add_license_headers.py --write    # 实际写入
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

MARK = "SPDX-License-Identifier: GPL-3.0-only"

# 每个文件的简短头：SPDX 标识符 + 版权 + 免责指向
TEMPLATE = """# {spdx}
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。
"""

# 这些文件已经写了完整声明，跳过
SKIP = {"mc_player_calc/__init__.py"}


def targets() -> list[Path]:
    files = sorted((ROOT / "mc_player_calc").rglob("*.py"))
    files += sorted((ROOT / "tools").glob("*.py"))
    return [p for p in files
            if str(p.relative_to(ROOT)).replace("\\", "/") not in SKIP]


def insert(text: str, header: str) -> str:
    """插到 shebang / coding 声明 / 模块 docstring 之后。

    注意：`from __future__ import annotations` **必须**在 docstring 之后、
    其他语句之前，所以头部只能插在它之前，不能插到它后面。
    """
    lines = text.splitlines(keepends=True)
    idx = 0
    # 跳过 shebang 与 coding 声明
    while idx < len(lines) and (lines[idx].startswith("#!") or "coding" in lines[idx][:30]):
        idx += 1
    # 跳过模块 docstring
    if idx < len(lines) and lines[idx].lstrip().startswith(('"""', "'''")):
        quote = lines[idx].lstrip()[:3]
        if lines[idx].strip().count(quote) >= 2:
            idx += 1
        else:
            idx += 1
            while idx < len(lines) and quote not in lines[idx]:
                idx += 1
            idx += 1
    head = "".join(lines[:idx])
    rest = "".join(lines[idx:])
    if head and not head.endswith("\n"):
        head += "\n"
    return f"{head}{header}\n{rest}"


def main() -> int:
    ap = argparse.ArgumentParser(description="给源文件加 GPL 声明头")
    ap.add_argument("--write", action="store_true", help="实际写入（默认只预演）")
    args = ap.parse_args()

    changed, skipped = 0, 0
    for path in targets():
        text = path.read_text(encoding="utf-8")
        if MARK in text:
            skipped += 1
            continue
        new = insert(text, TEMPLATE.format(spdx=MARK))
        rel = path.relative_to(ROOT)
        if args.write:
            path.write_text(new, encoding="utf-8")
            print(f"  已加声明头：{rel}")
        else:
            print(f"  待加声明头：{rel}")
        changed += 1

    print(f"\n{'已修改' if args.write else '需要修改'} {changed} 个文件，"
          f"已有声明 {skipped} 个")
    if not args.write and changed:
        print("加 --write 才会真正写入")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
