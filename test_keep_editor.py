# -*- coding: utf-8 -*-
"""截图时编辑器要不要自动最小化。

默认：自动最小化让位（免得自己被拍进图里）。
但用户发现"想截编辑器本身"时就没法弄了 —— 所以加了开关
「选项 → 截图时不最小化编辑器」，打开后编辑器留在原地。

本文件锁住三种情况：
  · 默认（关）：截图时编辑器最小化，结束/取消后还原
  · 打开时：编辑器**不**最小化（这样才截得到它）
  · 开关读写的是同一个设置键（主程序与编辑器菜单共用，不能各写一份）
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

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_keep_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import editor as ed_mod
import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeScreen:
    def name(self):
        return "s"

    def geometry(self):
        return QRect(0, 0, 1920, 1080)

    def devicePixelRatio(self):
        return 1.0

    def grabWindow(self, w=0):
        p = QPixmap(20, 20)
        p.fill(QColor("white"))
        return p


class FakeGui:
    def screens(self):
        return [FakeScreen()]

    primaryScreen = screenAt = lambda self, *a: self.screens()[0]


class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def setContextMenu(self, menu):
        pass

    def setToolTip(self, t):
        pass

    def show(self):
        pass

    def showMessage(self, *a):
        pass


class Probe(m.PyShotApp):
    """只跑最小化/还原那段逻辑，不碰托盘与热键。"""

    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self.editors = []
        self._minimized_by_capture = []
        m.QGuiApplication = FakeGui()

    def _cap_log(self, *a):
        pass


def make_editor():
    win = ed_mod.EditorWindow(QPixmap(200, 150))
    win.show()
    return win


# ---------- 1) 默认：截图时最小化，结束后还原 ----------
i18n.set_setting(ed_mod.KEEP_EDITOR_SETTING, False)
core = Probe()
win = make_editor()
core.editors.append(win)
check("默认开关是关的", not core.keep_editor_on_capture())
core._prepare_capture()
check("**默认行为：截图时编辑器自动最小化**", win.isMinimized(),
      f"isMinimized={win.isMinimized()}")
core._finish_capture_session()
check("截图结束后编辑器还原", not win.isMinimized())

# 取消截图也要还原（以前只处理了正常结束）
core._prepare_capture()
check("再次截图又最小化", win.isMinimized())
core._on_snip_cancelled()
check("取消截图后也还原", not win.isMinimized())

# 本来就是最小化的窗口，不该被"还原"成正常状态
win.showMinimized()
core._prepare_capture()
core._finish_capture_session()
check("原本就最小化的窗口不会被顺带还原", win.isMinimized())

# ---------- 2) 打开开关：截图时保留编辑器（才能截它自己） ----------
i18n.set_setting(ed_mod.KEEP_EDITOR_SETTING, True)
core2 = Probe()
win2 = make_editor()
core2.editors.append(win2)
check("开关打开后 keep_editor_on_capture() 为真",
      core2.keep_editor_on_capture())
core2._prepare_capture()
check("**打开后：截图时编辑器留在原地（不被最小化）**",
      not win2.isMinimized(), f"isMinimized={win2.isMinimized()}")
check("也不会被记进「待还原」列表", core2._minimized_by_capture == [],
      str(core2._minimized_by_capture))
core2._finish_capture_session()
check("结束后编辑器仍在原地", not win2.isMinimized())

# ---------- 3) 编辑器菜单里的开关能读写同一个设置 ----------
win3 = ed_mod.EditorWindow(QPixmap(120, 90))
check("编辑器菜单里有这个开关", win3.act_keep_editor.isVisible()
      or win3.act_keep_editor.text() == "截图时不最小化编辑器",
      win3.act_keep_editor.text())
check("菜单初始勾选状态跟着设置走", win3.act_keep_editor.isChecked())
win3.act_keep_editor.setChecked(False)
check("**取消勾选会写进设置**（主程序读得到）",
      i18n.get_setting(ed_mod.KEEP_EDITOR_SETTING, None) is False,
      str(i18n.get_setting(ed_mod.KEEP_EDITOR_SETTING, None)))
core3 = Probe()
win3b = make_editor()
core3.editors.append(win3b)
core3._prepare_capture()
check("关掉之后又恢复「截图时最小化」的老行为", win3b.isMinimized())

# 主程序与编辑器必须用同一个键（写岔了开关就会"看着有、其实没用"）
check("主程序与编辑器共用同一个设置键",
      m.KEEP_EDITOR_SETTING == ed_mod.KEEP_EDITOR_SETTING,
      f"{m.KEEP_EDITOR_SETTING} / {ed_mod.KEEP_EDITOR_SETTING}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("截图时保留编辑器的开关测试通过 ✔")
