# -*- coding: utf-8 -*-
"""序号（步骤）自动重排：删掉中间/尾部序号后自动补上，再标自动续号。

用户的需求：
  · 1,2,3,4,5,6 删掉 4 → 自动变成 1,2,3,4,5
  · 删掉 6 之后再标 → 新序号是 6（自动续上）
  · 顺带：Ctrl+D 再制序号时不能再克隆原编号（否则出现两个"3"）

关键实现点（editor.py / Canvas）：
  · next_step_number() = 现有最大编号 + 1（没有就是 1）
  · renumber_steps()   = 按现有编号顺序压成 1..n，并同步 step_counter
  · 三条删除路径（Delete 键、右键删除）在删掉序号后调用 renumber_steps()
  · 删除前已 push_undo()，所以"删除 + 重排"是同一步撤销
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_step_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import style

style.apply_theme(app)

from editor import EditorWindow
from shapes import RectShape, StepShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def solid(w, h, color="#ffffff") -> QPixmap:
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


win = EditorWindow(solid(400, 300))
canvas = win.canvas
canvas.setFocus()


def click_step(x, y):
    """用真实鼠标路径放一个序号（走 mousePressEvent，不是绕过它直接 append）。"""
    canvas.tool = "step"
    ev = QMouseEvent(QEvent.Type.MouseButtonPress,
                     canvas.to_widget(QPointF(x, y)),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    canvas.mousePressEvent(ev)


def press_delete():
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Delete, Qt.NoModifier)
    canvas.keyPressEvent(ev)


def step_numbers() -> list:
    return [s.number for s in canvas.shapes if isinstance(s, StepShape)]


def step_with_number(n):
    return next(s for s in canvas.shapes
                if isinstance(s, StepShape) and s.number == n)


# ---------- 1) 连续放置：1..6 ----------
for i, x in enumerate((40, 90, 140, 190, 240, 290), 1):
    click_step(x, 40)
check("连放 6 个序号是 1..6", step_numbers() == [1, 2, 3, 4, 5, 6],
      str(step_numbers()))
check("计数器同步到 7", canvas.step_counter == 7, str(canvas.step_counter))

# ---------- 2) 删掉中间的 4 → 5,6 自动变 4,5 ----------
canvas._selected = step_with_number(4)
press_delete()
check("**删掉 4 之后重排成 1..5**", step_numbers() == [1, 2, 3, 4, 5],
      str(step_numbers()))
check("重排后计数器 = 6（下一个就是 6）", canvas.step_counter == 6,
      str(canvas.step_counter))

# ---------- 3) 撤销：回到 1..6 ----------
canvas.undo()
check("撤销删除后回到 1..6", step_numbers() == [1, 2, 3, 4, 5, 6],
      str(step_numbers()))
check("撤销后计数器也回到 7", canvas.step_counter == 7, str(canvas.step_counter))

# ---------- 4) 删掉尾部的 6 → 再标自动续上（还是 6） ----------
canvas._selected = step_with_number(6)
canvas._emit_ctx("del")          # 走右键删除路径（另一处删除入口）
check("右键删掉 6 之后剩 1..5", step_numbers() == [1, 2, 3, 4, 5],
      str(step_numbers()))
click_step(320, 60)
check("**删掉尾部后再标，自动续上 6**", step_numbers() == [1, 2, 3, 4, 5, 6],
      str(step_numbers()))

# ---------- 5) 再制序号：发新号，不能克隆原编号 ----------
canvas._selected = step_with_number(2)
win.duplicate_selected()
nums = step_numbers()
check("再制序号后编号没有重复", len(nums) == len(set(nums)), str(nums))
check("再制出来的序号是当前最大号 + 1", max(nums) == 7, str(nums))
check("再制后一共 7 个序号", len(nums) == 7, str(nums))

# ---------- 6) 删除非序号图形不影响编号 ----------
canvas.tool = "rect"
r = RectShape(QColor("#ff0000"), 3, QRectF(10, 100, 70, 60))
canvas.shapes.append(r)
before = step_numbers()
canvas._selected = r
press_delete()
check("删掉矩形后序号编号不变", step_numbers() == before, str(step_numbers()))

# ---------- 7) 连删两个：依然连续 ----------
canvas._selected = step_with_number(3)
press_delete()
canvas._selected = step_with_number(5)
press_delete()
check("连删 3 和 5 后仍是连续的 1..5", step_numbers() == [1, 2, 3, 4, 5],
      str(step_numbers()))

# ---------- 8) 会话序列化保留重排后的编号 ----------
import session as sess

data = [sess.shape_to_dict(s) for s in canvas.shapes]
restored = [sess.shape_from_dict(d) for d in data]
nums2 = [s.number for s in restored if isinstance(s, StepShape)]
check("序列化/反序列化后编号不变", nums2 == step_numbers(), str(nums2))

# ---------- 9) 空画布：下一个序号是 1 ----------
for s in list(canvas.shapes):
    canvas._selected = s
    press_delete()
check("全删光后画布为空", canvas.shapes == [])
check("**全删光后下一个序号从 1 开始**", canvas.next_step_number() == 1,
      str(canvas.next_step_number()))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("序号自动重排测试通过 ✔")
