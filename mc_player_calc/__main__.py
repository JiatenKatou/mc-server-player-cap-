"""python -m mc_player_calc 入口。

默认行为：启动**本地网页版**并在浏览器中打开（最省事、跨平台）。
也可显式选择其它界面：
    python -m mc_player_calc                 # 本地网页（默认）
    python -m mc_player_calc --web --port 9000
    python -m mc_player_calc --gui           # tkinter 桌面窗口
    python -m mc_player_calc --mods 30 ...   # 命令行一步到位（带参数即走 CLI）
"""
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 <请填写你的名字或昵称>
#
# 本文件是「Minecraft 服务器人数上限计算器」的一部分，按 GPL-3.0 授权。
# 完整声明见 mc_player_calc/__init__.py 与项目根目录的 COPYRIGHT。
# 本程序不提供任何担保；输出为模型估算值，不是实测保证。


from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        from .web import main as web_main
        return web_main([])

    # 只要不是明确要求其它界面，就把参数交给网页版（含 --port / --host / --no-browser）
    if argv[0] in ("--gui", "-g"):
        from .gui import main as gui_main
        return gui_main()

    if argv[0] in ("--web", "-w", "--host", "--port", "--no-browser"):
        from .web import main as web_main
        return web_main(argv[1:] if argv[0] in ("--web", "-w") else argv)

    from .cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
