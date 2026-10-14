"""静态检查网页前端：JS 里引用的每个 id 都必须在 HTML 里存在。

纯前端没有浏览器自动化测试，所以用这个守住"改了 HTML 忘了改 JS"这类低级错误。

    python tools/check_web_ids.py
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

JS = ROOT / "mc_player_calc" / "web" / "app.js"
HTML = ROOT / "mc_player_calc" / "web" / "index.html"
CSS = ROOT / "mc_player_calc" / "web" / "style.css"

FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def main() -> int:
    js = JS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    ids_html = set(re.findall(r'id="([^"]+)"', html))
    # $('xxx') 形式
    ids_js = set(re.findall(r"\$\('([^']+)'\)", js))
    # STATE_LABEL 之类的对象字面量不算 id，这里只关心 $()

    print(f"HTML id {len(ids_html)} 个，JS 引用 {len(ids_js)} 个")
    missing = sorted(ids_js - ids_html)
    check("JS 引用的 id 都在 HTML 里", not missing, str(missing))
    unused = sorted(ids_html - ids_js)
    check("HTML 里没有完全没人用的 id（提示用，不算错）", True,
          f"未被 $() 引用：{len(unused)} 个 {unused[:6]}")

    # 关键交互区块必须在
    for must in ("feedback-panel", "state-card", "st-reset-user", "st-reset-all", "st-preview",
                 "st-backups", "state-list", "st-report",
                 "modpack", "pack_hints", "pack-note", "fb-optimization"):
        check(f"存在 #{must}", must in ids_html)

    # CSS 里出现的 class 是否在 HTML/JS 里用到（只检查新增的状态标签）
    for cls in ("state-tag", "state-gone", "danger"):
        check(f"CSS 定义了 .{cls}", f".{cls}" in css)
        check(f".{cls} 在 HTML/JS 里被用到", cls in html or cls in js)

    # 危险按钮必须有确认（防止误点丢数据）
    check("清除用户数据有二次确认", "window.confirm" in js and "doReset('user')" in js)
    check("恢复默认前会提示备份可撤销", "可整组撤销" in html or "可以整组撤销" in html)

    # JS 里不能残留未定义的助手（之前踩过 api()/escapeHtml() 不存在的坑）
    for helper in ("postJson", "stateText", "renderState", "loadState", "doReset", "undoReset"):
        check(f"定义了 {helper}()", f"function {helper}(" in js or f"async function {helper}(" in js)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print("网页前端静态检查通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
