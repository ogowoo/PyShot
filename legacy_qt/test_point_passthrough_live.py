# -*- coding: utf-8 -*-
"""真机验证：选滚动条模式下，选区内的点击能真的点到应用（同时被程序记录位置）。

做法：放一个带按钮的窗口，把选区挖空在按钮上，用真实鼠标输入点下去，
然后检查 ① 按钮收到了点击（穿透成功）② 程序也记录了锚点位置。
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton

from snipper import SnipperOverlay

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

app = QApplication(sys.argv)
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.clicks = 0
        self.btn = QPushButton("点我", self)
        self.btn.setGeometry(40, 40, 160, 60)
        self.btn.clicked.connect(self._on_click)
        self.setFixedSize(400, 240)
        self.move(300, 260)

    def _on_click(self):
        self.clicks += 1


win = Win()
win.show()
win.raise_()
win.activateWindow()
QTest.qWait(800)

# 按钮的全局中心（穿透点击的目标）
btn_center = win.btn.mapToGlobal(win.btn.rect().center())
print("按钮全局中心:", btn_center)

# 选区覆盖按钮所在窗口
region = QRect(win.x(), win.y(), win.width(), win.height())
ov = SnipperOverlay("region")
ov.mode = "point"
ov._active = True
ov._geo = QRect(0, 0, 1920, 1080)
ov.setGeometry(ov._geo)
ov.show()
QTest.qWait(150)
ov.set_point_hole(region)
QTest.qWait(200)

picked = []
ov.point_selected.connect(lambda p: picked.append(p))

# 真实鼠标点击（走系统输入，跟用户手动点击一样）
QCursor.setPos(btn_center)
QTest.qWait(80)
user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
QTest.qWait(60)
user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
QTest.qWait(400)

check("点击穿透到了应用（按钮收到点击）", win.clicks >= 1, f"clicks={win.clicks}")
check("程序同时记录了锚点", bool(picked), str(picked))
if picked:
    near = (picked[0] - btn_center).manhattanLength() <= 6
    check("记录的锚点就是点击处", near,
          f"{picked[0]} vs {btn_center}")
check("记录后覆盖层已收起", not ov.isVisible())

win.close()
print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("选区内可穿透点击验证通过 ✔")
