# -*- coding: utf-8 -*-
"""托盘菜单结构测试：分组、子菜单、图标、快捷键显示。

菜单是用户唯一的主入口，很容易在后续改动中被打乱（项越来越多、分组消失）。
这里把"整理好的结构"锁住：新增项必须放进合适的分组，不能随手往顶层塞。
"""
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeScreen:
    def __init__(self, n, g, d):
        self._n, self._g, self._d = n, QRect(g), d

    def name(self):
        return self._n

    def geometry(self):
        return QRect(self._g)

    def devicePixelRatio(self):
        return self._d

    def grabWindow(self, w=0):
        p = QPixmap(20, 20)
        p.fill(QColor("white"))
        return p


class FakeGui:
    def __init__(self, sc):
        self._s = sc

    def screens(self):
        return list(self._s)

    def primaryScreen(self):
        return self._s[0]

    def screenAt(self, pt):
        return self._s[0]


m.QGuiApplication = FakeGui([
    FakeScreen("screenA", QRect(0, 0, 1920, 1080), 1.0),
    FakeScreen("screenB", QRect(1920, 0, 2560, 1440), 1.5)])


class FakeTray:
    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, t):
        self.tip = t

    def show(self):
        pass


class FakeSignal:
    def connect(self, fn):
        pass


FakeTray.activated = FakeSignal()


class Probe(m.PyShotApp):
    """只跑 _init_tray，不启动真实托盘/热键。"""

    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self._init_tray()


p = Probe()
menu = p.menu

# ---------- 顶层结构 ----------
top = [(a.text().split("\t")[0] if not a.isSeparator() else "|",
        bool(a.menu()), a.isSeparator()) for a in menu.actions()]
names = [t[0] for t in top]
print("顶层:", names)

check("顶层不含旧的长条目（已收进子菜单）",
      not any("滚动长截图（" in n for n in names), str(names))
check("截图三件事在顶部且连续",
      names[:3] == ["区域截图", "全屏截图", "选择显示器截图"], str(names[:3]))
check("选择显示器是子菜单", top[2][1] is True)
check("滚动长截图是子菜单",
      any(t[1] and t[0] == "滚动长截图" for t in top))
check("工具项成组（取色/贴图相邻）",
      names.index("屏幕取色") + 1 == names.index("贴出剪贴板图片"), str(names))
check("窗口项成组（打开图片/打开编辑器相邻）",
      names.index("打开图片编辑…") + 1 == names.index("显示编辑器"))
check("退出在最后", names[-1] == "退出 PyShot", str(names[-1]))

# 分组分隔线：5 条（截图|滚动、滚动|工具、工具|语言、语言|退出 …）
sep_count = sum(1 for t in top if t[2])
check("分隔线数量合理（5 条）", sep_count == 5, f"{sep_count} 条")
check("有语言子菜单", "语言" in names, str(names))

# ---------- 图标与快捷键显示 ----------
plain = [a for a in menu.actions() if not a.isSeparator()]
no_icon = [a.text() for a in plain if a.icon().isNull()]
check("顶层项都有图标", not no_icon, str(no_icon))
check("区域截图显示快捷键在右列",
      "\t" in p.act_region.text() and "Ctrl+Alt+X" in p.act_region.text(),
      repr(p.act_region.text()))
check("全屏截图显示快捷键在右列",
      "\t" in p.act_full.text() and "Ctrl+Alt+F" in p.act_full.text(),
      repr(p.act_full.text()))

# ---------- 滚动子菜单 ----------
scroll_menu = [a.menu() for a in menu.actions() if a.menu()
               and a.text() == "滚动长截图"][0]
scroll_items = [a.text() for a in scroll_menu.actions()]
check("滚动子菜单恰好 4 种模式",
      scroll_items == ["自动滚轮", "拖拽滚动条", "按键翻页", "手动滚动"],
      str(scroll_items))
check("每种模式都有说明",
      all(a.toolTip() for a in scroll_menu.actions()))

# ---------- 选择显示器子菜单 ----------
p.menu_screens.aboutToShow.emit()
items = p.menu_screens.actions()
labels = [a.text() for a in items if not a.isSeparator()]
check("列出每块显示器", sum(1 for s in labels if "：" in s) == 2, str(labels))
check("主屏有标记", any(l.startswith("主屏：") for l in labels), str(labels))
check("高缩放屏标出比例",
      any("@150%" in l for l in labels), str(labels))
check("末尾有所有显示器拼成一张",
      labels[-1] == "所有显示器拼成一张", str(labels))
check("显示器项都有图标",
      all(not a.icon().isNull() for a in items if not a.isSeparator()))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("托盘菜单结构测试通过 ✔")
