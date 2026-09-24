# -*- coding: utf-8 -*-
"""A/B 对照：同一窗口、同一次真实滚动，只换"选区"看匹配结果。

左边 = 只框列表（排除标题栏/工具栏/侧栏）
右边 = 框整个窗口（用户实际的选区）
若 A 成功、B 失败 → 病根就是"选区里混进了大块静止区域"。
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

app = QApplication([])
from pathlib import Path

from scroller import find_scroll, pixmap_to_frame
from snipper import grab_logical_region

u32 = ctypes.windll.user32
u32.OpenInputDesktop.restype = ctypes.c_void_p
if not u32.OpenInputDesktop(0, False, 0x0100):
    print("桌面已锁定，无法复现")
    sys.exit(0)

OUT = Path.home() / ".pyshot" / "scroll_debug"
OUT.mkdir(parents=True, exist_ok=True)
TARGET = r"C:\Explorer\pyshot"


def find_win():
    res = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, cls, 256)
        if cls.value == "CabinetWClass" and u32.IsWindowVisible(h):
            n = u32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, b, n + 1)
            res.append((h, b.value))
        return True

    u32.EnumWindows(cb, 0)
    for h, t in res:
        if "pyshot" in t:
            return h
    return res[0][0] if res else None


def rect_of(h):
    r = wintypes.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)


def wheel(n=3):
    for _ in range(n):
        u32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(-120).value, 0)
        time.sleep(0.12)


subprocess.Popen(["explorer.exe", TARGET])
time.sleep(2.0)
hwnd = find_win()
if not hwnd:
    print("没找到窗口")
    sys.exit(0)
win = rect_of(hwnd)
print(f"窗口 rect=({win.x()},{win.y()},{win.width()}x{win.height()})\n")

REGIONS = [
    ("A 只框列表（排除外壳）",
     QRect(win.x() + 220, win.y() + 190,
           max(200, win.width() - 460), max(200, win.height() - 260))),
    ("B 框整个窗口（用户实际）",
     QRect(win.x() + 4, win.y() + 4, win.width() - 8, win.height() - 8)),
]

print(f"{'选区':<26}{'尺寸':<14}{'静止时':<12}{'滚动后':<22}")
print("-" * 74)
for label, region in REGIONS:
    # 让窗口回顶部并聚焦
    cx, cy = win.x() + win.width() // 2, win.y() + 120
    u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    u32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    for _ in range(30):                      # 滚回顶部
        u32.mouse_event(0x0800, 0, 0, 120, 0)
    time.sleep(0.6)

    lx, ly = region.x() + region.width() // 2, region.y() + region.height() // 2
    u32.SetCursorPos(lx, ly)
    time.sleep(0.3)

    f0 = pixmap_to_frame(grab_logical_region(region))
    time.sleep(0.5)
    f1 = pixmap_to_frame(grab_logical_region(region))
    s_still, _ = find_scroll(f0, f1)

    results = []
    prev = f1
    for i in range(3):
        wheel(3)
        time.sleep(0.5)
        cur = pixmap_to_frame(grab_logical_region(region))
        s, diff = find_scroll(prev, cur)
        results.append(s)
        prev = cur
    tag = "✓ 有位移" if any(s > 0 for s in results) else "✗ 算不出位移"
    print(f"{label:<26}{region.width()}x{region.height():<9}"
          f"s={s_still:<10}滚动后 s={results}  {tag}")

    (OUT / f"ab_{label[0]}_top.png").write_bytes(b"")   # 占位，避免误读
    grab_logical_region(region).save(str(OUT / f"ab_{label[0]}.png"))

u32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)
print(f"\n帧已存到 {OUT}\\ab_*.png")
