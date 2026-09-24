# -*- coding: utf-8 -*-
"""验证编辑器取色放大镜：缩放显示下红框像素应与色值标签一致。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from editor import EditorWindow
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)

# 色块图：25px 一块，每块不同色相，块间 1px 白线
pix = QPixmap(800, 600)
p = QPainter(pix)
for y in range(0, 600, 25):
    for x in range(0, 800, 25):
        p.fillRect(x, y, 24, 24, QColor.fromHsl(((x + y) // 25 * 24) % 360, 200, 130))
p.end()

win = EditorWindow(pix)
win.resize(900, 650)
win.canvas.set_zoom(0.62)
win.set_tool("pick")
win.show()
QTest.qWait(400)
# 悬停在几个色块交界处（最容易取错的位置）
QTest.mouseMove(win.canvas, QPointF(300, 200).toPoint())
QTest.qWait(200)
win.canvas.grab().save(os.path.join(os.path.dirname(__file__), "_test_pick_mag.png"))
print("zoom:", win.canvas.zoom)
print("ok")
