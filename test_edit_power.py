# -*- coding: utf-8 -*-
"""更强大的编辑能力：旋转手柄 / 图层顺序 / 方向键微调 / 再制。

用户要的"编辑功能更强大"里这几条：
  · 拖图形上方的圆形手柄能任意角度旋转（编辑菜单还有 15°/摆正）
  · 图层顺序：置于顶层/底层、上移/下移一层（做指引叠图时很要紧）
  · 方向键微调 1px，Shift+方向键 10px
  · Ctrl+D 再制一个（错开 12px）
  · 画布右键菜单能直接调这些
  · 旋转角要能存进会话缓存（重启后还在）
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_edit_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import EditorWindow
from shapes import RectShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def solid(w, h, color) -> QPixmap:
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


win = EditorWindow(solid(400, 300, "#ffffff"))
canvas = win.canvas
canvas.tool = "select"

# ---------- 1) 旋转手柄（索引 8） ----------
canvas.push_undo()
r1 = RectShape(QColor("#e53935"), 3, QRectF(100, 100, 120, 80))
canvas.shapes.append(r1)
canvas._selected = r1
check("图形有 8 个缩放手柄 + 1 个旋转手柄",
      len(r1.rotated_handles()) == 9, str(len(r1.rotated_handles())))

# 把旋转手柄拖到中心正右方 → 应该转 90°
c = r1.bounding_rect().center()
r1.apply_rotation_and_resize(8, QPointF(c.x() + 200, c.y()))
check("**拖旋转手柄能转角度**", abs(r1.rotation - 90.0) < 0.5,
      f"{r1.rotation:.1f}°")

# 旋转后手柄也跟着转（外接框四角应偏离原始矩形）
corners = r1.rotated_corners()
check("旋转后手柄/选中框跟着转",
      abs(corners[0].x() - r1.bounding_rect().left()) > 1, str(corners[0]))

# 旋转后仍然能点中（命中判定在自身坐标里）
check("旋转后还能选中它",
      r1.contains(r1.world_to_local(c), 6.0), "中心点应在图形内")
check("旋转后点图形外面不会误选",
      not r1.contains(r1.world_to_local(QPointF(c.x() + 400, c.y())), 6.0))

# 菜单里的旋转 / 摆正
win.rotate_selected(15)
check("菜单旋转 15° 生效", abs(r1.rotation - 105.0) < 0.5, f"{r1.rotation:.1f}°")
win.rotate_selected(None)
check("摆正回到 0°", r1.rotation == 0.0, f"{r1.rotation}°")

# ---------- 2) 图层顺序 ----------
canvas.push_undo()
r2 = RectShape(QColor("#1e88e5"), 3, QRectF(150, 120, 120, 80))
canvas.shapes.append(r2)
order0 = [s.color.name() for s in canvas.shapes]
canvas._selected = r1                     # r1 在最下面
win._layer("front")
check("**置于顶层**", canvas.shapes[-1] is r1,
      f"{order0} → {[s.color.name() for s in canvas.shapes]}")
win._layer("back")
check("置于底层", canvas.shapes[0] is r1)
win._layer("up")
check("上移一层", canvas.shapes[1] is r1)
win._layer("down")
check("下移一层", canvas.shapes[0] is r1)

# ---------- 3) 方向键微调 ----------
x0 = r2.bounding_rect().left()
y0 = r2.bounding_rect().top()
canvas._selected = r2
QTest.keyClick(canvas, Qt.Key_Right)
check("方向键微调 1px",
      abs(r2.bounding_rect().left() - x0 - 1) < 0.01,
      f"{x0:.0f} → {r2.bounding_rect().left():.0f}")
QTest.keyClick(canvas, Qt.Key_Down, Qt.ShiftModifier)
check("Shift+方向键微调 10px",
      abs(r2.bounding_rect().top() - y0 - 10) < 0.01,
      f"{y0:.0f} → {r2.bounding_rect().top():.0f}")

# ---------- 4) 再制 ----------
n_before = len(canvas.shapes)
win.duplicate_selected()
check("**Ctrl+D 再制一个**", len(canvas.shapes) == n_before + 1,
      f"{n_before} → {len(canvas.shapes)}")
dup = canvas.shapes[-1]
check("再制的图形错开了一点",
      dup.bounding_rect().topLeft() != r2.bounding_rect().topLeft())
check("再制后选中的是新图形", canvas._selected is dup)

# ---------- 5) 右键菜单动作分发 ----------
canvas.context_action.emit("rot15")
check("右键菜单的旋转也生效", abs(canvas._selected.rotation - 15.0) < 0.5,
      f"{canvas._selected.rotation}°")
canvas.context_action.emit("rot0")
check("右键菜单的摆正也生效", canvas._selected.rotation == 0.0)

# ---------- 6) 旋转角存进会话 ----------
from session import load_session, save_session, shape_to_dict

d = shape_to_dict(r1)
r1.rotation = 42.0
d = shape_to_dict(r1)
check("旋转角写进了会话结构", d.get("rot") == 42.0, str(d.get("rot")))
save_session([{"title": "t", "zoom": 1.0, "pixmap": canvas.base_pixmap,
               "shapes": canvas.shapes}])
tabs = load_session()
rots = [getattr(s, "rotation", 0.0) for s in tabs[0]["shapes"]]
check("**重启后旋转角还在**", any(abs(r - 42.0) < 0.01 for r in rots), str(rots))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("编辑增强（旋转/图层/微调/再制）测试通过 ✔")
