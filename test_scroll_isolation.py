# -*- coding: utf-8 -*-
"""滚动截图不得干扰画面：选区阶段只取坐标、编辑器全程保持最小化、不加标签。

历史 bug：选区松手时同时发了 captured，宿主把它当普通截图处理，
把编辑器恢复并前置，正好盖住要滚动的区域，之后每帧都把编辑器拍进去。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import tempfile as _tempfile
from pathlib import Path as _Path

import session as _session

# 会话缓存隔离到临时目录：新建编辑器会自动恢复上次的标签，
# 不隔离的话这里会读到用户真实的缓存、标签计数全乱（也不该动用户数据）
_tmp = _Path(_tempfile.mkdtemp(prefix="pyshot_scrolliso_"))
_session.SESSION_DIR = _tmp / "session"
_session.SESSION_SETTINGS_PATH = _tmp / "settings.json"
_session.clear_session()

from main import PyShotApp
from snipper import SnipperOverlay

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


app = QApplication([])
core = PyShotApp(app)

# 准备一个已打开并最小化的编辑器（模拟"二次截图"场景）
core.open_editor(QPixmap(400, 300))
ed = core.editors[0]
QTest.qWait(200)


def drag(snip, p1=(120, 120), p2=(520, 520)):
    snip._origin = QPoint(*p1)
    snip._current = QPoint(*p2)
    snip._selecting = True
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(*p2),
                     Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    snip.mouseReleaseEvent(ev)


# --- 1) 滚动截图入口应使用 scroll 模式 ---
core.capture_scrolling()
QTest.qWait(400)
snip = core.snipper
check("滚动截图使用 scroll 模式", snip is not None and snip.mode == "scroll",
      snip.mode if snip else "None")
check("选区阶段编辑器已最小化", ed.isMinimized())

# --- 2) scroll 模式只发选区信号，不发截图信号 ---
captured, regions = [], []
snip.captured.connect(lambda p: captured.append(p))
snip.region_selected.connect(lambda r: regions.append(r))
drag(snip)
QTest.qWait(300)
check("scroll 模式不发出 captured（不会触发打开编辑器）", not captured)
check("scroll 模式发出选区坐标", len(regions) == 1,
      f"{len(regions)} 次")

# --- 3) 滚动截图进行中：编辑器仍最小化、没有新增标签 ---
QTest.qWait(700)                       # 等 scroller 真正启动
check("滚动截图已启动", core.scroller is not None)
check("滚动期间编辑器保持最小化（不会被拍进画面）", ed.isMinimized())
check("滚动期间没有多加标签", ed.tabs.count() == 1,
      f"标签数 {ed.tabs.count()}")

# --- 4) 滚动截图失败/结束后编辑器应恢复，且只有成功才加标签 ---
outcome = []
if core.scroller is not None:
    core.scroller.finished_ok.connect(lambda p: outcome.append("ok"))
    core.scroller.failed.connect(lambda m: outcome.append("fail"))
    core.scroller.stop()
QTest.qWait(1500)
check("结束后编辑器恢复显示", not ed.isMinimized())
check("结束后标签数符合结果（成功才加）",
      ed.tabs.count() == (2 if "ok" in outcome else 1),
      f"结果={outcome} 标签数={ed.tabs.count()}")

# --- 5) 手动滚动模式同样走 scroll 模式 ---
core.capture_scrolling(manual=True)
QTest.qWait(400)
check("手动滚动也用 scroll 模式",
      core.snipper is not None and core.snipper.mode == "scroll")
captured.clear()
drag(core.snipper)
QTest.qWait(200)
check("手动模式也不发 captured", not captured)
check("手动模式 scroller 已启动且保持最小化",
      core.scroller is not None and core.scroller.manual and ed.isMinimized())
if core.scroller is not None:
    core.scroller.stop()
QTest.qWait(1200)

# --- 6) 普通截图仍然正常打开编辑器 ---
before = ed.tabs.count()
core.capture_region()
QTest.qWait(400)
check("普通截图用 region 模式", core.snipper.mode == "region")
core.snipper.captured.emit(QPixmap(200, 150))     # 模拟框选完成
QTest.qWait(600)
check("普通截图仍会新增标签", ed.tabs.count() == before + 1,
      f"{before} → {ed.tabs.count()}")

core.shutdown()
print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("滚动截图不干扰画面测试通过 ✔")
