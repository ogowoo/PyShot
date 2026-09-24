# -*- coding: utf-8 -*-
"""浮动粘贴：把剪贴板里的新截图贴到**当前这张图**上，摆好位置再固定。

用户要的场景：做操作指引时，把第二张截图贴到第一张上拼成一张。
约定（本文件锁住）：
  · Ctrl+V / 编辑菜单 → 贴到当前图，**不新开标签**（新标签是 Ctrl+Shift+V）
  · 贴上去是"浮层"：可拖动摆位置、Ctrl+滚轮缩放
  · Enter 或双击 → 固定进图（可 Ctrl+Z 撤销）；Esc → 丢弃
  · 没固定之前导出（复制/保存/贴图）也要包含它 —— 看到什么就存什么
  · 没有打开的图时退回"新标签"，别让用户以为没反应
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

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_paste_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap, QWheelEvent
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


def set_clip(pix: QPixmap | None):
    cb = QApplication.clipboard()
    if pix is None:
        cb.clear()
    else:
        cb.setPixmap(pix)


def color_at(pix: QPixmap, x: int, y: int) -> str:
    return pix.toImage().pixelColor(int(x), int(y)).name()


# ---------- 1) 有图时：Ctrl+V 贴到当前图，不新开标签 ----------
win = EditorWindow(solid(400, 300, "#ffffff"))
canvas = win.canvas
set_clip(solid(100, 60, "#ff0000"))
before_tabs = win.tabs.count()
win.paste_onto_current()
check("**贴到当前图而不是新开标签**", win.tabs.count() == before_tabs,
      f"{before_tabs} → {win.tabs.count()}")
check("画布上出现了浮动层", canvas.has_float())
check("浮动层默认放在可见区域内（不越界）",
      canvas.float_rect().left() >= 0 and canvas.float_rect().top() >= 0
      and canvas.float_rect().right() <= canvas.base_pixmap.width() + 1,
      str(canvas.float_rect()))
check("菜单项「固定粘贴的图」此时可用", win.act_paste_ok.isEnabled())

# ---------- 2) 拖动摆位置 ----------
r0 = canvas.float_rect()
start = canvas.mapTo(canvas.parent() or win, r0.center().toPoint()) \
    if False else None
# 直接用画布坐标做事件（Canvas 的坐标就是图像坐标 × zoom/dpr）
pos = canvas.to_widget(r0.center())
press = QMouseEvent(QEvent.MouseButtonPress, pos, Qt.LeftButton,
                    Qt.LeftButton, Qt.NoModifier)
canvas.mousePressEvent(press)
move = QMouseEvent(QEvent.MouseMove, pos + QPointF(25, 15), Qt.NoButton,
                   Qt.LeftButton, Qt.NoModifier)
canvas.mouseMoveEvent(move)
release = QMouseEvent(QEvent.MouseButtonRelease, pos + QPointF(25, 15),
                      Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
canvas.mouseReleaseEvent(release)
r1 = canvas.float_rect()
check("拖动可以移动浮动图",
      abs(r1.left() - r0.left() - 25) < 2 and abs(r1.top() - r0.top() - 15) < 2,
      f"{r0.left():.0f},{r0.top():.0f} → {r1.left():.0f},{r1.top():.0f}")

# ---------- 3) Ctrl+滚轮缩放浮动图（中心不动） ----------
c0 = canvas.float_rect().center()
s0 = canvas.float_scale()
canvas.scale_float(1.15)
check("缩放生效", abs(canvas.float_scale() - s0 * 1.15) < 1e-6,
      f"{s0:.2f} → {canvas.float_scale():.2f}")
check("缩放以中心为锚点（不会越缩越跑）",
      abs(canvas.float_rect().center().x() - c0.x()) < 0.5
      and abs(canvas.float_rect().center().y() - c0.y()) < 0.5,
      str(canvas.float_rect().center()))

# ---------- 3b) 拖角手柄改大小（Shift 等比） ----------
check("浮动图有 8 个缩放手柄 + 1 个旋转手柄",
      len(canvas.float_handles()) == 9, str(len(canvas.float_handles())))
r_before = canvas.float_rect()
h_corner = canvas.float_handles()[4]          # 右下
canvas.resize_float_by_handle(4, h_corner + QPointF(40, 0))
r_after = canvas.float_rect()
check("**拖右手柄能把图拉宽**",
      r_after.width() > r_before.width() + 30
      and abs(r_after.left() - r_before.left()) < 0.5,
      f"{r_before.width():.0f} → {r_after.width():.0f}")
canvas.resize_float_by_handle(4, canvas.float_rect().bottomRight()
                              - QPointF(0, 20))
check("拖下边也能改高", canvas.float_rect().height() < r_after.height())

# Shift 等比：拉宽时高度按原比例变
canvas._float_rect_obj = QRectF(50, 50, 200, 100)   # 已知 2:1
canvas._float_aspect = 2.0
canvas.resize_float_by_handle(4, QPointF(350, 150), keep_aspect=True)
rr = canvas.float_rect()
check("Shift 拖角保持宽高比（2:1）",
      abs(rr.width() / max(1.0, rr.height()) - 2.0) < 0.05,
      f"{rr.width():.0f}x{rr.height():.0f}")
check("拖得太小会被挡下（不会缩成一条线）",
      canvas.resize_float_by_handle(4, canvas.float_rect().topLeft()
                                    + QPointF(2, 2)) is False
      or canvas.float_rect().width() >= 8,
      str(canvas.float_rect()))

# ---------- 4) 没固定之前导出也要包含它 ----------
out = canvas.render_result()
r = canvas.float_rect()
check("导出结果包含还没固定的浮层（看到什么就存什么）",
      color_at(out, r.center().x(), r.center().y()) == "#ff0000",
      color_at(out, r.center().x(), r.center().y()))

# ---------- 5) Enter 固定进图（可撤销） ----------
base_before = QPixmap(canvas.base_pixmap)
kev = QTest.keyClick(canvas, Qt.Key_Return)
check("Enter 之后浮动层消失", not canvas.has_float())
fixed_at = color_at(canvas.base_pixmap, r.center().x(), r.center().y())
check("**粘贴的内容真的合成进底图了**", fixed_at == "#ff0000", fixed_at)
check("固定后「固定粘贴的图」置灰", not win.act_paste_ok.isEnabled())

win.act_m_undo.trigger()
check("Ctrl+Z 能撤销这次粘贴（底图恢复）",
      color_at(canvas.base_pixmap, r.center().x(), r.center().y()) != "#ff0000",
      color_at(canvas.base_pixmap, r.center().x(), r.center().y()))
win.act_m_redo.trigger()
check("重做能把粘贴找回来",
      color_at(canvas.base_pixmap, r.center().x(), r.center().y()) == "#ff0000")

# ---------- 6) Esc 丢掉浮层，底图不动 ----------
set_clip(solid(80, 80, "#0000ff"))
win.paste_onto_current()
check("再次粘贴又是浮动层", canvas.has_float())
base_snapshot = QPixmap(canvas.base_pixmap)
# 关键：有浮层时 Esc 只能取消粘贴，不能走到"空闲 Esc → 关窗口"那条路
idle, closed = [], []
canvas.escape_idle.connect(lambda: idle.append(1))
win.closing.connect(lambda: closed.append(1))
QTest.keyClick(canvas, Qt.Key_Escape)
check("Esc 之后浮动层消失", not canvas.has_float())
check("Esc 不会改动底图", base_snapshot.toImage() == canvas.base_pixmap.toImage())
check("**有浮层时 Esc 只取消粘贴**（不会发 escape_idle 把编辑器关掉）",
      not idle and not closed, f"idle={idle} closed={closed}")

# ---------- 7) 双击 = 固定 ----------
set_clip(solid(80, 80, "#00aa00"))
win.paste_onto_current()
rc = canvas.float_rect().center()
dbl = QMouseEvent(QEvent.MouseButtonDblClick, canvas.to_widget(rc),
                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.mouseDoubleClickEvent(dbl)
check("双击也能固定", not canvas.has_float()
      and color_at(canvas.base_pixmap, rc.x(), rc.y()) == "#00aa00",
      color_at(canvas.base_pixmap, rc.x(), rc.y()))

# ---------- 8) 没有图片时 Ctrl+V → 新标签（不能没反应） ----------
empty = EditorWindow()
check("空编辑器没有标签", empty.tabs.count() == 0)
set_clip(solid(50, 40, "#123456"))
empty.paste_onto_current()
check("**空编辑器里粘贴会开一个新标签**", empty.tabs.count() == 1,
      str(empty.tabs.count()))
check("新标签的底图就是剪贴板内容",
      color_at(empty.canvas.base_pixmap, 10, 10) == "#123456")

# ---------- 9) 剪贴板没有图片：给提示，不崩 ----------
empty2 = EditorWindow(solid(200, 200, "#ffffff"))
set_clip(None)
empty2.paste_onto_current()
check("剪贴板为空时不产生浮动层", not empty2.canvas.has_float())
check("剪贴板为空时给状态栏提示",
      "剪贴板" in empty2.statusBar().currentMessage(),
      empty2.statusBar().currentMessage())

# ---------- 10) 连按两次粘贴：前一个先固定，别被覆盖丢掉 ----------
win2 = EditorWindow(solid(400, 300, "#ffffff"))
set_clip(solid(60, 40, "#ff00ff"))
win2.paste_onto_current()
r_first = win2.canvas.float_rect()
set_clip(solid(60, 40, "#00ffff"))
win2.paste_onto_current()
check("第二次粘贴时，第一个浮动图已被固定进图",
      color_at(win2.canvas.base_pixmap, r_first.center().x(),
               r_first.center().y()) == "#ff00ff",
      color_at(win2.canvas.base_pixmap, r_first.center().x(),
               r_first.center().y()))
check("第二次粘贴仍然是浮动层（等着摆位置）", win2.canvas.has_float())

# ---------- 11) 旋转手柄：**走真实鼠标事件**（之前拖不动就是这里） ----------
win3 = EditorWindow(solid(400, 300, "#ffffff"))
c3 = win3.canvas
c3.tool = "select"
set_clip(solid(120, 80, "#e91e63"))
win3.paste_onto_current()
r3 = c3.float_rect()


def drag_canvas(canvas, from_img, to_img, modifiers=Qt.NoModifier):
    """在画布上模拟一次"按下-移动-松开"（坐标是图像像素）。"""
    p0 = canvas.to_widget(from_img)
    p1 = canvas.to_widget(to_img)
    canvas.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, p0,
                                       Qt.LeftButton, Qt.LeftButton, modifiers))
    canvas.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, p1, Qt.NoButton,
                                      Qt.LeftButton, modifiers))
    canvas.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, p1,
                                         Qt.LeftButton, Qt.NoButton, modifiers))


rot_handle = c3.float_handles()[8]
check("浮层旋转手柄画在上边外侧", rot_handle.y() < r3.top(), str(rot_handle))
# 把旋转手柄拖到"中心正右方" → 应该转 90°
drag_canvas(c3, rot_handle, QPointF(r3.center().x() + 150, r3.center().y()))
check("**拖浮层旋转手柄真的能转**（真实鼠标路径）",
      abs(c3._float_angle - 90.0) < 1.0, f"{c3._float_angle:.1f}°")
# 转了 90° 之后，旋转手柄应该从"上边外侧"跑到"右边外侧"
_h8 = c3.float_handles()[8]
_c = c3.float_rect().center()
check("旋转后旋转手柄跟着转到右边外侧",
      _h8.x() > _c.x() + 5 and abs(_h8.y() - _c.y()) < 5,
      f"手柄 {_h8} / 中心 {_c}")

# 转过之后：还能拖动、还能点中（命中要按旋转后的位置算）
before = QPointF(c3.float_rect().topLeft())
drag_canvas(c3, c3.float_rect().center(),
            c3.float_rect().center() + QPointF(30, 4))
check("旋转后仍然能拖动", c3.float_rect().topLeft() != before,
      f"{before} → {c3.float_rect().topLeft()}")
check("旋转后点击应按旋转后的范围命中",
      c3.float_rect().contains(c3.float_local(c3.float_rect().center())))

# 渲染结果也要是转过的（颜色块的角度变了：看包围盒以外的点）
out_rot = c3.render_result()
px_center = out_rot.toImage().pixelColor(int(c3.float_rect().center().x()),
                                         int(c3.float_rect().center().y())).name()
check("旋转后的浮层仍然画在中心（内容没跑掉）", px_center == "#e91e63", px_center)

# 固定后转过的角度要进底图
c3.commit_float()
check("旋转后固定：底图中心还是这个颜色",
      color_at(c3.base_pixmap, int(r3.center().x()), int(r3.center().y()))
      == "#e91e63")

# 图形的旋转手柄也走一遍真实鼠标路径（之前只做了单元级验证）
win4 = EditorWindow(solid(400, 300, "#ffffff"))
c4 = win4.canvas
c4.tool = "select"
c4.push_undo()
rect4 = RectShape(QColor("#2196f3"), 3, QRectF(150, 150, 100, 60))
c4.shapes.append(rect4)
c4._selected = rect4
h8 = rect4.rotated_handles()[8]
c4c = rect4.bounding_rect().center()
drag_canvas(c4, h8, QPointF(c4c.x() + 120, c4c.y()))
check("**拖图形旋转手柄也能转**（真实鼠标路径）",
      abs(rect4.rotation - 90.0) < 1.0, f"{rect4.rotation:.1f}°")


# ---------- 12) 虚线框要跟着一起转（用户报过"框不动"） ----------
def blue_hits(img, p0, p1, n=80):
    """沿一条线数"高亮蓝"像素：虚线框画到的地方才有点。"""
    hits = 0
    for i in range(n + 1):
        t = i / n
        x = int(round(p0.x() + (p1.x() - p0.x()) * t))
        y = int(round(p0.y() + (p1.y() - p0.y()) * t))
        c = img.pixelColor(max(0, min(img.width() - 1, x)),
                           max(0, min(img.height() - 1, y)))
        if c.blue() > 170 and c.red() < 170 and (c.blue() - c.green()) > 30:
            hits += 1
    return hits


def frame_follows_rotation(canvas, corners, rect, tag):
    """断言：框画在"旋转后的四角"上，而不是轴对齐的矩形上。"""
    img = canvas.grab().toImage()
    rotated = (corners[0], corners[1])
    aligned = (QPointF(rect.left(), rect.top()),
               QPointF(rect.right(), rect.top()))
    n_rot = blue_hits(img, *rotated)
    n_axis = blue_hits(img, *aligned)
    check(f"**{tag}：虚线框画在旋转后的边上**（未旋转的那条边应该基本没有框）",
          n_rot >= 12 and n_axis <= 8, f"旋转边 {n_rot} 点 / 未旋转边 {n_axis} 点")


win5 = EditorWindow(solid(420, 320, "#ffffff"))
c5 = win5.canvas
c5.tool = "select"
set_clip(solid(130, 90, "#bbbbbb"))          # 浅色内容，蓝色框才认得出
win5.paste_onto_current()
r5 = c5.float_rect()
drag_canvas(c5, c5.float_handles()[8],
            QPointF(r5.center().x() + 120, r5.center().y() - 40))
check("浮层已转过一个角度",
      abs(c5._float_angle) > 20, f"{c5._float_angle:.1f}°")
frame_follows_rotation(c5, c5.float_corners(), r5, "浮层")

win6 = EditorWindow(solid(420, 320, "#ffffff"))
c6 = win6.canvas
c6.tool = "select"
c6.push_undo()
rect6 = RectShape(QColor("#888888"), 3, QRectF(120, 110, 160, 100))
c6.shapes.append(rect6)
c6._selected = rect6
rect6.rotation = 32.0
frame_follows_rotation(c6, rect6.rotated_corners(), rect6.bounding_rect(), "图形")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("浮动粘贴测试通过 ✔")
