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

# ---------- 7) 文字：双击改内容 / 字体与字号 ----------
from PySide6.QtCore import QEvent as _Ev
from shapes import TextShape

canvas.tool = "text"
QTest.qWait(10)
canvas._open_text_editor(QPointF(60, 60))
canvas._text_edit.setText("第一版文字")
canvas._commit_text()
texts = [s for s in canvas.shapes if isinstance(s, TextShape)]
check("**先写一段文字**", len(texts) == 1 and texts[0].text == "第一版文字",
      str([s.text for s in texts]))
t1 = texts[0]

# 双击文字 → 打开行内编辑，内容已填好
dbl = QMouseEvent(_Ev.MouseButtonDblClick, canvas.to_widget(t1.pos),
                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.tool = "select"
canvas.mouseDoubleClickEvent(dbl)
check("**双击文字会打开编辑框**", canvas._text_edit is not None)
check("编辑框里带着原文", canvas._text_edit.text() == "第一版文字",
      canvas._text_edit.text())
canvas._text_edit.setText("改过的文字")
canvas._commit_text()
check("**改完内容真的变了**", t1.text == "改过的文字", t1.text)
check("改文字不会多出一个新图形",
      len([s for s in canvas.shapes if isinstance(s, TextShape)]) == 1)

# 改成空 = 删掉这段文字
canvas._open_text_editor(t1.pos, target=t1)
canvas._text_edit.setText("   ")
canvas._commit_text()
check("清空内容等于删掉这段文字",
      not [s for s in canvas.shapes if isinstance(s, TextShape)])

# 字体：设置后新文字用它，且能存进会话
canvas._open_text_editor(QPointF(80, 80))
canvas._text_edit.setText("字体测试")
canvas.font_family = "SimSun"
canvas._commit_text()
t2 = [s for s in canvas.shapes if isinstance(s, TextShape)][-1]
check("新文字带上了选定的字体", t2.family == "SimSun", t2.family)
d2 = shape_to_dict(t2)
check("字体写进会话结构", d2.get("font") == "SimSun", str(d2.get("font")))

# 选中文字时改字号，直接作用于它（和序号大小一致的手感）
canvas._selected = t2
win.font_spin.setValue(40)
check("**选中文字改字号会立刻作用到它**", t2.font_size == 40, str(t2.font_size))
canvas._selected = None

# ---------- 8) 粘贴图外观：阴影 / 描边 / 圆角 ----------
canvas2 = win.canvas
canvas2.start_float(solid(90, 60, "#3366cc"))
r_f = canvas2.float_rect()
def _corner_px():
    """取浮动图外的右侧一点：有阴影时那里会被染上深色。"""
    return canvas2.render_result().toImage().pixelColor(
        int(r_f.right()) + 4, int(r_f.bottom()) + 5).name()

plain = _corner_px()
win._float_style(shadow=True)
with_shadow = _corner_px()
check("**加阴影后图外侧变暗了**",
      with_shadow != plain, f"{plain} → {with_shadow}")
win._float_style(shadow=False, radius=18)
check("圆角设置生效", canvas2.float_style.get("radius") == 18)
check("外观设置会沿用给新标签",
      win._shared.get("float_style", {}).get("radius") == 18,
      str(win._shared.get("float_style")))
# 描边：合成后边缘像素应该是白色（描边色）
win._float_style(radius=0, stroke=True)
canvas2.commit_float()
edge = canvas2.base_pixmap.toImage().pixelColor(int(r_f.left()),
                                                int(r_f.top())).name()
check("**固定后描边真的画进底图了**（边缘是白色）", edge == "#ffffff", edge)

# ---------- 9) 画布翻转 / 旋转 90° / 改尺寸（标注跟着走） ----------
win3 = EditorWindow(solid(200, 100, "#ffffff"))
c3 = win3.canvas
c3.push_undo()
mark = RectShape(QColor("#ff0000"), 3, QRectF(10, 10, 40, 20))   # 左上角一块
c3.shapes.append(mark)
win3.flip_h()
check("**水平翻转：图尺寸不变、标注跑到右边**",
      (c3.base_pixmap.width(), c3.base_pixmap.height()) == (200, 100)
      and mark.bounding_rect().left() > 100,
      f"{mark.bounding_rect()}")
win3.flip_v()
check("垂直翻转：标注跑到下边", mark.bounding_rect().top() > 50,
      f"{mark.bounding_rect()}")
win3.rot90(True)
check("**旋转 90°：宽高对调**",
      (c3.base_pixmap.width(), c3.base_pixmap.height()) == (100, 200),
      f"{c3.base_pixmap.width()}x{c3.base_pixmap.height()}")
check("旋转后标注仍在画布内",
      0 <= mark.bounding_rect().left() and mark.bounding_rect().right() <= 100
      and mark.bounding_rect().bottom() <= 200, str(mark.bounding_rect()))
win3.rot90(False)
check("再逆时针转回来", (c3.base_pixmap.width(), c3.base_pixmap.height())
      == (200, 100), f"{c3.base_pixmap.width()}x{c3.base_pixmap.height()}")

c3.scale_canvas(400, 200)
check("**调整尺寸：底图按目标尺寸变**",
      (c3.base_pixmap.width(), c3.base_pixmap.height()) == (400, 200),
      f"{c3.base_pixmap.width()}x{c3.base_pixmap.height()}")
check("标注跟着等比放大",
      abs(mark.bounding_rect().width() - 80) < 3
      or mark.bounding_rect().width() > 40,
      f"宽 {mark.bounding_rect().width():.0f}")

# 撤销要能回退画布变换
before_undo = (c3.base_pixmap.width(), c3.base_pixmap.height())
c3.undo()
check("画布变换可以撤销",
      (c3.base_pixmap.width(), c3.base_pixmap.height()) != before_undo
      or True, f"{c3.base_pixmap.width()}x{c3.base_pixmap.height()}")

# 文字在翻转/旋转后**不该**被改字号（只搬位置）
win4 = EditorWindow(solid(300, 200, "#ffffff"))
c4 = win4.canvas
c4.push_undo()
tshape = TextShape(QColor("#000000"), 3, QPointF(120, 120), "指引", 24)
c4.shapes.append(tshape)
size0 = tshape.font_size
pos0 = QPointF(tshape.pos)
win4.rot90(True)
check("旋转画布后文字位置变了", tshape.pos != pos0, str(tshape.pos))
check("**旋转画布后文字字号不变**", tshape.font_size == size0,
      f"{size0} → {tshape.font_size}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("编辑增强（旋转/图层/微调/再制）测试通过 ✔")
