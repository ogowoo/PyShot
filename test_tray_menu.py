# -*- coding: utf-8 -*-
"""托盘菜单结构测试：分组、子菜单、图标、快捷键显示。

菜单是用户唯一的主入口，很容易在后续改动中被打乱（项越来越多、分组消失）。
这里把"整理好的结构"锁住：新增项必须放进合适的分组，不能随手往顶层塞。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 设置文件也要隔离：滚动长截图的开关存在里面，读真实文件会被用户状态带偏
# （自己开过就断言不出"默认关闭"了）。
import i18n

i18n.SETTINGS_PATH = Path(tempfile.mkdtemp(prefix="pyshot_test_cfg_")) / "settings.json"
i18n.reset_cache()

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

check("顶层不含四种滚动方式（已收进子菜单）",
      not any(n in ("自动滚轮", "拖拽滚动条", "按键翻页", "手动滚动")
              for n in names), str(names))
check("截图三件事在顶部且连续",
      names[:3] == ["区域截图", "全屏截图", "选择显示器截图"], str(names[:3]))
check("选择显示器是子菜单", top[2][1] is True)
check("滚动长截图是子菜单（标题标注实验性）",
      any(t[1] and t[0].startswith("滚动长截图") for t in top), str(names))
check("工具项成组（取色/贴图相邻）",
      names.index("屏幕取色") + 1 == names.index("贴出剪贴板图片"), str(names))
check("窗口项成组（打开图片/打开编辑器相邻）",
      names.index("打开图片编辑…") + 1 == names.index("显示编辑器"))
check("退出在最后", names[-1] == "退出 PyShot", str(names[-1]))

# 分组分隔线：6 条（截图|滚动、滚动|工具、工具|语言、语言|取消、取消|退出）
sep_count = sum(1 for t in top if t[2])
check("分隔线数量合理（6 条）", sep_count == 6, f"{sep_count} 条")
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

# ---------- 滚动子菜单（说明 + 开关 + 四种模式）----------
scroll_menu = [a.menu() for a in menu.actions() if a.menu()
               and a.text().startswith("滚动长截图")][0]
scroll_acts = [a for a in scroll_menu.actions() if not a.isSeparator()]
scroll_items = [a.text() for a in scroll_acts]
check("滚动子菜单：说明 + 开关 + 4 种模式",
      scroll_items == ["说明：实验性功能，长图可能重复、错位或拼不上",
                       "启用滚动长截图（不稳定）",
                       "自动滚轮", "拖拽滚动条", "按键翻页", "手动滚动"],
      str(scroll_items))
note_act, switch_act = scroll_acts[0], scroll_acts[1]
mode_acts = scroll_acts[2:]
check("「说明」就在开关上面一条（点不动、但看得见）",
      (not note_act.isEnabled()) and "实验" in note_act.text(), note_act.text())
check("开关下面有条分隔线（跟四种模式分开）",
      any(a.isSeparator() for a in scroll_menu.actions()))
check("每种模式都有说明",
      all(a.toolTip() for a in scroll_acts),
      str([a.toolTip() for a in scroll_acts]))
check("开关本身也带说明（讲清不稳定）",
      "实验" in switch_act.toolTip(), switch_act.toolTip())
check("子菜单打开了 tooltip 显示（否则说明看不见）",
      scroll_menu.toolTipsVisible())

# 默认关闭：开关未勾选、四种模式全部置灰（防止误点拿到坏图）
check("**滚动长截图默认关闭**（开关未勾选）",
      not switch_act.isChecked(), f"checked={switch_act.isChecked()}")
check("**开关关闭时四种模式都点不动**",
      not any(a.isEnabled() for a in mode_acts),
      str([(a.text(), a.isEnabled()) for a in mode_acts]))

# 勾上开关：四种模式要立刻可用（不能要求重启）
p._scroll_notice = lambda: True          # 测试里不弹真实模态说明框
switch_act.setChecked(True)
check("打开开关后四种模式立即可用",
      all(a.isEnabled() for a in mode_acts),
      str([(a.text(), a.isEnabled()) for a in mode_acts]))
switch_act.setChecked(False)
check("关掉开关后又都置灰",
      not any(a.isEnabled() for a in mode_acts))
check("开关状态写进了设置",
      m.get_setting(m.SCROLL_ENABLED_KEY, None) is False,
      str(m.get_setting(m.SCROLL_ENABLED_KEY, None)))

# ---------- 开启前的说明（取消就不开）----------
p2 = Probe()
p2._scroll_notice = lambda: False        # 模拟用户在说明框里点了「取消」
act2 = p2.act_scroll_enable
act2.setChecked(True)
check("说明里点取消 → 开关自动弹回未勾选", not act2.isChecked())
check("说明里点取消 → 设置保持关闭",
      m.get_setting(m.SCROLL_ENABLED_KEY, None) is False)

# ---------- 说明框的内容（讲清"不稳定"，且能记住"不再提示"）----------
class FakeCheck:
    next_state = False           # 测试设置：新建的勾选框初始是否勾上

    def __init__(self, text=""):
        self.text = text
        self._on = FakeCheck.next_state

    def isChecked(self):
        return self._on

    def setChecked(self, v):
        self._on = bool(v)


class FakeBox:
    Warning = 0
    AcceptRole = 0
    RejectRole = 1
    next_click = None            # 测试设置：说明框里"点了哪个按钮"
    last = None

    def __init__(self):
        FakeBox.last = self
        self._clicked = None
        self._accept = None
        self.info = ""

    def setWindowTitle(self, t):
        self.title = t

    def setIcon(self, i):
        pass

    def setText(self, t):
        self.text = t

    def setInformativeText(self, t):
        self.info = t

    def setCheckBox(self, cb):
        self.check = cb

    def addButton(self, text, role):
        if role == FakeBox.AcceptRole:
            self._accept = text
        return text

    def exec(self):
        self._clicked = FakeBox.next_click

    def clickedButton(self):
        return self._clicked


_orig_box, _orig_check = m.QMessageBox, m.QCheckBox
m.QMessageBox, m.QCheckBox = FakeBox, FakeCheck
try:
    i18n.set_setting(m.SCROLL_NOTICE_KEY, False)   # 让说明真的走一遍
    p3 = Probe()
    FakeBox.next_click = "取消"
    check("说明框：点取消 → 不启用", p3._scroll_notice() is False)
    info = FakeBox.last.info
    check("说明框讲清了不稳定与适用场景",
          ("实验" in FakeBox.last.text or "实验" in info) and "Citrix" in info,
          info[:60].replace("\n", " "))
    check("说明框给了「不再提示」勾选框", isinstance(FakeBox.last.check, FakeCheck))

    FakeBox.next_click = FakeBox.last._accept
    FakeCheck.next_state = True                    # 这次把「不再提示」勾上
    check("说明框：点「仍然启用」→ 可以启用", p3._scroll_notice() is True)
    check("勾了「不再提示」后记进了设置",
          m.get_setting(m.SCROLL_NOTICE_KEY, None) is True)
    FakeBox.last = None
    check("记住「不再提示」后不再弹框", p3._scroll_notice() is True
          and FakeBox.last is None)
finally:
    FakeCheck.next_state = False
    m.QMessageBox, m.QCheckBox = _orig_box, _orig_check
    i18n.set_setting(m.SCROLL_NOTICE_KEY, False)

# ---------- 兜底：没启用时直接调滚动截图要被挡住 ----------
p4 = Probe()
_notes = []
p4._notify = lambda title, msg="": _notes.append((title, msg))
p4.capture_scrolling()
check("未启用时 capture_scrolling 被挡住并给出提示",
      len(_notes) == 1 and "未启用" in _notes[0][0], str(_notes))

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
