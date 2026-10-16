# -*- coding: utf-8 -*-
"""截图热键可选 + 默认不含 Alt（截右键菜单的关键）。

用户反馈："真实情况是按下 alt 键之后菜单会消失，所以无法截到那个菜单，
可能要重新注册一个快捷键。"

原因：`RegisterHotKey` 只吃掉组合里的**最后一个键**；修饰键按下时目标窗口仍然
收得到 —— 而 **Alt 就是 Windows 的"菜单键"**，按下它会让弹出菜单立刻关闭。
所以：截右键菜单/下拉框必须用不含 Alt 的键（如 Ctrl+Shift+X、Ctrl+PrtSc）。

本文件锁住：
  · 默认首选热键不含 Alt（回归防线：改动候选表时不许把带 Alt 的排前面）
  · 可选项都能解析，前几个都是"截菜单友好"的
  · 托盘「截图热键」子菜单：可选项 + 自动选择，勾选与设置一致
  · set_hotkey()：立即生效（先注销旧的）、写进设置、编辑器提示同步、
    非法值/被占用时安全回退
  · 下次启动优先用用户选的键
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_hotkey_"))
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
    """只测热键相关的逻辑，不真注册系统热键、不建托盘图标。"""

    def __init__(self):
        self.app = app
        self.tray_available = True
        self.tray = FakeTray()
        self.editors = []
        self.hotkey_text = ""
        self.full_hotkey_text = ""
        self._region_hotkeys = {}
        self._hotkeys = {}
        self._hotkey_actions = {}
        self._filter = None
        self._hotkey_actions_ui = []
        self._delay_actions = []
        self._notifies = []
        self._logs = []

    def _cap_log(self, *a):
        self._logs.append(a)

    def _notify(self, title, msg):
        self._notifies.append((title, msg))


# ---------- 1) 默认首选不含 Alt（这条是整个修复的核心） ----------
check("**默认首选热键不含 Alt**", "alt" not in m.DEFAULT_HOTKEYS[0],
      m.DEFAULT_HOTKEYS[0])
check("全屏首选也不含 Alt", "alt" not in m.FULLSCREEN_HOTKEYS[0],
      m.FULLSCREEN_HOTKEYS[0])
check("候选表里仍然保留了带 Alt 的备选（被占用时还有得用）",
      any("alt" in h for h in m.DEFAULT_HOTKEYS), str(m.DEFAULT_HOTKEYS))

# ---------- 2) 可选项都能解析，且前几个截菜单友好 ----------
bad = [h for h in m.HOTKEY_CHOICES if m.parse_hotkey(h) is None]
check("所有可选项都能解析", not bad, str(bad))
check("**前三个可选项都不含 Alt**",
      all("alt" not in h for h in m.HOTKEY_CHOICES[:3]),
      str(m.HOTKEY_CHOICES[:3]))
check("可选项里有 Ctrl+PrtSc（应用不会响应 PrtSc，截菜单最稳）",
      "ctrl+printscreen" in m.HOTKEY_CHOICES)
check("PrtSc 显示名是通用的 PrtSc",
      m.parse_hotkey("ctrl+printscreen")[2] == "Ctrl+PrtSc",
      m.parse_hotkey("ctrl+printscreen")[2])

# ---------- 3) 托盘子菜单 ----------
core = Probe()
core._build_tray_menu()
hot_menu = [a.menu() for a in core.menu.actions()
            if a.menu() is not None and a.text() == "截图热键"]
check("托盘菜单里有「截图热键」子菜单", len(hot_menu) == 1)
labels = [a.text() for a in hot_menu[0].actions()] if hot_menu else []
picks = [a for a in hot_menu[0].actions()
         if a.isCheckable()] if hot_menu else []
check("子菜单含全部可选项 + 自动选择",
      len([x for x in labels if x]) == len(m.HOTKEY_CHOICES) + 1
      and labels[-1] == "自动选择（推荐）",
      str(labels))
check("选项标签是规范的热键名（不是 ctrl+shift+x 这种）",
      labels[0] == "Ctrl+Shift+X（截菜单友好）", labels[0] if labels else "")
check("**带 Alt 的选项标注了「会失败」**",
      any("Alt" in t and "失败" in t for t in labels), str(labels))
check("默认勾的是「自动选择」",
      [a.isChecked() for a in picks] == [False] * len(m.HOTKEY_CHOICES) + [True],
      str([a.isChecked() for a in picks]))

# ---------- 4) set_hotkey：立即生效（先注销旧的）+ 写设置 + 勾选同步 ----------
unregistered = []
registered = []


class FakeUser32:
    def UnregisterHotKey(self, hwnd, hid):
        unregistered.append(hid)
        return 1

    def RegisterHotKey(self, hwnd, hid, mods, vk):
        registered.append((hid, mods, vk))
        return 1


import ctypes

_real_windll = ctypes.windll


class FakeWindll:
    user32 = FakeUser32()


ctypes.windll = FakeWindll()
try:
    core._region_hotkeys = {m.HOTKEY_ID_BASE: "Ctrl+Shift+X"}
    core._hotkey_actions = {m.HOTKEY_ID_BASE: "region"}
    ok = core.set_hotkey("ctrl+shift+s")
    check("set_hotkey 注册成功", ok)
    check("**换键前先注销了旧热键**", unregistered == [m.HOTKEY_ID_BASE],
          str(unregistered))
    check("注册的就是新键（Ctrl+Shift+S = 0x53）",
          registered and registered[-1][2] == ord("S"), str(registered))
    check("hotkey_text 更新为新键", core.hotkey_text == "Ctrl+Shift+S",
          core.hotkey_text)
    check("设置里记下了新键", m.saved_hotkey() == "ctrl+shift+s",
          m.saved_hotkey())
    check("托盘勾选跟着走",
          [a.isChecked() for a in picks]
          == [False, True, False, False, False, False, False],
          str([a.isChecked() for a in picks]))
    check("给了提示且提到 Alt 的坑",
          core._notifies and "Alt" in core._notifies[-1][1],
          str(core._notifies[-1:] if core._notifies else None))

    # ---------- 5) 非法值 → 安全回退到"自动选择" ----------
    registered.clear()
    core.set_hotkey("这不是热键")
    check("非法值不写进设置（清空 = 自动选择）", m.saved_hotkey() == "",
          m.saved_hotkey())
    check("非法值回退到候选表注册", bool(core._region_hotkeys))

    # ---------- 6) 被占用 → 回退到候选表，不能没键可用 ----------
    registered.clear()

    class BusyUser32(FakeUser32):
        def RegisterHotKey(self, hwnd, hid, mods, vk):
            registered.append((hid, mods, vk))
            return 0 if vk == ord("S") else 1

    ctypes.windll = type("W", (), {"user32": BusyUser32()})()
    core.set_hotkey("ctrl+shift+s")
    check("**被占用时回退到候选表（仍有热键可用）**",
          bool(core._region_hotkeys) and core.hotkey_text != "",
          core.hotkey_text)
finally:
    ctypes.windll = _real_windll

# ---------- 7) 下次启动优先用用户选的键 ----------
i18n.set_setting(m.HOTKEY_SETTING, "ctrl+printscreen")
seen = {}


def fake_register(cands, offset=0):
    seen.setdefault(offset, list(cands))
    return {m.HOTKEY_ID_BASE + offset: m.parse_hotkey(cands[0])[2]}


_real_register = m.register_global_hotkeys
m.register_global_hotkeys = fake_register
try:
    core2 = Probe()
    core2._init_hotkey()
finally:
    m.register_global_hotkeys = _real_register
check("**启动时优先注册用户选的键**",
      seen.get(0, [""])[0] == "ctrl+printscreen", str(seen.get(0)))
check("用户选的键后面跟着候选表（选键失效也能兜住）",
      len(seen.get(0, [])) > 1, str(seen.get(0)))

# ---------- 8) 编辑器提示同步 ----------
from editor import EditorWindow

win = EditorWindow(QPixmap(120, 90))
core.editors = [win]
core.set_hotkey("ctrl+shift+x", quiet=True)
check("换键后编辑器里的热键提示同步更新",
      win.hotkey_hint == "Ctrl+Shift+X", win.hotkey_hint)

# ---------- 9) 帮助里写明了 Alt 这个坑 ----------
import help_text as ht

blob = " ".join(line for _t, lines in ht.SECTIONS for line in lines)
check("帮助里解释了 Alt 会让菜单消失", "Alt" in blob and "菜单" in blob)
check("帮助/界面文案三语齐全",
      all(i18n.TABLE.get(k) and i18n.TABLE[k][0] and i18n.TABLE[k][1]
          for k in ("截图热键", "自动选择（推荐）",
                    "截右键菜单请选不带 Alt 的键：Alt 会让菜单消失",
                    "{}（截菜单友好）", "{}（含 Alt，截菜单会失败）")),
      "")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("截图热键可选测试通过 ✔")
