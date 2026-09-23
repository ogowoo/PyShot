# -*- coding: utf-8 -*-
"""快捷键测试：Ctrl+Z / Ctrl+Y 等必须真的生效（并且不能有重复绑定）。

背景：加编辑器菜单栏时，菜单项设了 Ctrl+Z / Ctrl+Y / Ctrl+S / Ctrl+C / Ctrl+W，
而 _build_shortcuts 里早就注册过同样的序列 —— 同一个窗口里两个动作抢同一个
按键，Qt 判为"歧义"后**两个都不触发**，于是 Ctrl+Z 直接失效。
所以这里两头都测：
1) 全窗口的快捷键**不允许重复**（从机制上杜绝这类问题）
2) 真的按下去，撤销/重做/保存/复制要生效
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeySequence, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import EditorWindow
from shapes import RectShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def make_win():
    pix = QPixmap(300, 200)
    pix.fill(QColor("#ddeeff"))
    win = EditorWindow(pix)
    win.resize(700, 500)
    win.show()
    app.processEvents()
    return win


def all_sequences(win):
    """收集窗口里所有快捷键（QAction + QShortcut），返回 {序列: [来源]}。"""
    seen = {}
    for a in win.findChildren(type(win.act_undo)):
        for seq in a.shortcuts():
            s = seq.toString()
            if s:
                seen.setdefault(s, []).append(a.text() or "（菜单项/内部动作）")
    for sc in win.findChildren(QShortcut):
        s = sc.key().toString()
        if s:
            seen.setdefault(s, []).append("QShortcut")
    return seen


win = make_win()

# ---------- 1) 不允许重复绑定 ----------
seqs = all_sequences(win)
dups = {s: src for s, src in seqs.items() if len(src) > 1}
if dups:
    for s, src in sorted(dups.items()):
        print(f"   重复：{s} -> {src}")
check("编辑器里没有重复的快捷键绑定", not dups, f"{len(dups)} 个重复")

for need in ("Ctrl+Z", "Ctrl+Y", "Ctrl+S", "Ctrl+C", "Ctrl+W", "Ctrl+O"):
    check(f"{need} 有且仅有一处绑定", len(seqs.get(need, [])) == 1,
          str(seqs.get(need)))

# ---------- 2) 真的按下去要生效 ----------
canvas = win.canvas
canvas.shapes.append(RectShape(QColor("#e53935"), 4, QRectF(20, 20, 80, 60)))
canvas.push_undo()
canvas.shapes.append(RectShape(QColor("#43a047"), 4, QRectF(120, 20, 80, 60)))
app.processEvents()
check("先造出 2 个图形", len(canvas.shapes) == 2, str(len(canvas.shapes)))

win.activateWindow()
canvas.setFocus()
app.processEvents()

QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
app.processEvents()
check("按 Ctrl+Z 能撤销", len(canvas.shapes) == 1, str(len(canvas.shapes)))

QTest.keyClick(win, Qt.Key_Y, Qt.ControlModifier)
app.processEvents()
check("按 Ctrl+Y 能重做", len(canvas.shapes) == 2, str(len(canvas.shapes)))

# Ctrl+Shift+Z 是**重做**的备选键（和 Ctrl+Y 同一个动作）
QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier)
app.processEvents()
check("先撤销到一个图形", len(canvas.shapes) == 1, str(len(canvas.shapes)))
QTest.keyClick(win, Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
app.processEvents()
check("按 Ctrl+Shift+Z 能重做（菜单之外的备选键）",
      len(canvas.shapes) == 2, str(len(canvas.shapes)))

# 复制到剪贴板
QTest.keyClick(win, Qt.Key_C, Qt.ControlModifier)
app.processEvents()
check("按 Ctrl+C 有反应（剪贴板拿到图）",
      QApplication.clipboard().pixmap().width() > 0,
      str(QApplication.clipboard().pixmap().size()))

# 关闭标签
before = win.tabs.count()
QTest.keyClick(win, Qt.Key_W, Qt.ControlModifier)
app.processEvents()
check("按 Ctrl+W 能关闭标签", win.tabs.count() == before - 1,
      f"{before} -> {win.tabs.count()}")

# ---------- 3) 工具字母键仍然可用 ----------
win2 = make_win()
win2.activateWindow()
win2.canvas.setFocus()
app.processEvents()
QTest.keyClick(win2, Qt.Key_R)
app.processEvents()
check("按 R 切到矩形工具", win2.canvas.tool == "rect", win2.canvas.tool)
QTest.keyClick(win2, Qt.Key_V)
app.processEvents()
check("按 V 切回选择工具", win2.canvas.tool == "select", win2.canvas.tool)

# ---------- 4) 没有画布时，快捷键不应报错 ----------
win3 = EditorWindow()
win3.show()
app.processEvents()
for key in (Qt.Key_Z, Qt.Key_Y, Qt.Key_C, Qt.Key_W):
    QTest.keyClick(win3, key, Qt.ControlModifier)
    app.processEvents()
check("空白编辑器按这些键也不出错", win3.tabs.count() == 0)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("快捷键测试通过 ✔")
