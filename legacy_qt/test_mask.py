# -*- coding: utf-8 -*-
"""验证：真实屏幕上，覆盖层是否真的画出了遮罩（不依赖 widget.grab）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from snipper import SnipperOverlay, grab_virtual_desktop
from style import apply_theme

HERE = os.path.dirname(os.path.abspath(__file__))
app = QApplication(sys.argv)
apply_theme(app)

def brightness(pix):
    img = pix.toImage()
    n = 0
    total = 0
    for y in range(0, img.height(), 40):
        for x in range(0, img.width(), 40):
            c = img.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
            n += 1
    return total / (n * 3)


before = grab_virtual_deskop if False else grab_virtual_desktop()[0]
print("截图前屏幕平均亮度: %.1f" % brightness(before))

# 首次截图：启动覆盖层（模拟用户第一次按 PrintScreen）
snip = SnipperOverlay("region")
snip.start()
QTest.qWait(900)
on_screen = grab_virtual_desktop()[0]          # 抓真实屏幕（含覆盖层）
print("覆盖层显示后屏幕平均亮度: %.1f" % brightness(on_screen))
on_screen.save(os.path.join(HERE, "_test_mask_idle.png"))

# 拖拽中的实际屏幕
QTest.mousePress(snip, Qt.LeftButton, Qt.NoModifier, QPoint(400, 300))
for i in range(1, 5):
    QTest.mouseMove(snip, QPoint(400 + i * 70, 300 + i * 45))
    QTest.qWait(60)
QTest.qWait(200)
drag_screen = grab_virtual_desktop()[0]
drag_screen.save(os.path.join(HERE, "_test_mask_drag.png"))
print("拖拽中屏幕平均亮度: %.1f" % brightness(drag_screen))
QTest.mouseRelease(snip, Qt.LeftButton, Qt.NoModifier, QPoint(680, 480))
QTest.qWait(300)
print("done")
