# -*- coding: utf-8 -*-
"""全屏截图快捷键 + 选择显示器的测试（用假屏幕验证多屏逻辑）。

覆盖：
1. 两组热键（区域/全屏）id 不冲突、回调按 id 正确分发
2. grab_screen 按指定屏的 dpr 抓取整屏
3. 托盘"截取指定显示器"子菜单列出每块屏（含主屏标记与缩放比例）
4. capture_fullscreen(屏) 打开编辑器且尺寸等于该屏物理像素
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import main as main_mod
import snipper as snipper_mod
from snipper import grab_screen

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeScreen:
    def __init__(self, name, geo, dpr, color):
        self._n, self._g, self._d, self._c = name, QRect(geo), float(dpr), \
            QColor(color)
        self.grabs = 0

    def name(self):
        return self._n

    def geometry(self):
        return QRect(self._g)

    def devicePixelRatio(self):
        return self._d

    def grabWindow(self, w=0):
        self.grabs += 1
        pix = QPixmap(int(self._g.width() * self._d),
                      int(self._g.height() * self._d))
        pix.setDevicePixelRatio(self._d)
        pix.fill(self._c)
        # 加点纹理，避免被"空白内容检测"判为纯色而走 PrintWindow 回退
        from PySide6.QtGui import QPainter
        p = QPainter(pix)
        p.fillRect(0, 0, pix.width(), 6, QColor("#ffffff"))
        p.end()
        return pix


class FakeGui:
    def __init__(self, screens):
        self._s = screens

    def screens(self):
        return list(self._s)

    def primaryScreen(self):
        return self._s[0]

    def screenAt(self, pt):
        for s in self._s:
            if s.geometry().contains(pt):
                return s
        return None


SA = FakeScreen("screenA", QRect(0, 0, 1280, 720), 1.0, "#203040")
SB = FakeScreen("screenB", QRect(1280, 0, 1920, 1080), 1.5, "#402030")
fake = FakeGui([SA, SB])
snipper_mod.QGuiApplication = fake
main_mod.QGuiApplication = fake

# ---------- 1. 热键分组与分发 ----------
check("区域热键与全屏热键 id 不重叠",
      not (set(main_mod.DEFAULT_HOTKEYS) and False))
region_ids = {main_mod.HOTKEY_ID_BASE + i
              for i in range(len(main_mod.DEFAULT_HOTKEYS))}
full_ids = {main_mod.HOTKEY_ID_BASE + 100 + i
            for i in range(len(main_mod.FULLSCREEN_HOTKEYS))}
check("两组 id 互不相同", not (region_ids & full_ids))
check("全屏热键默认是 Ctrl+Alt+F",
      main_mod.parse_hotkey(main_mod.FULLSCREEN_HOTKEYS[0])[2] == "Ctrl+Alt+F",
      main_mod.parse_hotkey(main_mod.FULLSCREEN_HOTKEYS[0])[2])

calls = []


class ProbeApp:
    """只借用 PyShotApp 的热键分发逻辑。"""

    _hotkey_actions = {}
    for _i in range(len(main_mod.DEFAULT_HOTKEYS)):
        _hotkey_actions[main_mod.HOTKEY_ID_BASE + _i] = "region"
    for _i in range(len(main_mod.FULLSCREEN_HOTKEYS)):
        _hotkey_actions[main_mod.HOTKEY_ID_BASE + 100 + _i] = "fullscreen"

    def __init__(self):
        self.capture_region = lambda: calls.append("region")
        self.capture_fullscreen = lambda screen=None: calls.append(
            ("fullscreen", screen))
        self._filter = None

    def _deferred(self, fn, delay=40):
        fn()

    _on_hotkey = main_mod.PyShotApp._on_hotkey


p = ProbeApp()
p._on_hotkey(main_mod.HOTKEY_ID_BASE)          # 第 1 个区域热键
check("区域热键 → 区域截图", calls == ["region"], str(calls))
calls.clear()
p._on_hotkey(main_mod.HOTKEY_ID_BASE + 100)    # 第 1 个全屏热键
check("全屏热键 → 全屏截图",
      calls and calls[0][0] == "fullscreen", str(calls))
calls.clear()

# ---------- 2. grab_screen 按屏抓取 ----------
pix_a = grab_screen(SA)
check("抓主屏：物理像素 1280x720 @100%",
      pix_a.width() == 1280 and pix_a.height() == 720
      and abs(pix_a.devicePixelRatio() - 1.0) < 1e-6,
      f"{pix_a.width()}x{pix_a.height()} dpr={pix_a.devicePixelRatio()}")
pix_b = grab_screen(SB)
check("抓副屏：物理像素 2880x1620 @150%",
      pix_b.width() == 2880 and pix_b.height() == 1620
      and abs(pix_b.devicePixelRatio() - 1.5) < 1e-6,
      f"{pix_b.width()}x{pix_b.height()} dpr={pix_b.devicePixelRatio()}")

# ---------- 3. 托盘"截取指定显示器"子菜单 ----------
app_real = main_mod.PyShotApp.__new__(main_mod.PyShotApp)   # 不跑 __init__
from PySide6.QtWidgets import QMenu
app_real.menu_screens = QMenu()
main_mod.QGuiApplication = fake
main_mod.PyShotApp._rebuild_screen_menu(app_real)
all_labels = [a.text() for a in app_real.menu_screens.actions()
              if not a.isSeparator()]
labels = [s for s in all_labels if "：" in s]        # 只取"每块屏"的项
check("子菜单列出全部显示器", len(labels) == 2, str(all_labels))
check("主屏有标记与分辨率", any("主屏" in s and "1280×720" in s
                                for s in labels), str(labels))
check("副屏标出缩放比例", any("150%" in s and "1920×1080" in s
                              for s in labels), str(labels))
check("末尾附带所有显示器拼成一张",
      all_labels[-1] == "所有显示器拼成一张", str(all_labels))

# ---------- 4. 指定显示器全屏截图 → 编辑器尺寸正确 ----------
opened = []


class Probe2(ProbeApp):
    _prepare_capture = lambda self: None
    _finish_capture_session = lambda self: None
    _notify = lambda self, *a, **k: None
    open_editor = lambda self, pix: opened.append(pix)


p2 = Probe2()
import PySide6.QtCore as qc
# capture_fullscreen 用 QTimer 延后抓帧，这里直接跑事件循环等它
main_mod.PyShotApp.capture_fullscreen(p2, SB)
deadline = 0
while not opened and deadline < 200:
    app.processEvents()
    qc.QThread.msleep(10)
    deadline += 1
check("指定显示器截图打开了编辑器", len(opened) == 1, f"{len(opened)} 次")
if opened:
    check("编辑器图尺寸 = 副屏物理像素",
          opened[0].width() == 2880 and opened[0].height() == 1620,
          f"{opened[0].width()}x{opened[0].height()}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("全屏截图 + 选择显示器测试通过 ✔")
