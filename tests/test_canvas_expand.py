# -*- coding: utf-8 -*-
"""扩展画布边缘（特效 → 扩展画布边缘…）。

用户的需求："对截到的图片的边缘进行加大，方便把另一个图放一起编辑" ——
先扩出一块空白，再 Ctrl+V 把另一张截图贴上去。

实现：Canvas.expand_edges(left, top, right, bottom, color)
  · 新画布 = 原图 + 四边扩展，原图内容逐像素不动
  · 标注跟着偏移（只在扩了左/上时）
  · 有浮动层先固定（坐标系变了浮动层对不上）
  · 一步 Ctrl+Z 撤销
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_expand_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QDialog

app = QApplication([])

import style

style.apply_theme(app)

import editor as ed_mod
from editor import EditorWindow, ExpandEdgesDialog
from shapes import RectShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def solid(w, h, color="#102030") -> QPixmap:
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


def px(canvas, x, y) -> str:
    return canvas.base_pixmap.toImage().pixelColor(x, y).name()


# ---------- 1) 向右/下扩展：尺寸对、原内容不动、新区是填充色 ----------
win = EditorWindow(solid(100, 80))
canvas = win.canvas
check("向右 100 + 向下 80 → 200×160",
      canvas.expand_edges(right=100, bottom=80, color="#ffffff")
      and canvas.base_pixmap.width() == 200 and canvas.base_pixmap.height() == 160)
check("原图内容逐像素不动", px(canvas, 50, 40) == "#102030", px(canvas, 50, 40))
check("新扩出的区域是填充色",
      px(canvas, 150, 40) == "#ffffff" and px(canvas, 50, 120) == "#ffffff")

# ---------- 2) 撤销是一步 ----------
canvas.undo()
check("Ctrl+Z 一步退回 100×80",
      canvas.base_pixmap.width() == 100 and canvas.base_pixmap.height() == 80)

# ---------- 3) 向左/上扩展：标注跟着偏移 ----------
canvas2 = EditorWindow(solid(100, 80)).canvas
rect = RectShape(QColor("#ff0000"), 3, QRectF(10, 10, 20, 20))
canvas2.shapes.append(rect)
canvas2.expand_edges(left=30, top=20, color="#eeeeee")
check("左上扩展后尺寸 130×100",
      canvas2.base_pixmap.width() == 130 and canvas2.base_pixmap.height() == 100)
check("**标注跟着偏移 (10,10) → (40,30)**",
      rect.rect.topLeft() == QPointF(40, 30), str(rect.rect.topLeft()))
check("原图内容在新位置", px(canvas2, 30 + 50, 20 + 40) == "#102030")
canvas2.undo()
# 撤销恢复的是快照里的克隆体，不能拿旧引用比 —— 从画布里重新取
check("撤销后标注位置也回来",
      canvas2.shapes[0].rect.topLeft() == QPointF(10, 10),
      str(canvas2.shapes[0].rect.topLeft()))

# ---------- 4) 全 0 = 不动 ----------
canvas3 = EditorWindow(solid(60, 40)).canvas
check("四边都是 0 → 返回 False 且尺寸不变",
      canvas3.expand_edges() is False and canvas3.base_pixmap.width() == 60)

# ---------- 5) 有浮动层时先固定 ----------
canvas4 = EditorWindow(solid(80, 60)).canvas
canvas4.start_float(solid(20, 20, "#ff8800"))
check("开始时有浮动层", canvas4.has_float())
canvas4.expand_edges(right=40)
check("**扩展时浮动层被先固定**（不然坐标系变了它会对不上）",
      not canvas4.has_float())
# 浮动层是直接画进底图的（不是变成 shape）：验证它的像素还在
check("固定进底图的浮动层像素还在（居中位置）",
      px(canvas4, 40, 30) == "#ff8800", px(canvas4, 40, 30))

# ---------- 6) 对话框：预设、结果尺寸、values ----------
from PySide6.QtWidgets import QPushButton

dlg = ExpandEdgesDialog(win, 100, 80)
dlg.spin["right"].setValue(100)
check("结果尺寸实时更新", "200" in dlg.result.text(), dlg.result.text())
dlg2 = ExpandEdgesDialog(win, 100, 80)
preset = [b for b in dlg2.findChildren(QPushButton) if b.text() == "右侧留一张图宽"]
check("预设按钮存在", len(preset) == 1)
preset[0].click()
check("「右侧留一张图宽」→ right=100", dlg2.spin["right"].value() == 100)
v = dlg2.values()
check("values() 含四边与颜色",
      v == {"left": 0, "top": 0, "right": 100, "bottom": 0, "color": "#ffffff"},
      str(v))

# ---------- 7) 菜单入口 + 处理器真的调用了 expand_edges ----------
fx_items = [a.text() for a in win.menus["fx"].actions()]
check("特效菜单里有「扩展画布边缘…」", "扩展画布边缘…" in fx_items, str(fx_items))
check("它在「需要画布」清单里（空编辑器置灰）", win.act_expand in win._needs_canvas)


class FakeDlg:
    def __init__(self, parent, w, h):
        pass

    def exec(self):
        return QDialog.Accepted

    def values(self):
        return {"left": 0, "top": 0, "right": 50, "bottom": 0, "color": "#ffffff"}


orig = ed_mod.ExpandEdgesDialog
ed_mod.ExpandEdgesDialog = FakeDlg
try:
    win.expand_canvas_dialog()
finally:
    ed_mod.ExpandEdgesDialog = orig
check("**菜单处理器真的把画布扩了**", win.canvas.base_pixmap.width() == 150,
      f"{win.canvas.base_pixmap.width()}x{win.canvas.base_pixmap.height()}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("扩展画布边缘测试通过 ✔")
