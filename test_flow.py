# -*- coding: utf-8 -*-
"""真实桌面端到端流程测试：启动 → 框选截图 → 编辑器出现（并抓屏留证）。"""
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import PyShotApp
from snipper import grab_virtual_desktop
from style import apply_theme

HERE = os.path.dirname(os.path.abspath(__file__))

app = QApplication(sys.argv)
apply_theme(app)
core = PyShotApp(app)
print("托盘可用:", core.tray_available)

# --- 1) 模拟按 PrintScreen：覆盖层出现，顶部应有一条操作提示 ---
core.capture_region()
QTest.qWait(700)
snip = core.snipper
print("覆盖层存在:", snip is not None, "模式:", snip.mode if snip else None)
snip.grab().copy(560, 10, 800, 60).save(os.path.join(HERE, "_test_hint.png"))

# --- 2) 拖拽框选一块区域（模拟用户操作） ---
QTest.mousePress(snip, Qt.LeftButton, Qt.NoModifier, QPoint(300, 220))
for i in range(1, 6):
    QTest.mouseMove(snip, QPoint(300 + i * 60, 220 + i * 40))
    QTest.qWait(40)
QTest.mouseRelease(snip, Qt.LeftButton, Qt.NoModifier, QPoint(600, 420))
QTest.qWait(1200)

# --- 3) 编辑器应出现且可见 ---
print("编辑器窗口数:", len(core.editors))
assert core.editors, "截图后没有出现编辑器窗口！"
ed = core.editors[0]
print("编辑器可见:", ed.isVisible(), " 标签数:", ed.tabs.count(),
      " 尺寸:", ed.width(), "x", ed.height())

# --- 4) 再截一张，应变成第二个标签而不是第二个窗口 ---
core.open_editor(grab_virtual_desktop()[0])
QTest.qWait(400)
print("第二张后：窗口数 =", len(core.editors), " 标签数 =", ed.tabs.count())
assert ed.tabs.count() == 2

# --- 5) 二次截图时编辑器应自动最小化，截完自动恢复 ---
QTest.qWait(300)
ed.showNormal()
QTest.qWait(200)
core.capture_region()
QTest.qWait(600)
print("截图期间编辑器已最小化:", ed.isMinimized())
assert ed.isMinimized(), "二次截图时编辑器没有自动最小化！"
snip = core.snipper
QTest.mousePress(snip, Qt.LeftButton, Qt.NoModifier, QPoint(320, 240))
for i in range(1, 5):
    QTest.mouseMove(snip, QPoint(320 + i * 55, 240 + i * 35))
    QTest.qWait(40)
QTest.mouseRelease(snip, Qt.LeftButton, Qt.NoModifier, QPoint(540, 380))
QTest.qWait(1200)
print("截完已恢复显示:", ed.isVisible() and not ed.isMinimized(),
      " 标签数 =", ed.tabs.count())
assert ed.isVisible() and not ed.isMinimized(), "截图结束后编辑器没有恢复"
assert ed.tabs.count() == 3

# --- 6) 取消截图也应恢复编辑器 ---
core.capture_region()
QTest.qWait(500)
assert core.editors[0].isMinimized()
core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(500)
print("Esc 取消后已恢复:", not core.editors[0].isMinimized())
assert not core.editors[0].isMinimized(), "取消截图后编辑器没有恢复"

# --- 7) 编辑器内的"截图"按钮 ---
from PySide6.QtWidgets import QPushButton
btn = ed.findChild(QPushButton, "primarybtn")
assert btn is not None, "顶栏没有找到截图按钮"
QTest.mouseClick(btn, Qt.LeftButton)
QTest.qWait(600)
print("点编辑器截图按钮后：覆盖层 =", core.snipper is not None,
      " 编辑器已最小化 =", ed.isMinimized())
assert core.snipper is not None and ed.isMinimized()
core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(400)

# --- 8) 抓整屏，看用户实际能看到什么 ---
QTest.qWait(400)
grab_virtual_desktop()[0].save(os.path.join(HERE, "_test_flow.png"))
print("已保存 _test_flow.png")

core.shutdown()
app.quit()
print("done")
