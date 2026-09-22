# -*- coding: utf-8 -*-
"""诊断：截图→编辑器管线是否存在重采样（100% 是否等于 1:1 物理像素）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from editor import EditorWindow
from scroller import pixmap_to_array
from snipper import SnipperOverlay, grab_virtual_desktop
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)

scr = QGuiApplication.primaryScreen()
print("=== 屏幕信息 ===")
print("geometry:", scr.geometry())
print("availableGeometry:", scr.availableGeometry())
print("devicePixelRatio:", scr.devicePixelRatio())
print("logicalDotsPerInch:", round(scr.logicalDotsPerInch(), 2))
print("physicalDotsPerInch:", round(scr.physicalDotsPerInch(), 2))
print("physicalSize:", scr.physicalSize())

bg, geo = grab_virtual_desktop()
print("\n=== 抓屏 ===")
print("virtualGeometry:", geo)
print("抓到的 pixmap 物理像素:", bg.width(), "x", bg.height())
print("抓到的 pixmap dpr:", bg.devicePixelRatio())
print("逻辑尺寸 = 物理/dpr:", bg.width() / bg.devicePixelRatio(),
      "x", bg.height() / bg.devicePixelRatio())
print("是否与逻辑几何一致:", abs(bg.width() / bg.devicePixelRatio() - geo.width()) < 1.5)

# --- 选区截图（走真实 snipper 路径） ---
snip = SnipperOverlay("region")
snip.start()
QTest.qWait(500)
snip._origin = QRect(100, 100, 1, 1).topLeft()
snip._current = QRect(0, 0, 401, 301).bottomRight()
snip._selecting = True
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import QPointF, Qt
snip.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(400, 300),
                                   Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
QTest.qWait(300)

captured = []
snip2 = SnipperOverlay("region")
snip2.captured.connect(lambda p: captured.append(p))
snip2.start()
QTest.qWait(400)
snip2._origin = QRect(0, 0, 1, 1).topLeft()
snip2._current = QRect(0, 0, 401, 301).bottomRight()
snip2._selecting = True
snip2.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(400, 300),
                                    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
QTest.qWait(300)
if not captured:
    print("!! 没有捕获到选区")
    sys.exit(1)
cap = captured[0]
print("\n=== 选区截图结果 ===")
print("物理像素:", cap.width(), "x", cap.height(), " dpr:", cap.devicePixelRatio())
print("逻辑尺寸:", cap.width() / cap.devicePixelRatio(),
      "x", cap.height() / cap.devicePixelRatio())

# --- 进编辑器：100% 时渲染结果应与源逐位一致 ---
win = EditorWindow(cap)
win.resize(900, 700)
win.show()
QTest.qWait(400)
canvas = win.canvas
canvas.set_zoom(1.0)
QTest.qWait(200)
print("\n=== 编辑器 100% 时 ===")
print("画布控件逻辑尺寸:", canvas.width(), "x", canvas.height())
print("底图物理像素:", canvas.base_pixmap.width(), "x", canvas.base_pixmap.height())
print("底图 dpr:", canvas.base_pixmap.devicePixelRatio())
print("状态栏显示:", win.zoom_label.text())
print("控件逻辑尺寸 == 物理像素? ", canvas.width() == canvas.base_pixmap.width())

out = canvas.render_result()
print("导出图物理像素:", out.width(), "x", out.height(), " dpr:", out.devicePixelRatio())
a = pixmap_to_array(cap)
b = pixmap_to_array(out)
if a.shape == b.shape:
    diff = int(np.abs(a.astype(int) - b.astype(int)).max())
    print("导出 vs 源截图 逐位最大差异:", diff, "（0 = 无重采样/无压缩）")
else:
    print("!! 导出尺寸不一致，发生了缩放:", a.shape, b.shape)

# 控件实拍：能反映系统实际光栅化后的像素密度（1:1 说明没有被放大显示）
shot = canvas.grab()
print("画布实拍物理像素:", shot.width(), "x", shot.height(),
      " dpr:", shot.devicePixelRatio())
if shot.width() == cap.width() and shot.height() == cap.height():
    d2 = int(np.abs(pixmap_to_array(shot).astype(int)
                    - pixmap_to_array(cap).astype(int)).max())
    print("画布实拍 vs 源截图 最大差异:", d2, "（接近 0 = 屏幕上是 1:1 物理像素）")
else:
    # 允许 1 像素的边缘留白（逻辑尺寸取整所致），比对重叠区域确认图像本身没被拉伸
    n = min(shot.width(), cap.width())
    m = min(shot.height(), cap.height())
    d2 = int(np.abs(pixmap_to_array(shot)[:m, :n].astype(int)
                    - pixmap_to_array(cap)[:m, :n].astype(int)).max())
    print(f"画布实拍尺寸 {shot.width()}x{shot.height()} 比源多 "
          f"{shot.width() - cap.width()}x{shot.height() - cap.height()} 像素（取整留白）")
    print(f"重叠区域 {n}x{m} 逐位最大差异: {d2}", "（0 = 图像本身 1:1，无拉伸）" if d2 == 0 else "（有缩放！）")

core = "结论："
if canvas.width() != canvas.base_pixmap.width():
    print(core, "100% 时控件逻辑尺寸 != 图像物理像素 → 在缩放显示器上会被系统放大（看起来拉伸）")
else:
    print(core, "当前机器 dpr=1，100% 即 1:1；若显示器有缩放，需要按 dpr 计算画布尺寸")
win.close()
