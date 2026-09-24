# -*- coding: utf-8 -*-
"""抓一张编辑器界面的真实渲染图，检查主题效果。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from editor import EditorWindow
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)

pix = QPixmap(os.path.join(os.path.dirname(__file__), "demo.png"))
win = EditorWindow(pix)
win.resize(1100, 720)
# 再补两张截图，展示标签页
win.add_canvas(QPixmap(400, 260))
win.add_canvas(QPixmap(640, 360))
win.tabs.setCurrentIndex(0)
win.show()
QTest.qWait(600)
win.grab().save(os.path.join(os.path.dirname(__file__), "_test_editor_ui.png"))
win.set_tool("step")
win.tabs.setCurrentIndex(2)
QTest.qWait(300)
win.grab().save(os.path.join(os.path.dirname(__file__), "_test_editor_ui2.png"))
print("标签数:", win.tabs.count())
print("ok")
