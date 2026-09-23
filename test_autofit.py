# -*- coding: utf-8 -*-
"""窗口缩放时图片自适应（适应模式）测试。

契约：
- 新打开的标签处于"适应模式"，窗口变大/变小 → 图片跟着适配
- 用户一旦**手动缩放**（Ctrl+滚轮 / 缩放按钮 / 实际像素），退出适应模式，
  之后改窗口大小不再动缩放（不打断看细节）
- 点「适应窗口」重新进入适应模式
- 不会因为适配引起反复触发的死循环（缩放稳定下来）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import EditorWindow

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def make_win(w=1000, h=700, img=(1200, 900)):
    pix = QPixmap(*img)
    pix.fill(QColor("#3366cc"))
    win = EditorWindow(pix)
    win.resize(w, h)
    win.show()
    app.processEvents()
    win._autofit_current()
    app.processEvents()
    return win


win = make_win()
canvas = win.canvas
check("新标签进入适应模式", canvas.fit_mode is True)
z_fit = canvas.zoom
check("适应模式下缩放是合身的（< 100%）", z_fit < 1.0, f"{z_fit:.3f}")

# ---------- 窗口变小 → 图片跟着变小 ----------
win.resize(600, 420)
app.processEvents()
win._autofit_current()
app.processEvents()
z_small = canvas.zoom
check("窗口变小后图片跟着缩小", z_small < z_fit, f"{z_fit:.3f} -> {z_small:.3f}")

# ---------- 窗口变大 → 图片跟着变大 ----------
win.resize(1400, 950)
app.processEvents()
win._autofit_current()
app.processEvents()
z_big = canvas.zoom
check("窗口变大后图片跟着放大", z_big > z_small, f"{z_small:.3f} -> {z_big:.3f}")
check("放大不会超过 100%（小图不硬撑）", z_big <= 1.0, f"{z_big:.3f}")

# ---------- 手动缩放 → 退出适应模式 ----------
win._zoom_step(1.25)                       # 相当于点放大按钮
app.processEvents()
check("手动缩放后退出适应模式", canvas.fit_mode is False)
z_manual = canvas.zoom
win.resize(800, 560)
app.processEvents()
win._autofit_current()
app.processEvents()
check("退出适应模式后，改窗口大小不再动缩放",
      abs(canvas.zoom - z_manual) < 1e-6, f"{z_manual:.3f} -> {canvas.zoom:.3f}")

# Ctrl+滚轮也算手动缩放
win.resize(1000, 700)
app.processEvents()
win._autofit_current()
app.processEvents()
z0 = canvas.zoom
ev = QWheelEvent(QPointF(canvas.rect().center()),
                 QPointF(canvas.mapToGlobal(canvas.rect().center())),
                 QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                 Qt.ControlModifier, Qt.NoScrollPhase, False)
win.wheelEvent(ev)
app.processEvents()
check("Ctrl+滚轮缩放也退出适应模式", canvas.fit_mode is False)
check("Ctrl+滚轮确实改变了缩放", canvas.zoom > z0, f"{z0:.3f} -> {canvas.zoom:.3f}")

# ---------- 「适应窗口」重新进入适应模式 ----------
win.fit_to_window()
app.processEvents()
check("点「适应窗口」回到适应模式", canvas.fit_mode is True)
z_refit = canvas.zoom
win.resize(700, 500)
app.processEvents()
win._autofit_current()
app.processEvents()
check("回到适应模式后又能跟着窗口变了", canvas.zoom < z_refit,
      f"{z_refit:.3f} -> {canvas.zoom:.3f}")

# ---------- 稳定性：连续适配后缩放不变（没有来回抖）----------
z_prev = canvas.zoom
for _ in range(3):
    win._autofit_current()
    app.processEvents()
check("连续适配是稳定的（不会来回抖）", abs(canvas.zoom - z_prev) < 1e-6,
      f"{z_prev:.3f} -> {canvas.zoom:.3f}")

# ---------- 多标签：各自记住自己的模式 ----------
win.add_canvas(QPixmap(400, 300))
app.processEvents()
win._autofit_current()
canvas2 = win.canvas
check("新标签也是适应模式", canvas2.fit_mode is True)
canvas2.fit_mode = False                   # 模拟用户在新标签里手动缩放过
win.tabs.setCurrentIndex(0)                # 切回第一个标签
app.processEvents()
check("切回旧标签不会改变它的模式", canvas.fit_mode is True)
check("切标签不会把别的标签也置为非适应", canvas2.fit_mode is False)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("窗口自适应测试通过 ✔")
