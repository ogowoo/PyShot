# -*- coding: utf-8 -*-
"""交互测试：真实窗口环境下模拟框选，抓取覆盖层画面验证选区可见性。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from snipper import SnipperOverlay, grab_virtual_desktop

app = QApplication(sys.argv)

# 1) 先看桌面抓图是否正常
bg, geo = grab_virtual_desktop()
bg.save(os.path.join(os.path.dirname(__file__), "_test_desktop.png"))
print("virtual geo:", geo, "dpr:", bg.devicePixelRatio())

# 2) 启动覆盖层并模拟拖拽
snip = SnipperOverlay()
snip.captured.connect(lambda p: print("captured:", p.size(), "dpr:", p.devicePixelRatio()))
snip.start()
QTest.qWait(800)

QTest.mousePress(snip, Qt.LeftButton, Qt.NoModifier, QPoint(200, 200))
for i in range(1, 8):
    QTest.mouseMove(snip, QPoint(200 + i * 60, 200 + i * 40))
    QTest.qWait(40)
# 拖拽中抓图：选区应该比周围亮、有蓝色边框和尺寸标签
snip.grab().save(os.path.join(os.path.dirname(__file__), "_test_during.png"))
QTest.mouseRelease(snip, Qt.LeftButton, Qt.NoModifier, QPoint(620, 480))
QTest.qWait(300)

# 3) 取色模式：先放一个已知颜色的窗口作为真值，再验证取色精确
from PySide6.QtWidgets import QWidget
probe = QWidget()
probe.setGeometry(300, 300, 400, 300)
probe.setStyleSheet("background: #1e88e5;")  # 真值蓝色块
probe.show()
QTest.qWait(600)

picked = []
snip2 = SnipperOverlay("color")
snip2.color_picked.connect(lambda c: picked.append(c))
snip2.start()
QTest.qWait(500)
QTest.mouseMove(snip2, QPoint(500, 400))
QTest.qWait(100)
QTest.mouseClick(snip2, Qt.LeftButton, Qt.NoModifier, QPoint(500, 400))
QTest.qWait(200)
probe.close()
got = picked[0] if picked else None
print("取色结果:", got.name() if got else "无", " 真值: #1e88e5")
assert got is not None and got.isValid()
assert got.name() == "#1e88e5", f"取色不准: {got.name()} != #1e88e5"
print("取色精确 ✓")
print("done")
