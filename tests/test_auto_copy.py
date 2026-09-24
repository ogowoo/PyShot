# -*- coding: utf-8 -*-
"""截图后自动进剪贴板（选项，默认开）。

用户要"截图后马上放到剪贴板" —— 这样截完直接粘到聊天窗口/文档里，不用再按 Ctrl+C。
本文件锁住：
  · 默认开：区域/全屏截图完成后剪贴板里就是那张图
  · 关掉后不再动剪贴板（用户原来的剪贴板内容要保住）
  · **用「打开图片编辑」打开已有文件时绝不能覆盖剪贴板**
  · 滚动长截图的结果同样按选项进剪贴板
  · 编辑器菜单里的开关能读写同一个设置键（主程序与编辑器必须一致）
  · 标注后的版本仍可用 Ctrl+C 单独复制
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = Path(__file__).resolve().parent.parent   # 项目根（本文件在子目录里）
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_copy_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import style

style.apply_theme(app)

import editor as ed_mod
import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def solid(w, h, color) -> QPixmap:
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


def clip_color() -> str:
    img = QApplication.clipboard().image()
    if img is None or img.isNull():
        return "（空）"
    return img.pixelColor(1, 1).name()


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
    """只用到截图完成→剪贴板这段，不碰托盘/热键/覆盖层。"""

    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self.editors = []
        self._scroll_mode = None
        m.QGuiApplication = FakeGui()

    def _cap_log(self, *a):
        pass

    def _on_snip_done(self):
        pass

    def _finish_capture_session(self):
        pass

    def open_editor(self, pixmap):
        self.editors.append(pixmap)      # 只记录，别真开窗口

    def _notify(self, *a):
        pass


# ---------- 1) 默认开：截图完成就进剪贴板 ----------
i18n.set_setting(ed_mod.AUTO_COPY_SETTING, True)
core = Probe()
QApplication.clipboard().setPixmap(solid(9, 9, "#000000"))     # 先占个"旧内容"
check("默认选项是开", ed_mod.auto_copy_on_capture()
      and core.auto_copy(solid(30, 20, "#ff0000")))
check("**截图完成后剪贴板里就是这张图**", clip_color() == "#ff0000", clip_color())

# ---------- 2) 关掉：不再动剪贴板 ----------
i18n.set_setting(ed_mod.AUTO_COPY_SETTING, False)
QApplication.clipboard().setPixmap(solid(9, 9, "#00ff00"))     # 用户自己复制的东西
check("关掉后 auto_copy 返回 False",
      core.auto_copy(solid(30, 20, "#0000ff")) is False)
check("**关掉后剪贴板保持用户原来的内容（不被覆盖）**",
      clip_color() == "#00ff00", clip_color())

# ---------- 3) 关键：打开已有图片不能覆盖剪贴板 ----------
i18n.set_setting(ed_mod.AUTO_COPY_SETTING, True)               # 就算开着也不行
QApplication.clipboard().setPixmap(solid(9, 9, "#123456"))
img_path = _tmp / "open_me.png"
solid(40, 30, "#f0f0f0").save(str(img_path), "PNG")
core2 = Probe()
core2.open_editor(solid(40, 30, "#f0f0f0"))                    # 模拟"打开图片编辑"
check("**「打开图片编辑」不会覆盖剪贴板**", clip_color() == "#123456",
      clip_color())

# ---------- 4) 滚动长截图的结果也按选项复制 ----------
i18n.set_setting(ed_mod.AUTO_COPY_SETTING, True)
core3 = Probe()
core3.scroller = object()          # _on_scroll_finished 会把它清空
core3._on_scroll_finished(solid(50, 400, "#ffaa00"))
check("**滚动截图拼出的长图也进剪贴板**", clip_color() == "#ffaa00",
      clip_color())

# ---------- 5) 编辑器菜单里的开关 ----------
win = ed_mod.EditorWindow(solid(120, 90, "#ffffff"))
check("选项菜单里有这个开关", win.act_auto_copy.text() == "截图后自动复制到剪贴板",
      win.act_auto_copy.text())
check("勾选状态跟着设置走（当前开着）", win.act_auto_copy.isChecked())
win.act_auto_copy.setChecked(False)
check("取消勾选会写进设置",
      i18n.get_setting(ed_mod.AUTO_COPY_SETTING, None) is False,
      str(i18n.get_setting(ed_mod.AUTO_COPY_SETTING, None)))
check("**主程序读的就是这个键**",
      m.AUTO_COPY_SETTING == ed_mod.AUTO_COPY_SETTING
      and m.auto_copy_on_capture() is False,
      f"{m.AUTO_COPY_SETTING} / {m.auto_copy_on_capture()}")
check("关掉后主程序也不会复制",
      core3.auto_copy(solid(10, 10, "#000000")) is False)
win.act_auto_copy.setChecked(True)
check("再打开又恢复", ed_mod.auto_copy_on_capture() is True)

# ---------- 6) 标注后的版本仍可单独复制（Ctrl+C 那条路没被破坏） ----------
QApplication.clipboard().setPixmap(solid(9, 9, "#abcdef"))
win.copy_to_clipboard()
check("编辑器里 Ctrl+C 仍能把当前结果复制走（含标注）",
      clip_color() != "#abcdef", clip_color())

# ---------- 7) 菜单里两项共存（保留编辑器 / 自动复制） ----------
opts = [a.text() for a in win.menus["options"].actions() if not a.isSeparator()]
check("选项菜单两项都在",
      "截图时不最小化编辑器" in opts and "截图后自动复制到剪贴板" in opts,
      str(opts))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("截图后自动复制到剪贴板测试通过 ✔")
