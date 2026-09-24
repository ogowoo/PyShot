# -*- coding: utf-8 -*-
"""帮助系统：三语内容、搜索、快捷键实时收集、入口（F1 / 托盘）。

用户要"做一个帮助，也一样的三语" —— 所以这里不仅要测窗口能开，更要测
**每一小节、每一行都有简体/繁體/English 三种文本**（内容写在 help_text.py，
只写简体，繁體与英文由 i18n 词表提供；漏译的话英文界面会蹦中文）。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 要用 set_language() 现切三种语言，所以**不能**设 PYSHOT_LANG
# （它的优先级更高，会把语言钉死）
os.environ.pop("PYSHOT_LANG", None)
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_help_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import style

style.apply_theme(app)

import helpwin
from editor import EditorWindow
from help_text import HELP_INTRO, HELP_TITLE, SECTIONS

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 内容完整性 ----------
check("有帮助标题与简介", bool(HELP_TITLE and HELP_INTRO))
check("小节数量合理（>=6）", len(SECTIONS) >= 6, f"{len(SECTIONS)} 节")
bad_empty = [t for t, lines in SECTIONS if not lines or not any(
    x.strip() for x in lines)]
check("每个小节都有内容", not bad_empty, str(bad_empty))

# ---------- 2) **每一条都是三语**（这就是"一样的三语"） ----------
missing = []
for title, lines in SECTIONS:
    for text in [title] + list(lines):
        row = i18n.TABLE.get(text)
        if not row or not row[0].strip() or not row[1].strip():
            missing.append(text[:40])
check("**帮助里每一小节/每一行都有简体/繁體/English**", not missing,
      f"缺 {len(missing)} 条：{missing[:3]}")
check("帮助里没有漏译的界面词（标题/简介/关闭/搜索框）",
      all(i18n.TABLE.get(k) and i18n.TABLE[k][1] for k in
          (HELP_TITLE, HELP_INTRO, "快捷键一览", "关闭",
           "搜索帮助内容…（例如：拼图、滚动、快捷键）")),
      "")

# 繁體不能等于简体（否则等于没翻）
same_tw = [t for t, lines in SECTIONS for t2 in [t] + list(lines)
           if (i18n.TABLE.get(t2) or ("", ""))[0] == t2
           and any("\u4e00" <= ch <= "\u9fff" for ch in t2)]
check("繁體确实转换过（不是照抄简体）", not same_tw, str(same_tw[:3]))

# ---------- 3) 窗口能开、内容能切 ----------
win = EditorWindow(QPixmap(200, 150))
win.set_hotkey_hint("Ctrl+Alt+X", "Ctrl+Alt+F")
win.show_help()
dlg = win._help_dialog
check("帮助入口打开了窗口", dlg is not None and dlg.isVisible())
check("非模态（可以一边看一边操作）", not dlg.isModal())
check("小节列表 = 内容小节 + 快捷键一览",
      dlg.topics.count() == len(SECTIONS) + 1, f"{dlg.topics.count()}")
check("默认选中第一小节", dlg.topics.currentRow() == 0)
first = dlg.view.toPlainText()
check("正文渲染出来了", len(first) > 60, f"{len(first)} 字")
check("**热键占位符被替换成真实热键**",
      "Ctrl+Alt+X" in first and "{hotkey}" not in first, first[:60])
dlg.topics.setCurrentRow(1)
check("切换小节会换正文", dlg.view.toPlainText() != first)
check("正文字体里没有残留的 ** 加粗标记",
      "**" not in dlg.view.toPlainText())

# ---------- 4) 快捷键一览取自当前菜单（不会过期） ----------
dlg.topics.setCurrentRow(dlg.topics.count() - 1)
sc_text = dlg.view.toPlainText()
list_sc = dict(win.help_shortcuts())
check("快捷键一览含全局热键", any("Ctrl+Alt+X" == v for v in list_sc.values()),
      str(list(list_sc.items())[:2]))
check("快捷键一览含编辑器快捷键（如 Ctrl+S 保存）", "Ctrl+S" in sc_text)
check("快捷键一览含帮助自己的 F1", "F1" in sc_text)
check("快捷键是从菜单实时收集的（>10 条）", len(list_sc) > 10, f"{len(list_sc)} 条")

# ---------- 5) 搜索 ----------
dlg.search.setText("compose" if i18n.current_language() == "en" else "截图")
vis = [dlg.topics.item(i).text() for i in range(dlg.topics.count())
       if not dlg.topics.item(i).isHidden()]
check("搜索能筛出相关小节", 0 < len(vis) < dlg.topics.count(), str(vis))
dlg.search.setText("绝对不存在的词xyzzy")
check("搜不到时全部隐藏", all(dlg.topics.item(i).isHidden()
                        for i in range(dlg.topics.count())))
dlg.search.clear()
check("清空搜索后全部恢复",
      all(not dlg.topics.item(i).isHidden() for i in range(dlg.topics.count())))

# ---------- 6) 三种语言都能切（正文真的换语言） ----------
samples = {}
for lang in ("zh_CN", "zh_TW", "en"):
    i18n.set_language(lang, persist=False)
    dlg.retranslate()
    dlg.topics.setCurrentRow(0)
    samples[lang] = dlg.view.toPlainText()
check("简体正文是中文", "框选截图" in samples["zh_CN"], samples["zh_CN"][:40])
check("**繁體正文是繁体**", "框選截圖" in samples["zh_TW"], samples["zh_TW"][:40])
check("**英文正文是英文**", "Press" in samples["en"] and "capture" in samples["en"],
      samples["en"][:60])
check("三种语言的正文互不相同",
      len({samples["zh_CN"], samples["zh_TW"], samples["en"]}) == 3)
check("英文正文里没有中文残留",
      not any("\u4e00" <= ch <= "\u9fff" for ch in samples["en"]),
      [ch for ch in samples["en"] if "\u4e00" <= ch <= "\u9fff"][:8])
i18n.set_language("zh_CN", persist=False)
dlg.retranslate()

# ---------- 7) 入口：编辑器菜单 / 托盘 ----------
i18n.set_language("zh_CN", persist=False)
win.retranslate()          # 切回简体后菜单文案要跟着刷（否则断言的是旧语言）
help_items = [a.text() for a in win.menus["help"].actions() if not a.isSeparator()]
check("编辑器「帮助」菜单里有使用帮助", i18n.tr("使用帮助") in help_items,
      str(help_items))
check("使用帮助绑了 F1", win.act_help.shortcut().toString() == "F1",
      win.act_help.shortcut().toString())
import main as m

tray_labels = [a.text().split("\t")[0] for a in
               (lambda: [x for x in []])()] if False else None
# 托盘菜单：用一个轻量 Probe 构建（和 test_tray_menu 同样的桩）
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor


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
        self.menu = menu

    def setToolTip(self, t):
        pass

    def show(self):
        pass


class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self.editors = []
        m.QGuiApplication = FakeGui()
        self._build_tray_menu()


p = Probe()
labels = [a.text().split("\t")[0] for a in p.menu.actions() if not a.isSeparator()]
check("**托盘菜单里也有「使用帮助」**", i18n.tr("使用帮助") in labels, str(labels))
check("托盘帮助项有图标",
      not [a for a in p.menu.actions()
           if a.text().split("\t")[0] == i18n.tr("使用帮助") and a.icon().isNull()])

# ---------- 8) 重复打开复用同一个窗口，不越开越多 ----------
before = dlg
win.show_help()
check("再次打开复用同一个帮助窗口", win._help_dialog is before)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("帮助系统（三语）测试通过 ✔")
