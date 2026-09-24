# -*- coding: utf-8 -*-
"""Citrix 端到端：用产品自己的 ScrollCapture 对 Desktop Viewer 里的列表做滚动截图。

选区取列表区域（上一轮已量出：窗口内 x 300..960, y 120..500），
自动滚轮模式，看最终能不能拼出比选区更长的图。
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
from style import apply_theme

apply_theme(app)

from scroller import ScrollCapture, ScrollDriver

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
region = QRect(win.x() + 300, win.y() + 120, 660, 380)
print(f"Citrix 端到端：{title!r}\n  选区=({region.x()},{region.y()},"
      f"{region.width()}x{region.height()})")

u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
u32.SetCursorPos(region.x() + region.width() // 2,
                 region.y() + region.height() // 2)
time.sleep(0.5)

result = {}


def on_ok(pix):
    result["pix"] = pix
    result["ok"] = True
    print(f"  finished_ok: 输出 {pix.width()}x{pix.height()}")


def on_fail(msg):
    result["ok"] = False
    result["msg"] = msg
    print(f"  failed: {msg[:140]}")


driver = ScrollDriver("wheel", region)
cap = ScrollCapture(region, manual=False, driver=driver)
cap.finished_ok.connect(on_ok)
cap.failed.connect(on_fail)
cap.start()

deadline = time.time() + 45
while time.time() < deadline and "ok" not in result:
    app.processEvents()
    time.sleep(0.05)

try:
    cap.stop()
except Exception:                                  # noqa: BLE001
    pass

print()
if result.get("ok"):
    pix = result["pix"]
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "e2e_citrix.png"
    pix.save(str(dst))
    grew = pix.height() > region.height()
    print(f"结果: {pix.width()}x{pix.height()}（选区高 {region.height()}）"
          f"{'  ✓ 拼出了更长的图' if grew else '  ✗ 高度没增加'}")
    print(f"已存到 {dst}")
    sys.exit(0 if grew else 1)
else:
    print(f"结果: 失败 —— {result.get('msg', '超时未完成')[:200]}")
    sys.exit(1)
