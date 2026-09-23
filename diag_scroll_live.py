# -*- coding: utf-8 -*-
"""本机真实复现：真窗口 + 真滚轮 + 真抓帧 + 我们的匹配。

不依赖 Citrix，也不需要你手动操作：脚本自己打开一个有很多文件的 Explorer 窗口，
把鼠标移到列表上、发真实滚轮事件、抓帧，然后跑 find_scroll 看能不能算出位移。
同时把帧存下来，便于事后核对。

用法：python diag_scroll_live.py
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)          # 必须真实平台
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import find_scroll, pixmap_to_frame
from snipper import grab_logical_region, region_to_screen_pixels

u32 = ctypes.windll.user32
u32.OpenInputDesktop.restype = ctypes.c_void_p
if not u32.OpenInputDesktop(0, False, 0x0100):
    print("桌面已锁定：无法复现（抓屏只能是黑屏）。请解锁后重跑。")
    sys.exit(0)

OUT = Path.home() / ".pyshot" / "scroll_debug"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = r"C:\Explorer\pyshot"                   # 92 个文件，够滚


def find_explorer_window():
    """找目标 Explorer 窗口（类名 CabinetWClass，标题含 pyshot）。"""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "CabinetWClass" and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            found.append((hwnd, buf.value))
        return True

    u32.EnumWindows(cb, 0)
    for hwnd, title in found:
        if "pyshot" in title:
            return hwnd, title
    return (found[0] if found else (None, None))


def window_rect(hwnd):
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)


print("打开目标窗口…")
subprocess.Popen(["explorer.exe", TARGET])
time.sleep(2.0)
hwnd, title = find_explorer_window()
if hwnd is None:
    print("没找到 Explorer 窗口，放弃")
    sys.exit(0)
rect = window_rect(hwnd)
print(f"窗口: {title!r} rect=({rect.x()},{rect.y()},{rect.width()}x{rect.height()})")

# 选一块"列表区域"：避开标题栏/工具栏（顶部 ~180px）和左侧导航（~200px）
region = QRect(rect.x() + 220, rect.y() + 190,
               max(200, rect.width() - 460), max(200, rect.height() - 260))
print(f"选区: ({region.x()},{region.y()},{region.width()}x{region.height()})")

# 先点一下窗口，让它拿到焦点（这正是之前怀疑的点）
cx, cy = rect.x() + rect.width() // 2, rect.y() + 120
u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
u32.SetCursorPos(cx, cy)
time.sleep(0.3)
u32.mouse_event(0x0002, 0, 0, 0, 0)              # 左键按下
u32.mouse_event(0x0004, 0, 0, 0, 0)              # 左键抬起
time.sleep(0.4)
fg = u32.GetForegroundWindow()
print(f"点击后前台窗口 == 目标窗口 ? {fg == hwnd}")

# 鼠标移到列表中间（滚轮是发给光标下/前台窗口）
lx, ly = region.x() + region.width() // 2, region.y() + region.height() // 2
u32.SetCursorPos(lx, ly)
time.sleep(0.3)


def grab(tag):
    t0 = time.perf_counter()
    pix = grab_logical_region(region)
    dt = (time.perf_counter() - t0) * 1000
    pix.save(str(OUT / f"live_{tag}.png"))
    print(f"  抓帧 {tag}: {pix.width()}x{pix.height()} 耗时 {dt:.0f}ms")
    return pixmap_to_frame(pix)


def wheel(notches=3):
    """发真实滚轮事件（向下滚）。"""
    for _ in range(notches):
        u32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(-120).value, 0)
        time.sleep(0.12)


print("\n=== 第 1 组：不滚动，只抓两帧（基线：应当 s=0）===")
prev = grab("a0")
time.sleep(0.6)
cur = grab("a1")
s, diff = find_scroll(prev, cur)
print(f"  find_scroll → s={s} diff={diff:.1f}   （期望 0）")

print("\n=== 第 2 组：发 3 格滚轮后再抓（应当 s≈一行/几行的高度）===")
for i in range(1, 5):
    wheel(3)
    time.sleep(0.5)
    prev = cur
    cur = grab(f"b{i}")
    s, diff = find_scroll(prev, cur)
    mark = "✓" if s > 0 else "✗"
    print(f"  第 {i} 次滚动: find_scroll → s={s} diff={diff:.1f}  {mark}")

print(f"\n帧已存到 {OUT}（live_*.png）")
u32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)   # WM_CLOSE 关掉窗口
print("完成")
