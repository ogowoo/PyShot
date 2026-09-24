# -*- coding: utf-8 -*-
"""Citrix 第三轮：用**产品真实的 ScrollDriver** 量"一轮滚轮到底滚了多少"。

前一轮端到端的现象：ScrollCapture 请求 step=0.45*380≈171px，
驱动按 px_per_unit=100 折算成 notches=round(1.71)=2（一个 mouse_event 带 -240），
结果三帧 s 全是 0（画面根本没动），被判成"滚到底了"，输出还是 380px 高。

本轮直接调 ScrollDriver.__call__，逐个步长量：
  请求 63px → 1 格、126px → 1 格、171px → 2 格、252px → 3 格
看每格到底对应多少像素，以及"-240 一次性发"会不会被丢掉。
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import ScrollDriver, find_scroll, find_scroll_strip, pixmap_to_frame
from snipper import grab_logical_region

u32 = ctypes.windll.user32
u32.OpenInputDesktop.restype = ctypes.c_void_p
if not u32.OpenInputDesktop(0, False, 0x0100):
    print("桌面已锁定")
    sys.exit(0)

OUT = Path.home() / ".pyshot" / "scroll_debug"
OUT.mkdir(parents=True, exist_ok=True)


def find_citrix():
    res = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, cls, 256)
        n = u32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, b, n + 1)
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

# 允许命令行覆盖选区：python diag_citrix3.py x y w h
if len(sys.argv) >= 5:
    REGION = QRect(int(sys.argv[1]), int(sys.argv[2]),
                   int(sys.argv[3]), int(sys.argv[4]))
else:
    REGION = QRect(win.x() + 300, win.y() + 120, 660, 380)
print(f"选区=({REGION.x()},{REGION.y()},{REGION.width()}x{REGION.height()})")

u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
time.sleep(0.4)
print(f"前台窗口 == 目标 ? {u32.GetForegroundWindow() == hwnd}")


def grab(tag=None):
    pix = grab_logical_region(REGION)
    if tag:
        pix.save(str(OUT / f"citrix3_{tag}.png"))
    return pixmap_to_frame(pix)


def raw_wheel(delta, times=1):
    """不经过驱动，直接发滚轮（用于"先滚回顶部"这类粗操作）。"""
    u32.SetCursorPos(REGION.center().x(), REGION.center().y())
    for _ in range(times):
        u32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(delta).value, 0)
        time.sleep(0.12)


def measure(prev, tag):
    cur = grab(tag)
    changed = sum(1 for r in range(prev.h) if prev.rows[r] != cur.rows[r])
    s, diff = find_scroll(prev, cur)
    ss, ssc = find_scroll_strip(prev, cur)
    return cur, changed, s, diff, ss, ssc


print("\n=== 先滚回顶部 ===")
raw_wheel(120, 25)
time.sleep(1.0)

driver = ScrollDriver("wheel", REGION)
print(f"初始 px_per_unit={driver.px_per_unit} mode={driver.mode}")

print("\n=== 用真实 ScrollDriver 逐步滚动 ===")
prev = grab("s0")
print(f"  基准帧 {prev.w}x{prev.h}")
for i, step in enumerate((63.0, 126.0, 171.0, 252.0), 1):
    driver(step)
    want_notches = int(min(15, max(1, round(step / driver.px_per_unit))))
    time.sleep(0.8)
    prev, changed, s, diff, ss, ssc = measure(prev, f"s{i}")
    print(f"  请求 {step:6.1f}px → 发 {int(driver.last_units)} 格（期望 {want_notches}）: "
          f"变化行={changed:3d}/{prev.h}  全局 s={s:4d}(diff={diff:5.1f})  "
          f"条带 s={ss:4d}({ssc:.2f})  "
          f"实测每格={s / max(1, driver.last_units):6.1f}px")

print("\n=== 对照：绕过驱动，直接发 1 格 ===")
for i in range(1, 4):
    raw_wheel(-120, 1)
    time.sleep(0.8)
    prev, changed, s, diff, ss, ssc = measure(prev, f"raw{i}")
    print(f"  第{i}次 1 格: 变化行={changed:3d}/{prev.h}  全局 s={s:4d}(diff={diff:5.1f})  "
          f"条带 s={ss:4d}({ssc:.2f})")

print("\n=== 对照：绕过驱动，一次发 3 格（-360）===")
for i in range(1, 3):
    raw_wheel(-360, 1)
    time.sleep(0.8)
    prev, changed, s, diff, ss, ssc = measure(prev, f"raw3_{i}")
    print(f"  第{i}次 3 格: 变化行={changed:3d}/{prev.h}  全局 s={s:4d}(diff={diff:5.1f})  "
          f"条带 s={ss:4d}({ssc:.2f})")

print(f"\n帧已存到 {OUT}\\citrix3_*.png")
