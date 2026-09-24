# -*- coding: utf-8 -*-
"""针对 Citrix Workspace（Desktop Viewer）窗口做真实滚动测试。

流程：找到 Citrix 会话窗口 → 聚焦 → 光标移到内容区 → 发真实滚轮 → 抓帧 →
      看 (1) 帧是不是真实画面（不是黑屏）(2) 有没有位移、能不能算出来。
帧存到 ~/.pyshot/scroll_debug/citrix_*.png 供事后核对。
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
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import find_scroll, find_scroll_strip, pixmap_to_frame
from snipper import grab_logical_region

u32 = ctypes.windll.user32
u32.OpenInputDesktop.restype = ctypes.c_void_p
if not u32.OpenInputDesktop(0, False, 0x0100):
    print("桌面已锁定，无法测试")
    sys.exit(0)

OUT = Path.home() / ".pyshot" / "scroll_debug"
OUT.mkdir(parents=True, exist_ok=True)


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
        blob = (b.value + " " + cls.value).lower()
        if ("desktop viewer" in blob or "citrix" in blob or "hdx" in blob
                or cls.value.startswith("WindowsForms10")):
            r = wintypes.RECT()
            u32.GetWindowRect(h, ctypes.byref(r))
            res.append((h, b.value, cls.value,
                        QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    u32.EnumWindows(cb, 0)
    for h, t, c, r in res:
        if "desktop viewer" in t.lower() or "citrix" in (t + c).lower():
            return h, t, c, r
    return (res[0][0], res[0][1], res[0][2], res[0][3]) if res else (None,) * 4


hwnd, title, cls, rect = find_citrix()
if hwnd is None:
    print("没找到 Citrix 窗口")
    sys.exit(0)
print(f"Citrix 窗口: {title!r}\n  类={cls}\n  矩形=({rect.x()},{rect.y()},{rect.width()}x{rect.height()})")

# 裁到屏幕内（窗口底边可能超出屏幕）
scr = QGuiApplication.primaryScreen().geometry()
region = rect.intersected(scr)
# 挤掉窗口边框/标题，取内容区中间一大块
inner = QRect(region.x() + 40, region.y() + 80,
              max(200, region.width() - 120), max(200, region.height() - 140))
print(f"  测试选区=({inner.x()},{inner.y()},{inner.width()}x{inner.height()})"
      f"（屏幕 {scr.width()}x{scr.height()}）")

# 聚焦 + 光标放到内容区中间（滚轮发给前台/光标下窗口）
u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
time.sleep(0.3)
u32.SetCursorPos(inner.x() + inner.width() // 2, inner.y() + inner.height() // 2)
time.sleep(0.4)
fg = u32.GetForegroundWindow()
print(f"  前台窗口 == 目标窗口 ? {fg == hwnd}")


def grab(tag):
    pix = grab_logical_region(inner)
    pix.save(str(OUT / f"citrix_{tag}.png"))
    return pixmap_to_frame(pix)


def wheel(n=3):
    for _ in range(n):
        u32.mouse_event(0x0800, 0, 0, ctypes.c_ulong(-120).value, 0)
        time.sleep(0.15)


# ---------- 1) 画面质量：是不是真实内容 ----------
f0 = grab("t0")
img = f0.rows
sample = [img[y][3 * (f0.w // 2) + 1] for y in range(0, f0.h, max(1, f0.h // 20))]
print(f"\n=== 1) 抓帧质量 ===")
print(f"  尺寸 {f0.w}x{f0.h}，采样亮度={sample}")
print(f"  是否纯色: {len(set(sample)) <= 2}   （纯色=抓不到内容）")

# ---------- 2) 发滚轮，看内容有没有动 ----------
print(f"\n=== 2) 真实滚轮测试 ===")
prev = f0
for i in range(1, 6):
    wheel(3)
    time.sleep(0.6)
    cur = grab(f"t{i}")
    changed = sum(1 for r in range(f0.h) if prev.rows[r] != cur.rows[r])
    s, diff = find_scroll(prev, cur)
    ss, ssc = find_scroll_strip(prev, cur)
    print(f"  第{i}次滚轮: 变化行={changed:4d}/{f0.h}  "
          f"find_scroll s={s:4d} (diff={diff:5.1f})  条带 s={ss:4d} (占比{ssc:.2f})")
    prev = cur

print(f"\n帧已存到 {OUT}\\citrix_*.png")
print("完成")
