# -*- coding: utf-8 -*-
"""对比实验：不同窗口标志 / 预热策略下，"首次显示覆盖层到真正上屏"的耗时。

每个变体都必须在独立进程里跑（首屏行为是每进程一次的）。
用法：python diag_first_show.py <variant>
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import snipper
from snipper import SnipperOverlay, grab_virtual_desktop
from style import apply_theme

variant = sys.argv[1] if len(sys.argv) > 1 else "current"

NO_BYPASS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
NO_BYPASS_NOTOOL = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

if variant.startswith("nobypass_notool"):
    snipper.OVERLAY_FLAGS = NO_BYPASS_NOTOOL
elif variant.startswith("nobypass"):
    snipper.OVERLAY_FLAGS = NO_BYPASS

app = QApplication([])
apply_theme(app)

base_pix = grab_virtual_desktop()[0]


def brightness(pix):
    img = pix.toImage()
    total = n = 0
    for y in range(0, img.height(), 60):
        for x in range(0, img.width(), 60):
            c = img.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
            n += 1
    return total / (n * 3)


base = brightness(base_pix)
ov = SnipperOverlay("region")

warm = "none"
if variant.endswith("+winid"):
    warm = "winid"
    ov.setGeometry(grab_virtual_desktop()[1])
    ov.winId()
elif variant.endswith("+showhide"):
    warm = "showhide"
    ov.setGeometry(grab_virtual_desktop()[1])
    ov.setWindowOpacity(0.0)
    ov.show()
    app.processEvents()
    ov.hide()
    ov.setWindowOpacity(1.0)
elif "+hold" in variant:
    # 启动预热：透明上屏并保持一段时间，等它真正被合成过一次再隐藏
    parts = variant.split("+")
    opacity = float(parts[1])
    hold_ms = int(parts[2].replace("hold", ""))
    warm = f"hold({opacity},{hold_ms}ms)"
    ov.setGeometry(grab_virtual_desktop()[1])
    ov.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    ov.setWindowOpacity(opacity)
    ov.show()
    ov.raise_()
    QTest.qWait(hold_ms)
    ov.hide()
    ov.setWindowOpacity(1.0)
    ov.setAttribute(Qt.WA_TransparentForMouseEvents, False)

QTest.qWait(400)

t0 = time.perf_counter()
ov.start("region")
latency = None
while time.perf_counter() - t0 < 10:
    QTest.qWait(10)
    if brightness(grab_virtual_desktop()[0]) < base * 0.75:
        latency = (time.perf_counter() - t0) * 1000
        break
ov.finish()
print(f"{variant:28s} 预热={warm:8s} 首次上屏: "
      + (f"{latency:.0f} ms" if latency else "!! 10 秒未上屏"))
