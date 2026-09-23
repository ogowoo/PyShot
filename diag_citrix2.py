# -*- coding: utf-8 -*-
"""Citrix 第二轮：只框列表区域 + 每次 1 格滚轮（对照上一轮）。

上一轮（整窗口 + 每次 3 格）：
  抓帧没问题、滚轮也送到了（列表滚了约 9 行 ≈198px），
  但帧里大半是静止的远程桌面背景 → 真位移的命中率只有 0.21，被"位移 0"的 0.38 压过。
本轮验证：只框列表 + 小步滚动，能不能顺利拼上。
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import find_scroll, find_scroll_strip, pixmap_to_frame
from snipper import grab_logical_region

u32 = ctypes.windll.user32
u32.OpenInputDesktop.restype = ctypes.c_void_p
if not u32.OpenInputDesktop(0, False, 0x0100):
    print("桌面已锁定")
    sys.exit(0)

OUT = Path.home() / ".pyshot" / "scroll_debug"


def find_citrix():
    res = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        n = u32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, b, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, cls, 256)
        if "desktop viewer" in b.value.lower() or cls.value.startswith("WindowsForms10"):
            r = wintypes.RECT()
            u32.GetWindowRect(h, ctypes.byref(r))
            res.append((h, b.value, QRect(r.left, r.top, r.right - r.left,
                                          r.bottom - r.top)))
        return True

    u32.EnumWindows(cb, 0)
    return res[0] if res else (None, None, None)


hwnd, title, win = find_citrix()
if hwnd is None:
    print("没找到 Citrix 窗口")
    sys.exit(0)
print(f"Citrix 窗口 {title!r} ({win.x()},{win.y()},{win.width()}x{win.height()})")

# 上一轮的整窗口帧里量出来的列表位置（相对窗口）：
#   列表大约在窗口内 x 300..960, y 120..500
LIST = QRect(win.x() + 300, win.y() + 120, 660, 380)
print(f"本轮选区（只框列表）=({LIST.x()},{LIST.y()},{LIST.width()}x{LIST.height()})")

u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
time.sleep(0.3)
u32.SetCursorPos(LIST.x() + LIST.width() // 2, LIST.y() + LIST.height() // 2)
time.sleep(0.4)
print(f"前台窗口 == 目标 ? {u32.GetForegroundWindow() == hwnd}")


def grab(tag):
    pix = grab_logical_region(LIST)
    pix.save(str(OUT / f"citrix2_{tag}.png"))
    return pixmap_to_frame(pix)


def wheel(n):
    for _ in range(n):
        u32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(-120).value, 0)
        time.sleep(0.15)


print("\n=== 每次 1 格滚轮，只框列表 ===")
prev = grab("a0")
print(f"  抓帧 a0: {prev.w}x{prev.h}")
for i in range(1, 7):
    wheel(1)
    time.sleep(0.7)
    cur = grab(f"a{i}")
    changed = sum(1 for r in range(prev.h) if prev.rows[r] != cur.rows[r])
    s, diff = find_scroll(prev, cur)
    ss, ssc = find_scroll_strip(prev, cur)
    mark = "✓" if s > 0 else ("=" if s == 0 else "✗")
    print(f"  第{i}次: 变化行={changed:3d}/{prev.h}  "
          f"s={s:4d} (diff={diff:5.1f})  条带 s={ss:4d} ({ssc:.2f}) {mark}")
    prev = cur

print(f"\n帧已存到 {OUT}\\citrix2_*.png")
