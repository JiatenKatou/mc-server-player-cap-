"""开发辅助脚本：启动 GUI、按窗口标题定位并抓取窗口内容（用于生成文档配图）。

    python tools/capture_gui.py docs/screenshot.png              # 默认桌面 CPU
    python tools/capture_gui.py docs/mobile.png --cpu i7-12700H  # 指定 CPU（演示散热联动）

使用 Windows 的 PrintWindow API 直接渲染窗口内容，不依赖窗口在屏幕上的位置，
因此不会出现坐标偏移导致的右侧裁切。
"""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

TITLE_KEY = "人数上限计算器"
PW_RENDERFULLCONTENT = 0x00000002


def find_window() -> int:
    user32 = ctypes.windll.user32
    found: list = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if TITLE_KEY in buf.value:
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def capture(hwnd: int, out: str) -> None:
    """用 GDI + PrintWindow 抓窗口内容（纯 ctypes，无需 pywin32）。"""
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    hdc_window = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    gdi32.SelectObject(hdc_mem, hbmp)

    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h          # 负数 = 自上而下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0      # BI_RGB

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    img.save(out)

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="抓取计算器窗口截图（默认抓本地网页版，--desktop 抓 tkinter 窗口）")
    ap.add_argument("out", nargs="?", default="docs/screenshot.png", help="输出图片路径")
    ap.add_argument("--desktop", action="store_true", help="抓 tkinter 桌面窗口而不是网页版")
    ap.add_argument("--port", type=int, default=8790, help="网页版临时端口")
    ap.add_argument("--cpu", default=None, help="把界面初始 CPU 设为指定型号（演示散热联动）")
    args = ap.parse_args()

    import os
    env = dict(os.environ)
    if args.cpu:
        env["MC_CALC_INIT_CPU"] = args.cpu

    if args.desktop:
        target = [sys.executable, "-m", "mc_player_calc.gui"]
    else:
        env["PYTHONIOENCODING"] = "utf-8"
        target = [sys.executable, "-m", "mc_player_calc.web",
                  "--port", str(args.port), "--no-browser"]

    proc = subprocess.Popen(target, env=env)
    try:
        hwnd = 0
        for _ in range(40):
            time.sleep(0.5)
            hwnd = find_window()
            if hwnd:
                break
        if not hwnd:
            print("未找到窗口", file=sys.stderr)
            return 1
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(2.5)
        capture(hwnd, args.out)
        print("截图已保存:", args.out)
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
