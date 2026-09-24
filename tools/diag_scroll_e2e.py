# -*- coding: utf-8 -*-
"""端到端验证目标："能顺利完成滚动窗口截屏"。

走**产品自己的 ScrollCapture**（不是单独调 find_scroll），用**整个窗口**做选区
（用户实际失败的场景），真实滚轮自动滚动，看最终能不能拼出一张长图。

判定：
- 成功（finished_ok）且输出高度 > 选区高度 → 拼接成功 ✓
- 失败信号 / 高度没变 → ✗
"""
import ctypes
import os
import subprocess
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
    print("桌面已锁定，无法端到端验证（请解锁后重跑）")
    sys.exit(0)

TARGET = r"C:\Explorer\pyshot"
OUT = Path.home() / ".pyshot" / "scroll_debug"


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


subprocess.Popen(["explorer.exe", TARGET])
time.sleep(2.0)
hwnd = find_win()
if not hwnd:
    print("没找到 Explorer 窗口")
    sys.exit(0)
r = wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(r))
win = QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)

# **整个窗口**做选区 —— 正是用户失败的那种框法
region = QRect(win.x() + 4, win.y() + 4, win.width() - 8, win.height() - 8)
print(f"端到端：窗口 {win.width()}x{win.height()}，选区（整个窗口）"
      f" {region.width()}x{region.height()}")

# 聚焦 + 光标放到列表中间（滚轮要发给前台窗口）
u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
u32.SetCursorPos(win.x() + win.width() // 2, win.y() + win.height() // 2)
time.sleep(0.4)

result = {}


def on_ok(pix):
    result["pix"] = pix
    result["ok"] = True
    print(f"  finished_ok: 输出 {pix.width()}x{pix.height()}")


def on_fail(msg):
    result["ok"] = False
    result["msg"] = msg
    print(f"  failed: {msg[:100]}")


driver = ScrollDriver("wheel", region)
cap = ScrollCapture(region, manual=False, driver=driver)
cap.finished_ok.connect(on_ok)
cap.failed.connect(on_fail)
cap.start()

deadline = time.time() + 40
while time.time() < deadline and "ok" not in result:
    app.processEvents()
    time.sleep(0.05)

# 收尾：把还在跑的控制条停掉
try:
    cap.stop()
except Exception:                                  # noqa: BLE001
    pass
u32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)

print()
if result.get("ok"):
    pix = result["pix"]
    OUT.mkdir(parents=True, exist_ok=True)
    pix.save(str(OUT / "e2e_result.png"))
    grew = pix.height() > region.height()
    print(f"结果: {pix.width()}x{pix.height()}（选区高 {region.height()}）"
          f"{'  ✓ 拼出了更长的图' if grew else '  ✗ 高度没增加'}")
    print(f"已存到 {OUT / 'e2e_result.png'}")
    sys.exit(0 if grew else 1)
else:
    print(f"结果: 失败 —— {result.get('msg', '超时未完成')[:200]}")
    sys.exit(1)
