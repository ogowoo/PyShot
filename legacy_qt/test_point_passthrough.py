# -*- coding: utf-8 -*-
"""选滚动条模式：选区外遮罩、选区内鼠标穿透（能真的点到应用）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from snipper import SnipperOverlay

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


ov = SnipperOverlay("region")
ov.mode = "point"
ov._active = True
ov._geo = QRect(0, 0, 800, 600)
ov.setGeometry(ov._geo)
ov.show()
QTest.qWait(100)

# 选区挖空后：窗口 mask 应该等于"整屏 − 选区"
region = QRect(200, 150, 300, 200)
ov.set_point_hole(region)
mask = ov.mask()
check("选区外仍然是遮罩", mask.contains(QPoint(50, 50)))
check("选区左上角已挖空（可穿透）", not mask.contains(QPoint(210, 160)))
check("选区中心已挖空（可穿透）", not mask.contains(QPoint(350, 250)))
check("选区右下角已挖空", not mask.contains(QPoint(490, 340)))
check("仍会绘制遮罩（选区外）", mask.contains(QPoint(790, 590)))
check("提示条落在选区外（可见）",
      not region.contains(ov._hint_anchor(region)),
      str(ov._hint_anchor(region)))

# 与本次覆盖层所在的屏没有交集时：不挖空（mask 为空 = 整屏都画遮罩）
ov.set_point_hole(QRect(5000, 5000, 100, 100))
check("无交集时不挖空（整屏遮罩）", ov.mask().isEmpty())

# 轮询点击：模拟左键按下（在选区内 → 触发 point_selected）
ov.set_point_hole(region)
picked = []
ov.point_selected.connect(lambda p: picked.append(p))
import snipper as sm
real_get = sm.user32.GetAsyncKeyState
real_pos = sm.QCursor.pos
try:
    sm.QCursor.pos = staticmethod(lambda: QPoint(350, 250))
    # 先松开，再按下
    sm.user32.GetAsyncKeyState = staticmethod(lambda vk: 0)
    ov._poll_point_click()
    check("未按下时不触发", not picked)
    sm.user32.GetAsyncKeyState = staticmethod(lambda vk: 0x8000)
    ov._poll_point_click()
finally:
    sm.user32.GetAsyncKeyState = real_get
    sm.QCursor.pos = real_pos
check("选区内的真实点击被捕获", picked == [QPoint(350, 250)], str(picked))
check("触发后窗口已隐藏", not ov.isVisible())
check("触发后 mask 已清空（不影响下次使用）", ov.mask().isEmpty())
check("触发后轮询停止", not ov._point_timer.isActive())

# 在选区外按下：不触发，且不消耗
ov2 = SnipperOverlay("region")
ov2.mode = "point"
ov2._geo = QRect(0, 0, 800, 600)
ov2.setGeometry(ov2._geo)
ov2._active = True
ov2.set_point_hole(region)
got2 = []
ov2.point_selected.connect(lambda p: got2.append(p))
try:
    sm.QCursor.pos = staticmethod(lambda: QPoint(60, 60))     # 遮罩区
    sm.user32.GetAsyncKeyState = staticmethod(lambda vk: 0x8000)
    ov2._poll_point_click()
finally:
    sm.user32.GetAsyncKeyState = real_get
    sm.QCursor.pos = real_pos
check("点遮罩区不当作滑块位置", not got2)
ov2.finish()

# 结束会话必须清掉 mask，否则下次框选会看不到
ov3 = SnipperOverlay("region")
ov3._geo = QRect(0, 0, 800, 600)
ov3.setGeometry(ov3._geo)
ov3.set_point_hole(region)
check("挖空状态下 mask 非空", not ov3.mask().isEmpty())
ov3.finish()
check("finish 会清掉 mask", ov3.mask().isEmpty())

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("选滚动条（可穿透点击）测试通过 ✔")
