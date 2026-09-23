# -*- coding: utf-8 -*-
"""对话框按钮行为测试：取消/确定/Esc 必须真的生效。

起因：边框对话框的"取消"点了没反应。原因是 QDialogButtonBox() 没有传 parent，
Qt 只在 box 的父对象是 QDialog 时才自动把 rejected() 接到对话框的 reject()。
所以这里逐个对话框验证：
- 点「取消」→ 对话框被 Rejected，且**什么都不改**
- 点「应用」→ Accepted
- Esc → Rejected
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

app = QApplication([])

from border import BORDER_DEFAULTS, BorderDialog
from editor import EditorWindow
from watermark import DEFAULT_SETTINGS, WatermarkDialog

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def by_role(box, role):
    """按角色找按钮（自定义文本按钮不能用 box.button()，那个只认 StandardButton）。"""
    for b in box.buttons():
        if box.buttonRole(b) == role:
            return b
    return None


def dialogs():
    win = EditorWindow(QPixmap(300, 200))
    size = win.canvas.base_pixmap.size()
    return [
        ("边框", BorderDialog(None, BORDER_DEFAULTS, size)),
        ("水印", WatermarkDialog(None, DEFAULT_SETTINGS, size)),
    ]


# ---------- 每个对话框：取消 / Esc / 应用 ----------
for label, dlg in dialogs():
    box = dlg.findChild(QDialogButtonBox)
    check(f"{label}对话框有按钮组", box is not None)
    check(f"{label}按钮组有父对象（否则取消无效）", box.parent() is not None,
          repr(box.parent()))
    cancel = by_role(box, QDialogButtonBox.RejectRole)
    check(f"{label}按钮组里有 RejectRole 按钮（取消）", cancel is not None)

    # 点取消 → Rejected
    dlg.show()
    app.processEvents()
    cancel.click()
    app.processEvents()
    check(f"{label}：点「取消」对话框被拒绝",
          dlg.result() == QDialog.Rejected, f"result={dlg.result()}")
    dlg.deleteLater()

for label, dlg in dialogs():
    # Esc → Rejected
    dlg.show()
    app.processEvents()
    QTest.keyClick(dlg, Qt.Key_Escape)
    app.processEvents()
    check(f"{label}：Esc 关闭对话框", dlg.result() == QDialog.Rejected,
          f"result={dlg.result()}")
    dlg.deleteLater()

for label, dlg in dialogs():
    box = dlg.findChild(QDialogButtonBox)
    accept = by_role(box, QDialogButtonBox.AcceptRole)
    dlg.show()
    app.processEvents()
    accept.click()
    app.processEvents()
    check(f"{label}：点「应用」对话框被接受",
          dlg.result() == QDialog.Accepted, f"result={dlg.result()}")
    check(f"{label}：接受后 save_as_default 为假（应用≠设为默认）",
          dlg.save_as_default() is False)
    dlg.deleteLater()

# ---------- 端到端：取消后编辑器不许有任何改动 ----------
_orig_exec = QDialog.exec


def cancel_exec(self):
    """把模态 exec 换成"点一下取消"。"""
    box = self.findChild(QDialogButtonBox)
    by_role(box, QDialogButtonBox.RejectRole).click()
    return QDialog.Rejected


QDialog.exec = cancel_exec
try:
    win = EditorWindow(QPixmap(300, 200))
    before = (win.canvas.base_pixmap.width(), win.canvas.base_pixmap.height(),
              len(win.canvas.shapes))
    win.add_border()
    after = (win.canvas.base_pixmap.width(), win.canvas.base_pixmap.height(),
             len(win.canvas.shapes))
    check("编辑器：边框对话框取消后图片尺寸不变", before[0] == after[0]
          and before[1] == after[1], f"{before} -> {after}")
    win.add_watermark()
    check("编辑器：水印对话框取消后不加图形",
          len(win.canvas.shapes) == before[2], str(len(win.canvas.shapes)))
    check("编辑器：取消后撤销栈也没变（没有多余的历史）",
          len(win.canvas._undo_stack) == 0, str(len(win.canvas._undo_stack)))
finally:
    QDialog.exec = _orig_exec

# ---------- 端到端：应用确实生效（对照组）----------
QDialog.exec = lambda self: QDialog.Accepted
try:
    win2 = EditorWindow(QPixmap(300, 200))
    w0 = win2.canvas.base_pixmap.width()
    win2.add_border()
    check("编辑器：对话框确定后边框生效",
          win2.canvas.base_pixmap.width() > w0,
          f"{w0} -> {win2.canvas.base_pixmap.width()}")
    win2.add_watermark()
    check("编辑器：对话框确定后水印加上",
          any(type(s).__name__ == "WatermarkShape" for s in win2.canvas.shapes))
finally:
    QDialog.exec = _orig_exec

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("对话框按钮行为测试通过 ✔")
