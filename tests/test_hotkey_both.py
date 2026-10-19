# -*- coding: utf-8 -*-
"""区域截图与全屏截图的热键**都能自定义**（含冲突自检、两组不能撞车）。

用户要求："全屏和选区都要可以自定义"。

设计要点：
  · 两组各自独立：设置键、候选表、注册 id 段（0 / 100）、托盘子菜单
  · **同一个组合不能同时绑两个动作**（注册必然失败）→ set_hotkey 里直接拒绝，
    并说明"已经是另一组的热键了"
  · 换键立即生效：只注销这一组、只重注册这一组，另一组原样不动
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

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_hkboth_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtGui import QPixmap
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

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, t):
        pass

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
        self._delay_actions = []
        self._notifies = []
        self._logs = []

    def _cap_log(self, *a):
        self._logs.append(a)

    def _notify(self, t, msg):
        self._notifies.append(msg)


# ---------- 1) 两组候选表都非空、互不重叠 ----------
check("区域候选表非空且首选是 PrtSc 族",
      m.HOTKEY_CHOICES and "printscreen" in m.HOTKEY_CHOICES[0],
      str(m.HOTKEY_CHOICES[:2]))
check("**全屏候选表非空且首选是 PrtSc 族**",
      m.FULLSCREEN_CHOICES and "printscreen" in m.FULLSCREEN_CHOICES[0],
      str(m.FULLSCREEN_CHOICES[:2]))
check("**两组候选不重叠**（一个组合只能绑一个动作）",
      not (set(m.HOTKEY_CHOICES) & set(m.FULLSCREEN_CHOICES)),
      str(set(m.HOTKEY_CHOICES) & set(m.FULLSCREEN_CHOICES)))

# ---------- 2) 托盘子菜单：两组各自一节 ----------
core = Probe()
core._build_tray_menu()
hot = [a.menu() for a in core.menu.actions()
       if a.menu() is not None and a.text() == "截图热键"][0]
subs = {a.text().split(" — ")[0]: a.menu() for a in hot.actions()
        if a.menu() is not None}
check("**「截图热键」下分出「区域截图（选区）」与「全屏截图」两节**",
      list(subs) == ["区域截图（选区）", "全屏截图"], str(list(subs)))
for title, choices in (("区域截图（选区）", m.HOTKEY_CHOICES),
                       ("全屏截图", m.FULLSCREEN_CHOICES)):
    labels = [a.text() for a in subs[title].actions() if a.text()]
    check(f"{title} 有全部候选 + 自定义 + 自动选择",
          len(labels) == len(choices) + 2 and "自定义…" in labels
          and labels[-1] == "自动选择（推荐）", str(labels))
    check(f"{title} 当前生效的键被勾上",
          sum(1 for a in subs[title].actions() if a.isCheckable()
              and a.isChecked()) == 1,
          str([a.text() for a in subs[title].actions()
               if a.isCheckable() and a.isChecked()]))

# ---------- 3) set_hotkey(which="full") 只动全屏那组 ----------
unreg, reg = [], []


class FakeUser32:
    def UnregisterHotKey(self, hwnd, hid):
        unreg.append(hid)
        return 1

    def RegisterHotKey(self, hwnd, hid, mods, vk):
        reg.append((hid, vk))
        return 1


import ctypes

_real = ctypes.windll
ctypes.windll = type("W", (), {"user32": FakeUser32()})()
try:
    region_before = dict(core._region_hotkeys)
    ok = core.set_hotkey("ctrl+shift+f7", "full")
    check("**全屏热键可以自定义**", ok and core.full_hotkey_text == "Ctrl+Shift+F7",
          core.full_hotkey_text)
    check("换全屏键时只注销了全屏那组的 id（区域那组没动）",
          unreg == [m.HOTKEY_ID_BASE + 100], str(unreg))
    check("注册时用的是全屏 id 段（+100）",
          reg and reg[-1][0] == m.HOTKEY_ID_BASE + 100, str(reg))
    check("区域热键保持原样", core._region_hotkeys == region_before,
          str(core._region_hotkeys))
    check("setting 分开存：全屏写进了 full 的键",
          m.saved_hotkey("full") == "ctrl+shift+f7" and m.saved_hotkey() == "",
          f"{m.saved_hotkey('full')!r} / {m.saved_hotkey()!r}")
    check("动作映射也跟着更新",
          core._hotkey_actions.get(m.HOTKEY_ID_BASE + 100) == "fullscreen"
          and core._hotkey_actions.get(m.HOTKEY_ID_BASE) == "region",
          str(core._hotkey_actions))

    # ---------- 4) 两组撞车 → 拒绝 ----------
    core._notifies.clear()
    ok = core.set_hotkey("ctrl+prtsc" if False else "ctrl+printscreen", "full")
    check("**把全屏设成区域正在用的键 → 拒绝并说明原因**",
          ok is False and core._notifies
          and "区域截图" in core._notifies[-1], str(core._notifies[-1:]))
    check("拒绝后全屏热键没变", core.full_hotkey_text == "Ctrl+Shift+F7",
          core.full_hotkey_text)

    # ---------- 5) 区域那组同样能自定义 ----------
    unreg.clear()
    ok = core.set_hotkey("ctrl+shift+s", "region")
    check("区域热键可以自定义", ok and core.hotkey_text == "Ctrl+Shift+S",
          core.hotkey_text)
    check("换区域键只注销区域那组的 id", unreg == [m.HOTKEY_ID_BASE], str(unreg))
    check("换区域键不动全屏热键", core.full_hotkey_text == "Ctrl+Shift+F7",
          core.full_hotkey_text)
finally:
    ctypes.windll = _real

# ---------- 6) 编辑器里的两条提示都同步 ----------
from editor import EditorWindow

win = EditorWindow(QPixmap(120, 90))
core.editors = [win]
core.set_hotkey("ctrl+printscreen", "region", quiet=True)
core.set_hotkey("ctrl+alt+printscreen", "full", quiet=True)
check("编辑器拿到的是两组各自的热键",
      win.hotkey_hint == "Ctrl+PrtSc" and win.full_hotkey_hint == "Ctrl+Alt+PrtSc",
      f"{win.hotkey_hint} / {win.full_hotkey_hint}")

# ---------- 7) 启动时两组各自读设置 ----------
seen = {}


def fake_register(cands, offset=0):
    seen[offset] = list(cands)
    return {m.HOTKEY_ID_BASE + offset: m.parse_hotkey(cands[0])[2]}


i18n.set_setting(m.HOTKEY_SETTING, "ctrl+shift+f9")
i18n.set_setting(m.HOTKEY_SETTING_FULL, "ctrl+shift+f10")
_real_register = m.register_global_hotkeys
m.register_global_hotkeys = fake_register
try:
    core2 = Probe()
    core2._init_hotkey()
finally:
    m.register_global_hotkeys = _real_register
check("**启动时区域热键用区域自己的设置**",
      seen.get(0, [""])[0] == "ctrl+shift+f9", str(seen.get(0)))
check("**启动时全屏热键用全屏自己的设置**",
      seen.get(100, [""])[0] == "ctrl+shift+f10", str(seen.get(100)))

# ---------- 8) 两个设置键不同（别写成同一个） ----------
check("区域/全屏的设置键不同",
      m.HOTKEY_SETTING != m.HOTKEY_SETTING_FULL,
      f"{m.HOTKEY_SETTING} / {m.HOTKEY_SETTING_FULL}")

# ---------- 9) 检测：已知冲突对两组都适用 ----------
r = m.check_hotkey("ctrl+shift+f")
check("全屏若选 Ctrl+Shift+F 也会报 Outlook 冲突",
      any("Outlook" in w for w in r["warnings"]), str(r["warnings"]))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("区域/全屏热键都能自定义：测试通过 ✔")
