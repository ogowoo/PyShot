# -*- coding: utf-8 -*-
"""托盘图标生命周期测试。

为什么单独测：托盘图标"有没有真的显示"只有 `show()` 被调用才知道。
早先有一个 bug —— 拆分 `_init_tray` / `_build_tray_menu` 时把
`show()` 和 `activated.connect` 一起从初始化里删掉了，托盘菜单本身正常，
但图标根本不显示（用户表现为"托盘图标没了"）。用假托盘记录调用即可拦住。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)


class FakeTray:
    """记录 show()/hide()/setContextMenu()/activated.connect()。"""

    def __init__(self, icon, parent):
        self.icon = icon
        self.shown = 0
        self.hidden = 0
        self.activated = FakeSignal()
        self.menus = []

    def setContextMenu(self, menu):
        self.menus.append(menu)

    def setToolTip(self, t):
        self.tip = t

    def show(self):
        self.shown += 1

    def hide(self):
        self.hidden += 1


class FakeScreen:
    def __init__(self, n, g, d):
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


# 用假托盘接管 QSystemTrayIcon
real_tray_cls = m.QSystemTrayIcon
created = []


class RecordingTray(FakeTray):
    def __init__(self, icon, parent):
        super().__init__(icon, parent)
        created.append(self)


m.QSystemTrayIcon = RecordingTray
m.QGuiApplication = FakeGui()


class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.editors = []


p = Probe()
p._init_tray()

check("初始化后创建了托盘图标", len(created) == 1, f"{len(created)} 个")
tray = created[0]
check("托盘图标被 show()（否则图标不显示）", tray.shown == 1, f"show {tray.shown} 次")
check("托盘图标连接了 activated 信号", len(tray.activated.slots) == 1,
      f"{len(tray.activated.slots)} 个槽")
check("托盘图标有菜单", len(tray.menus) == 1)
check("托盘图标有悬停提示", getattr(tray, "tip", ""), tray.tip)

# 关键：重建菜单（切换语言时会发生）不应重复 show / 重复连接信号
p._build_tray_menu()
p._build_tray_menu()
check("重建菜单不会重复 show()", tray.shown == 1, f"show {tray.shown} 次")
check("重建菜单不会重复连接 activated", len(tray.activated.slots) == 1,
      f"{len(tray.activated.slots)} 个槽")
check("重建菜单会更新菜单对象", len(tray.menus) == 3, f"{len(tray.menus)} 个")
check("重建后菜单里有语言子菜单",
      any(a.menu() is not None and a.text() == "语言"
          for a in tray.menus[-1].actions()),
      str([a.text() for a in tray.menus[-1].actions()]))

# 切换语言走的是同一路径：不能重复 show、不能重复连接
from i18n import set_language
set_language("en", persist=False)
p._retranslate()
set_language("zh_CN", persist=False)
p._retranslate()
check("切换语言两次后 show() 仍然只有一次", tray.shown == 1, f"show {tray.shown} 次")
check("切换语言后 activated 仍然只连一次",
      len(tray.activated.slots) == 1, f"{len(tray.activated.slots)} 个槽")

m.QSystemTrayIcon = real_tray_cls

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("托盘图标生命周期测试通过 ✔")
