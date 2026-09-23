# -*- coding: utf-8 -*-
"""编辑器"跟手"测试：图形必须画在鼠标所在的位置（含系统缩放 dpr≠1 的情形）。

背景
====
底图是 dpr 感知绘制的（QPixmap 带 devicePixelRatio 时 Qt 按逻辑尺寸 P/dpr 画），
而图形用"图像物理像素"坐标。少了 1/dpr 那一步变换时，dpr≠1（系统缩放非 100%）
就会让图形整体偏离鼠标 dpr 倍 —— 用户看到的就是"画图不跟手"。

本测试模拟：在某个控件坐标按下鼠标开始画 → 检查渲染结果里图形是否落在该位置。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import Canvas
from shapes import StepShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def make_canvas(dpr, zoom):
    pix = QPixmap(1000, 700)
    pix.fill(QColor("#f0f0f2"))
    p = QPainter(pix)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#dfe3e8"))
    for y in range(0, 700, 40):            # 加点纹理，便于区分底图与图形
        p.drawRect(0, y, 1000, 2)
    p.end()
    pix.setDevicePixelRatio(dpr)
    c = Canvas(pix)
    c.resize(c.sizeHint())
    c.zoom = zoom
    return c


def shape_centroid(canvas, color=QColor("#ff0000"), tol=40):
    """渲染画布，返回指定颜色像素的重心（控件坐标）。"""
    canvas.repaint()
    img = canvas.grab().toImage().convertToFormat(QImage.Format_RGB888)
    sx = sy = n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if abs(c.red() - color.red()) < tol and c.green() < tol \
                    and c.blue() < tol:
                sx += x
                sy += y
                n += 1
    if not n:
        return None, 0
    return QPointF(sx / n, sy / n), n


print("=== 图形是否画在鼠标位置（含 dpr≠1）===")
for dpr in (1.0, 1.25, 1.5, 2.0):
    for zoom in (1.0, 0.7, 1.5):
        c = make_canvas(dpr, zoom)
        mouse = QPointF(300, 220)                  # 模拟鼠标在控件里的位置
        img_pt = c.to_image(mouse)                 # 期望的图形参考点
        # 在该图像点画一个圆心即此点的实心圆（不透明，便于定位重心）
        sh = StepShape(QColor("#ff0000"), 2, img_pt, 1, font_size=20,
                       diameter=40)
        c.shapes.append(sh)
        centroid, n = shape_centroid(c)
        if centroid is None:
            check(f"dpr={dpr} zoom={zoom} 找到图形像素", False, "没找到红色像素")
            continue
        dx, dy = centroid.x() - mouse.x(), centroid.y() - mouse.y()
        # 允许 3px 误差（取整、抗锯齿、边界裁剪）
        ok = abs(dx) <= 3.0 and abs(dy) <= 3.0
        check(f"dpr={dpr} zoom={zoom} 图形落在鼠标位置", ok,
              f"偏差 dx={dx:+.1f} dy={dy:+.1f} px（红色像素 {n} 个）")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("编辑器跟手测试通过 ✔")
