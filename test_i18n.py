# -*- coding: utf-8 -*-
"""三语测试（简/繁/英）：查表、系统语言识别、切换持久化、界面文案真的会变。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QMenu

app = QApplication([])

import i18n
from i18n import (AUTO, LANGUAGES, TABLE, language_from_locale, set_language,
                  system_language, tr, tr_in)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 词表完整性 ----------
check("三种语言都在列表里", [c for c, _ in LANGUAGES] == ["zh_CN", "zh_TW", "en"],
      str(LANGUAGES))
total, tw, en = i18n.coverage()
check("词表非空", total > 150, f"{total} 条")
check("繁体覆盖率 100%", tw == total, f"{tw}/{total}")
check("英文覆盖率 >= 80%", en / total >= 0.80, f"{en}/{total}")
check("词表里没有空键/空值",
      all(k and (v[0] or v[1]) for k, v in TABLE.items()))

# ---------- 查表 ----------
set_language("zh_CN", persist=False)
check("简体：原样返回", tr("区域截图") == "区域截图")
set_language("zh_TW", persist=False)
check("繁体：截图 -> 截圖", tr("区域截图") == "區域截圖", tr("区域截图"))
set_language("en", persist=False)
check("英文：截图 -> Capture Region", tr("区域截图") == "Capture Region",
      tr("区域截图"))
check("英文：带占位符", tr("{} 区域截图", "Ctrl+Alt+X")
      == "Ctrl+Alt+X Capture Region", tr("{} 区域截图", "Ctrl+Alt+X"))
check("查不到的词条回落原文", tr("这句话不在词表里") == "这句话不在词表里")

# ---------- 反向查找（切换语言时对现有控件再翻一次）----------
set_language("zh_TW", persist=False)
check("繁体文本能翻回繁体（幂等）",
      tr(tr_in("zh_TW", "区域截图")) == "區域截圖")
set_language("en", persist=False)
check("英文文本能翻回英文（重复切换不乱）",
      tr(tr_in("en", "区域截图")) == "Capture Region")
set_language("zh_CN", persist=False)
check("英文文本能翻回简体", tr("Capture Region") == "区域截图")

# ---------- 系统语言识别 ----------
cases = [("zh_CN", "zh_CN"), ("zh-Hans-CN", "zh_CN"), ("zh_TW", "zh_TW"),
         ("zh-Hant-TW", "zh_TW"), ("zh_HK", "zh_TW"), ("en_US", "en"),
         ("ja_JP", "en"), ("de", "en"), ("", "zh_CN")]
bad = [(c, language_from_locale(c), want)
       for c, want in cases if language_from_locale(c) != want]
check("系统语言映射正确", not bad, str(bad))
check("system_language 返回三语之一",
      system_language() in [c for c, _ in LANGUAGES], system_language())

# ---------- 切换 + 持久化 ----------
orig = i18n.SETTINGS_PATH
tmp = os.path.join(HERE, "_i18n_settings.json")
i18n.SETTINGS_PATH = type(orig)(tmp)
i18n.reset_cache()
set_language("en", persist=True)
i18n.reset_cache()
check("语言选择被保存", i18n.saved_language() == "en", i18n.saved_language())
set_language(AUTO, persist=True)
i18n.reset_cache()
check("可以切回跟随系统", i18n.saved_language() == AUTO)
check("跟随系统时用系统语言",
      i18n.current_language() == system_language(),
      f"{i18n.current_language()} vs {system_language()}")
i18n.SETTINGS_PATH = orig
i18n.reset_cache()
try:
    os.remove(tmp)
except OSError:
    pass

# ---------- 界面文案真的会变（托盘菜单）----------
import main as m


class FakeScreen:
    def __init__(self, n, g, d):
        from PySide6.QtCore import QRect
        self._n, self._g, self._d = n, QRect(g), d

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


def top_labels(menu):
    return [a.text().split("\t")[0] for a in menu.actions() if not a.isSeparator()]


set_language("zh_CN", persist=False)
p = Probe()
zh = top_labels(p.menu)
set_language("en", persist=False)
p_en = Probe()
en = top_labels(p_en.menu)
set_language("zh_TW", persist=False)
p_tw = Probe()
tw = top_labels(p_tw.menu)

check("托盘菜单中文版", "区域截图" in zh and "退出 PyShot" in zh, str(zh[:4]))
check("托盘菜单英文版", "Capture Region" in en and "Exit PyShot" in en,
      str(en[:4]))
check("托盘菜单繁体版", "區域截圖" in tw and "結束 PyShot" in tw, str(tw[:4]))
check("三种语言的菜单项数量一致", len(zh) == len(en) == len(tw),
      f"{len(zh)}/{len(en)}/{len(tw)}")
check("英文菜单没有残留中文",
      not any(any("\u4e00" <= ch <= "\u9fff" for ch in s) for s in en),
      str([s for s in en if any("\u4e00" <= ch <= "\u9fff" for ch in s)]))
check("繁体菜单译法一致（截图->截圖）",
      all("截图" not in s for s in tw), str([s for s in tw if "截图" in s]))

# ---------- 编辑器文案 ----------
from editor import EditorWindow
set_language("en", persist=False)
win = EditorWindow(QPixmap(300, 200))
check("编辑器标题英文", win.windowTitle() == "PyShot Editor", win.windowTitle())
texts = [a.text() for a in win.findChildren(type(win.act_undo))]
check("编辑器按钮英文（撤销/重做）",
      "Undo" in texts and "Redo" in texts, str(texts[:6]))
set_language("zh_TW", persist=False)
win.retranslate()
check("切换语言后编辑器按钮变繁体", "復原" in [a.text() for a in
                                    win.findChildren(type(win.act_undo))],
      str([a.text() for a in win.findChildren(type(win.act_undo))][:6]))
check("编辑器标题也变繁体", win.windowTitle() == "PyShot 編輯器", win.windowTitle())
set_language("zh_CN", persist=False)
win.retranslate()
check("再切回简体", win.windowTitle() == "PyShot 编辑器")

# ---------- 对话框文案 ----------
from border import BorderDialog, BORDER_DEFAULTS
from watermark import WatermarkDialog, DEFAULT_SETTINGS
set_language("en", persist=False)
bd = BorderDialog(None, BORDER_DEFAULTS, win.canvas.base_pixmap.size())
check("边框对话框标题英文", bd.windowTitle() == "Border / Edge Effect",
      bd.windowTitle())
styles_en = [bd.style.itemText(i) for i in range(bd.style.count())]
check("边框样式名英文", "Torn Paper" in styles_en, str(styles_en))
wd = WatermarkDialog(None, DEFAULT_SETTINGS, win.canvas.base_pixmap.size())
check("水印对话框标题英文", wd.windowTitle() == "Watermark", wd.windowTitle())
set_language("zh_CN", persist=False)
bd2 = BorderDialog(None, BORDER_DEFAULTS, win.canvas.base_pixmap.size())
styles_zh = [bd2.style.itemText(i) for i in range(bd2.style.count())]
check("边框样式名中文", "手撕纸" in styles_zh, str(styles_zh))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("三语测试通过 ✔")
