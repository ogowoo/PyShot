# -*- coding: utf-8 -*-
"""回归测试：从托盘路径触发截图时，覆盖层必须立刻画出遮罩（不依赖鼠标事件）。

之前的 bug：托盘双击发生在 shell 原生消息回调里，窗口 show 后没有被正确绘制，
表现为"窗口在但没有遮罩，动一下鼠标才出现"。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from main import PyShotApp
from snipper import grab_virtual_desktop
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)
core = PyShotApp(app)


def brightness(pix):
    img = pix.toImage()
    total = n = 0
    for y in range(0, img.height(), 40):
        for x in range(0, img.width(), 40):
            c = img.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
            n += 1
    return total / (n * 3)


base = brightness(grab_virtual_desktop()[0])
print(f"截图前屏幕亮度: {base:.1f}")

# --- 模拟双击托盘图标：走 activated 信号 → 延后执行 ---
core._on_tray_activated(QSystemTrayIcon.DoubleClick)
QTest.qWait(500)                      # 全程没有任何鼠标移动/点击
assert core.snipper is not None, "托盘双击没有打开覆盖层"
after = brightness(grab_virtual_desktop()[0])
print(f"覆盖层出现后亮度: {after:.1f} （无鼠标交互）")

masked = after < base * 0.7
print("遮罩已画出:", masked)
assert masked, f"首次从托盘截图时没有遮罩（{base:.1f} → {after:.1f}）"

# 覆盖层还应铺满整个虚拟桌面
geo = core.snipper.geometry()
expect = core.snipper._geo
print("覆盖范围:", geo.width(), "x", geo.height(), " 期望:", expect.width(), "x", expect.height())
assert geo == expect, "覆盖层没有铺满虚拟桌面"

# Esc 能退出（说明窗口确实拿到了键盘焦点）
core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(300)
print("Esc 退出后 snipper =", core.snipper)
assert core.snipper is None

core.shutdown()
app.quit()
print("done")
