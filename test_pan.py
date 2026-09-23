# -*- coding: utf-8 -*-
"""拖动查看（平移画面）测试。

背景：状态栏一直写着"中键拖动滚动"，但 mousePressEvent 对非左键直接 return ——
也就是说中键其实从来没生效过。所以这里必须**真的模拟拖动、断言滚动条动了**，
光看代码有实现是不够的。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import TOOLS, EditorWindow

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def make_win(w=1200, h=900):
    """造一张比视口大的图，保证滚动条有可移动范围。"""
    pix = QPixmap(w, h)
    pix.fill(QColor("#3366cc"))
    win = EditorWindow(pix)
    win.resize(500, 400)
    win.show()
    app.processEvents()
    # 放大到 300%，这样画面比视口大、滚动条才有范围
    win.canvas.set_zoom(3.0)
    app.processEvents()
    return win


def press(canvas, pos, button=Qt.LeftButton, mods=Qt.NoModifier):
    e = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(pos), QPointF(pos),
                    button, button, mods)
    canvas.mousePressEvent(e)


def move(canvas, pos, button=Qt.LeftButton, mods=Qt.NoModifier):
    e = QMouseEvent(QMouseEvent.MouseMove, QPointF(pos), QPointF(pos),
                    Qt.NoButton, button, mods)
    canvas.mouseMoveEvent(e)


def release(canvas, pos, button=Qt.LeftButton, mods=Qt.NoModifier):
    e = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(pos), QPointF(pos),
                    button, Qt.NoButton, mods)
    canvas.mouseReleaseEvent(e)


def drag(canvas, start, delta, button=Qt.LeftButton):
    press(canvas, start, button)
    move(canvas, QPoint(start.x() + delta[0], start.y() + delta[1]), button)
    release(canvas, QPoint(start.x() + delta[0], start.y() + delta[1]), button)
    app.processEvents()


# ---------- 工具列表里有抓手 ----------
ids = [t[0] for t in TOOLS]
check("工具列表里有抓手工具", "pan" in ids, str(ids))
check("抓手有中文名与提示",
      any(t[0] == "pan" and t[1] == "抓手" and t[2] for t in TOOLS))

# ---------- 抓手工具：拖动改变滚动位置 ----------
win = make_win()
canvas = win.canvas
scroll = win.scroll
hbar, vbar = scroll.horizontalScrollBar(), scroll.verticalScrollBar()
check("放大后滚动条有可移动范围",
      hbar.maximum() > 0 and vbar.maximum() > 0,
      f"hmax={hbar.maximum()} vmax={vbar.maximum()} zoom={canvas.zoom}")

# 先滚到中间，否则从 0 往右拖没有可减的空间（滚动条已在最小）
hbar.setValue(hbar.maximum() // 2)
vbar.setValue(vbar.maximum() // 2)
app.processEvents()
h0, v0 = hbar.value(), vbar.value()
win.set_tool("pan")
check("抓手工具下画布是张开手光标",
      canvas.cursor().shape() == Qt.OpenHandCursor,
      str(canvas.cursor().shape()))

# 往右下拖 60px → 画面应该跟着走（滚动量减小）
drag(canvas, QPoint(200, 200), (60, 40))
check("抓手拖动改变了水平滚动", hbar.value() != h0,
      f"{h0} -> {hbar.value()}")
check("抓手拖动改变了垂直滚动", vbar.value() != v0,
      f"{v0} -> {vbar.value()}")

# 反向拖回来
h1, v1 = hbar.value(), vbar.value()
drag(canvas, QPoint(200, 200), (-60, -40))
check("反向拖动把滚动位置拖回来",
      hbar.value() > h1 and vbar.value() > v1,
      f"h {h1}->{hbar.value()}  v {v1}->{vbar.value()}")

# ---------- 任何工具下中键都能拖 ----------
win.set_tool("rect")
h2, v2 = hbar.value(), vbar.value()
drag(canvas, QPoint(200, 200), (50, 50), button=Qt.MiddleButton)
check("矩形工具下中键拖动也能平移",
      hbar.value() != h2 or vbar.value() != v2,
      f"{h2},{v2} -> {hbar.value()},{vbar.value()}")
check("中键拖动不会画出图形", len(canvas.shapes) == 0,
      str([type(s).__name__ for s in canvas.shapes]))

# ---------- 空格临时抓手 ----------
win.set_tool("rect")
canvas.setFocus()
ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)
canvas.keyPressEvent(ev)
check("按住空格进入临时抓手", canvas.can_pan() is True)
check("空格时是张开手光标",
      canvas.cursor().shape() == Qt.OpenHandCursor,
      str(canvas.cursor().shape()))
h3, v3 = hbar.value(), vbar.value()
drag(canvas, QPoint(200, 200), (40, 30))
check("空格 + 左键拖动可以平移",
      hbar.value() != h3 or vbar.value() != v3,
      f"{h3},{v3} -> {hbar.value()},{vbar.value()}")
check("空格拖动后没留下图形", len(canvas.shapes) == 0)
rel = QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier)
canvas.keyReleaseEvent(rel)
check("松开空格退出临时抓手", canvas.can_pan() is False)

# ---------- 普通工具的左键拖动仍然是画图 ----------
h4, v4 = hbar.value(), vbar.value()
drag(canvas, QPoint(120, 120), (40, 30))
check("非抓手工具左键拖动照旧画图", len(canvas.shapes) == 1,
      str([type(s).__name__ for s in canvas.shapes]))
check("画图时不会顺带平移", hbar.value() == h4 and vbar.value() == v4,
      f"{h4},{v4} -> {hbar.value()},{vbar.value()}")

# ---------- 抓手工具下不应画出图形 ----------
win.set_tool("pan")
before = len(canvas.shapes)
drag(canvas, QPoint(120, 120), (30, 30))
check("抓手工具下拖动不会画图", len(canvas.shapes) == before,
      f"{before} -> {len(canvas.shapes)}")

# ---------- 光标在拖动过程中是握拳 ----------
win.set_tool("pan")
press(canvas, QPoint(200, 200))
check("拖动中光标变握拳",
      canvas.cursor().shape() == Qt.ClosedHandCursor,
      str(canvas.cursor().shape()))
release(canvas, QPoint(200, 200))
check("松开后回到张开手",
      canvas.cursor().shape() == Qt.OpenHandCursor,
      str(canvas.cursor().shape()))

# ---------- 其他工具不显示手型光标 ----------
win.set_tool("pen")
check("画笔工具不是手型光标",
      canvas.cursor().shape() != Qt.OpenHandCursor,
      str(canvas.cursor().shape()))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("拖动查看测试通过 ✔")
