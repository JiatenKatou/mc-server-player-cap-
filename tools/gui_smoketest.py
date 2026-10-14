"""GUI 冒烟测试：散热控件联动 + 无裁切检查。

    python tools/gui_smoketest.py
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


import os
import sys
import tkinter as tk

# 允许直接以脚本方式运行（把仓库根目录加入模块搜索路径）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mc_player_calc.engine import CalcInput, calculate
from mc_player_calc.gui import App, _setup_style
from mc_player_calc.parser import parse_raw, RawInput

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def main() -> int:
    root = tk.Tk()
    root.geometry("1000x760")
    root.minsize(920, 660)
    _setup_style(root)
    app = App(root)
    root.update_idletasks()
    root.update()

    failures = []

    def probe(label: str) -> None:
        root.update_idletasks()
        root.update()
        raw = app._raw()
        fields, warns = parse_raw(raw)
        res = calculate(CalcInput(**fields))
        res.warnings = warns + res.warnings
        app._render(res)
        root.update_idletasks()
        root.update()
        cpu = res.factor("cpu")
        cw, ch = app.winfo_width(), app.winfo_height()
        ax, ay = app.winfo_rootx(), app.winfo_rooty()
        clipped = []
        for name, wdg in (("tree", app.tree), ("detail", app.detail), ("note", app.verdict_note)):
            rx = wdg.winfo_rootx() - ax
            ry = wdg.winfo_rooty() - ay
            if rx < 0 or ry < 0 or rx + wdg.winfo_width() > cw or ry + wdg.winfo_height() > ch:
                clipped.append(name)
        if clipped:
            failures.append(f"{label} 裁切: {clipped}")
        print(f"  [{label}] 散热 {cpu.values['散热系数']} | CPU-Z {cpu.values['CPU-Z 单核']}"
              f" | 有效单核 {cpu.values['有效单核']}"
              f" | CPU {cpu.ceiling:.1f} 人 | 整机 {res.final_players} 人"
              f" | 裁切 {clipped or '无'}")
        print(f"      提示: {app._cool_note.get().splitlines()[0]}")

    # 1) 桌面默认
    app.vars["cpu"].set("Ryzen 5 5600")
    root.update()
    probe("桌面默认")

    # 2) 桌面改成被动散热
    app.vars["radiator"].set("被动散热 / 无风扇（迷你主机、NAS）")
    probe("桌面被动散热")

    # 3) 切到移动端 CPU -> 应自动出现模具/耗材
    app.vars["cpu"].set("i7-12700H")
    root.update()
    probe("移动端默认")
    if app._chassis_box.winfo_ismapped() is False:
        failures.append("移动端未显示模具下拉")

    # 4) 手动选轻薄本
    app.vars["chassis"].set("轻薄本 / 核显本（单风扇、15~28W 限制）")
    probe("移动端轻薄本")

    # 5) 导热换液金
    app.vars["material"].set("液金导热（需专业维护）")
    probe("移动端+液金")

    # 6) 自定义系数覆盖
    app.vars["cooling_override"].set("0.7")
    probe("自定义 0.7")
    app.vars["cooling_override"].set("")

    # 7) 切回桌面 -> 应恢复散热器显示
    app.vars["cpu"].set("i5-12400")
    root.update()
    probe("切回桌面")
    if app._chassis_box.winfo_ismapped():
        failures.append("桌面端仍显示模具下拉")

    # 8) 重置
    app._on_reset()
    root.update()
    print(f"  [重置] 结论 {app.verdict.cget('text')} | 散热 {app.vars['radiator'].get() or '自动'}")

    root.destroy()
    if failures:
        print("\n失败:", failures)
        return 1
    print("\nGUI 冒烟测试全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
