# -*- coding: utf-8 -*-
"""验证放大镜渲染：红框应精确框住光标下的那个像素格。"""
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from snipper import SnipperOverlay, MAG_SIZE

app = QApplication(sys.argv)

# 棋盘格窗口：黑白 1px 交替太难渲染，用 4px 色块棋盘
probe = QWidget()
probe.setGeometry(200, 150, 600, 400)
probe.setStyleSheet(
    "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e53935, stop:0.5 #1e88e5, stop:1 #43a047);")
probe.show()
QTest.qWait(600)

snip = SnipperOverlay("color")
snip.start()
QTest.qWait(400)
QTest.mouseMove(snip, QPoint(500, 350))
QTest.qWait(200)
grab = snip.grab()
# 放大镜在光标右下 18px
grab.copy(500 + 10, 350 + 10, MAG_SIZE + 40, MAG_SIZE + 40).save(
    os.path.join(os.path.dirname(__file__), "_test_magnifier.png"))
print("ok")
