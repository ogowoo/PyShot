# -*- coding: utf-8 -*-
"""界面文案完整性：切到英文后，**所有可见文案都不应残留中文**。

这个测试是"扫一遍"而不是逐条断言：把编辑器、各对话框、托盘菜单里所有控件的
text / toolTip / windowTitle / 下拉项都收集起来，检查有没有中文字符。
比人工找漏译可靠得多——发现漏的直接把键补进 gen_i18n.py 即可。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
os.environ["PYSHOT_LANG"] = "en"          # 本测试固定英文
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import i18n
from i18n import set_language, tr

set_language("en", persist=False)

CJK = re.compile(r"[\u4e00-\u9fff]")

# 允许保留中文的东西：用户数据/配置值本身（不是界面文案）
ALLOW = (
    "仅供参考",            # 水印默认文字（配置值）
    "PyShot",              # 产品名
    "Microsoft YaHei",     # 字体名
    "简体中文",            # 语言名本身不翻译（各语言都显示自己的写法）
    "繁體中文",
    "English",
)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def texts_of(widget):
    """收集一个窗口里所有可见文案（含提示与下拉项）。"""
    out = []
    try:
        out.append(("windowTitle", widget.windowTitle()))
    except Exception:                              # noqa: BLE001
        pass
    for w in widget.findChildren(object):
        for attr in ("text", "toolTip", "placeholderText", "windowTitle"):
            try:
                fn = getattr(w, attr, None)
                if callable(fn):
                    v = fn()
                    if isinstance(v, str) and v.strip():
                        out.append((type(w).__name__ + "." + attr, v))
            except Exception:                      # noqa: BLE001
                continue
        # 下拉框的每一项
        try:
            if hasattr(w, "count") and hasattr(w, "itemText"):
                for i in range(w.count()):
                    out.append((type(w).__name__ + ".item", w.itemText(i)))
        except Exception:                          # noqa: BLE001
            pass
        # 表头
        try:
            if hasattr(w, "headerItem"):
                for i in range(w.columnCount()):
                    it = w.headerItem(i)
                    if it is not None:
                        out.append(("header", it.text()))
        except Exception:                          # noqa: BLE001
            pass
    return out


def chinese_in(items):
    bad = []
    for where, s in items:
        if not CJK.search(s):
            continue
        if any(a in s for a in ALLOW):
            continue
        bad.append((where, s.replace("\n", "\\n")[:70]))
    return bad


# ---------- 编辑器 ----------
from editor import EditorWindow
win = EditorWindow(QPixmap(400, 300))
items = texts_of(win)
bad = chinese_in(items)
check("英文模式下编辑器无中文残留", not bad, "\n      " + "\n      ".join(
    f"{w}: {s}" for w, s in bad[:14]) if bad else "")

# ---------- 边框对话框 ----------
from border import BORDER_DEFAULTS, BorderDialog
bd = BorderDialog(None, BORDER_DEFAULTS, win.canvas.base_pixmap.size())
bad_bd = chinese_in(texts_of(bd))
check("英文模式下边框对话框无中文残留", not bad_bd,
      "\n      " + "\n      ".join(f"{w}: {s}" for w, s in bad_bd[:10])
      if bad_bd else "")

# ---------- 水印对话框 ----------
from watermark import DEFAULT_SETTINGS, WatermarkDialog
wd = WatermarkDialog(None, DEFAULT_SETTINGS, win.canvas.base_pixmap.size())
bad_wd = chinese_in(texts_of(wd))
check("英文模式下水印对话框无中文残留", not bad_wd,
      "\n      " + "\n      ".join(f"{w}: {s}" for w, s in bad_wd[:10])
      if bad_wd else "")

# ---------- 托盘菜单（含子菜单） ----------
import main as m


class FakeScreen:
    def __init__(self, n, g, d):
        from PySide6.QtCore import QRect
        self._n, self._g, self._d = n, QRect(*g), d

    def name(self):
        return self._n

    def geometry(self):
        return self._g

    def devicePixelRatio(self):
        return self._d

    def grabWindow(self, w=0):
        px = QPixmap(20, 20)
        px.fill()
        return px


class FakeGui:
    def screens(self):
        return [FakeScreen("s1", (0, 0, 1920, 1080), 1.0)]

    def primaryScreen(self):
        return self.screens()[0]

    def screenAt(self, pt):
        return self.screens()[0]


class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, t):
        self.tip = t

    def show(self):
        pass


class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        m.QGuiApplication = FakeGui()
        self._build_tray_menu()


p = Probe()
menu_items = []
for a in p.menu.actions():
    if a.isSeparator():
        continue
    menu_items.append(("menu", a.text().split("\t")[0]))
    if a.menu():
        sub = a.menu()
        sub.aboutToShow.emit()                  # 触发按屏幕/语言重建
        for sa in sub.actions():
            if not sa.isSeparator():
                menu_items.append(("submenu", sa.text()))
p.menu_lang.aboutToShow.emit()
for sa in p.menu_lang.actions():
    if not sa.isSeparator():
        menu_items.append(("language", sa.text()))

bad_menu = chinese_in(menu_items)
check("英文模式下托盘菜单无中文残留", not bad_menu,
      "\n      " + "\n      ".join(f"{w}: {s}" for w, s in bad_menu[:10])
      if bad_menu else "")

# 托盘提示（气泡与悬停提示）
tips = [("trayTip", p.tray.tip)]
bad_tip = chinese_in(tips)
check("英文模式下托盘悬停提示无中文残留", not bad_tip,
      str(bad_tip[:3]) if bad_tip else "")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("英文界面无中文残留 ✔")
