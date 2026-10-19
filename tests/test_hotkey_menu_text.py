# -*- coding: utf-8 -*-
"""换热键后，所有显示热键的地方都要跟着变。

用户反馈："菜单的快捷键提示不会随着我改变的快捷键变更显示。"

根因：菜单项右侧的快捷键提示（`区域截图\tCtrl+PrtSc`）、托盘 tooltip、
「截图热键」两个子菜单的标题，都是**在 _build_tray_menu 里一次性写死**的，
set_hotkey 只改了内部状态，没人去刷新这些文案。

修法：抽出 _refresh_hotkey_texts()，建菜单时调用一次、每次换键后再调用一次。
（不重建整个菜单：换键时菜单可能正开着，重建会把 action 删掉。）
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_stale_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtWidgets import QApplication

app = QApplication([])

import style

style.apply_theme(app)

import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def __init__(self):
        self.tip = ""
        self.menu = None

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, t):
        self.tip = t

    def show(self):
        pass

    def showMessage(self, *a):
        pass


class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.tray_available = True
        self.tray = FakeTray()
        self.editors = []
        self.hotkey_text = "Ctrl+PrtSc"
        self.full_hotkey_text = "Ctrl+Shift+PrtSc"
        self._region_hotkeys = {m.HOTKEY_ID_BASE: "Ctrl+PrtSc"}
        self._full_hotkeys = {m.HOTKEY_ID_BASE + 100: "Ctrl+Shift+PrtSc"}
        self._hotkeys = {**self._region_hotkeys, **self._full_hotkeys}
        self._hotkey_ok = True
        self._hotkey_actions = {m.HOTKEY_ID_BASE: "region",
                                m.HOTKEY_ID_BASE + 100: "fullscreen"}
        self._filter = None
        self._hotkey_actions_ui = []
        self._hotkey_submenus = {}
        self._delay_actions = []
        self._notifies = []
        self._logs = []

    def _cap_log(self, *a):
        self._logs.append(a)

    def _notify(self, t, msg):
        self._notifies.append(msg)


class FakeUser32:
    def UnregisterHotKey(self, *a):
        return 1

    def RegisterHotKey(self, *a):
        return 1


import ctypes

_real_windll = ctypes.windll
ctypes.windll = type("W", (), {"user32": FakeUser32()})()


def region_text(core):
    return core.act_region.text()


def full_text(core):
    return core.act_full.text()


def sub_titles(core):
    return {w: s.title() for w, s in core._hotkey_submenus.items()}


try:
    # ---------- 1) 建菜单时就有正确文案 ----------
    core = Probe()
    core._build_tray_menu()
    check("**菜单项右侧显示当前热键**",
          region_text(core).endswith("\tCtrl+PrtSc")
          and "区域截图" in region_text(core), repr(region_text(core)))
    check("全屏菜单项也带热键",
          full_text(core).endswith("\tCtrl+Shift+PrtSc"), repr(full_text(core)))
    check("托盘 tooltip 里有两个热键",
          "Ctrl+PrtSc" in core.tray.tip and "Ctrl+Shift+PrtSc" in core.tray.tip,
          core.tray.tip)
    check("子菜单标题带当前热键",
          "Ctrl+PrtSc" in sub_titles(core)["region"]
          and "Ctrl+Shift+PrtSc" in sub_titles(core)["full"],
          str(sub_titles(core)))

    # ---------- 2) 换区域热键 → 三处文案全部刷新 ----------
    old = region_text(core)
    core.set_hotkey("ctrl+shift+f9", "region", quiet=True)
    new = region_text(core)
    check("**换键后菜单项右侧提示变了**", new != old and "Ctrl+Shift+F9" in new,
          repr(new))
    check("菜单项里不再出现旧热键", "Ctrl+PrtSc" not in new, repr(new))
    check("**换键后子菜单标题也变了**",
          "Ctrl+Shift+F9" in sub_titles(core)["region"],
          str(sub_titles(core)))
    check("**换键后托盘 tooltip 也变了**",
          "Ctrl+Shift+F9" in core.tray.tip and "Ctrl+PrtSc" not in core.tray.tip,
          core.tray.tip)
    check("换区域键不影响全屏那条文案",
          full_text(core).endswith("\tCtrl+Shift+PrtSc"), repr(full_text(core)))

    # ---------- 3) 换全屏热键 → 只变全屏那几处 ----------
    core.set_hotkey("ctrl+shift+f7", "full", quiet=True)
    check("**换全屏键后全屏菜单项变了**",
          "Ctrl+Shift+F7" in full_text(core)
          and "Ctrl+Shift+PrtSc" not in full_text(core), repr(full_text(core)))
    check("全屏子菜单标题跟着变",
          "Ctrl+Shift+F7" in sub_titles(core)["full"], str(sub_titles(core)))
    check("tooltip 里全屏键更新了",
          "Ctrl+Shift+F7" in core.tray.tip, core.tray.tip)
    check("区域那条文案没被牵连",
          "Ctrl+Shift+F9" in region_text(core), repr(region_text(core)))

    # ---------- 4) 恢复自动选择：文案回到实际生效的键 ----------
    core._region_hotkeys = {m.HOTKEY_ID_BASE: "Ctrl+PrtSc"}
    core.set_hotkey("", "region", quiet=True)
    check("恢复自动选择后文案是实际注册到的那把键",
          "自动" not in region_text(core) and region_text(core).strip() != "",
          repr(region_text(core)))

    # ---------- 5) 重复刷新是幂等的（菜单开着时会被反复调） ----------
    core._refresh_hotkey_texts()
    core._refresh_hotkey_texts()
    check("连续刷新文案稳定", "Ctrl+Shift+F9" in region_text(core)
          or region_text(core).strip() != "", repr(region_text(core)))
finally:
    ctypes.windll = _real_windll

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("热键文案同步测试通过 ✔")
