# -*- coding: utf-8 -*-
"""热键冲突自检 + 自定义热键对话框。

用户要求：
  · "自动检测冲突情况"
  · "弄个能自定义的吧"

关键认知：`RegisterHotKey` **成功不等于没冲突**。应用自己的快捷键（Outlook 的
Ctrl+Shift+F、多数软件的 Ctrl+Shift+S）只是本地快捷键，我们照样注册得上，
然后把它们"抢走" —— 用户就是这么发现 Ctrl+Shift+F 跟 Outlook 撞的。
所以检测必须分三层：语法 → 真去试注册（全局占用）→ 已知冲突表 + Alt 风险。
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

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_hkcheck_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialogButtonBox

app = QApplication([])

import style

style.apply_theme(app)

import main as m
from hotkeyui import (HotkeyDialog, sequence_from_spec,
                     spec_from_sequence)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 默认候选不再踩 Outlook ----------
check("**区域/全屏默认候选都不含 Ctrl+Shift+F（Outlook 查找）**",
      all(h != "ctrl+shift+f" for h in m.DEFAULT_HOTKEYS + m.FULLSCREEN_HOTKEYS),
      str(m.DEFAULT_HOTKEYS + m.FULLSCREEN_HOTKEYS))
check("默认首选是 PrtSc 族（应用基本不响应，不会抢别人）",
      m.DEFAULT_HOTKEYS[0] == "ctrl+printscreen"
      and m.FULLSCREEN_HOTKEYS[0] == "ctrl+shift+printscreen",
      f"{m.DEFAULT_HOTKEYS[0]} / {m.FULLSCREEN_HOTKEYS[0]}")

# ---------- 2) 检测：已知冲突（这类才是真正难发现的） ----------
r = m.check_hotkey("ctrl+shift+f")
check("Ctrl+Shift+F 被判为「有风险」并指出 Outlook",
      r["level"] == "warn" and any("Outlook" in w for w in r["warnings"]),
      str(r["warnings"]))
check("Ctrl+Shift+F 语法本身合法（不能报写法错）", r["ok"], str(r["errors"]))
r = m.check_hotkey("ctrl+shift+s")
check("Ctrl+Shift+S 提示会抢「另存为」",
      any("另存为" in w for w in r["warnings"]), str(r["warnings"]))

# ---------- 3) 检测：Alt 会关掉菜单 ----------
r = m.check_hotkey("ctrl+alt+x")
check("含 Alt 会提示截不到右键菜单",
      any("Alt" in w and "菜单" in w for w in r["warnings"]), str(r["warnings"]))

# ---------- 4) 检测：干净的组合没有警告 ----------
r = m.check_hotkey("ctrl+printscreen")
check("Ctrl+PrtSc 判为完全可用、零警告",
      r["level"] == "ok" and not r["warnings"] and not r["errors"], str(r))

# ---------- 5) 检测：语法错 / 空 / 缺修饰键 ----------
for bad in ("随便写", "", "x", "ctrl+"):
    r = m.check_hotkey(bad)
    check(f"非法组合 {bad!r} 被判为不可用", r["level"] == "bad" and r["errors"],
          str(r["errors"]))

# ---------- 6) 检测：全局占用（打桩 RegisterHotKey 返回 0） ----------
_real_windll = m.ctypes.windll


class Busy:
    def RegisterHotKey(self, *a):
        return 0

    def UnregisterHotKey(self, *a):
        return 1


m.ctypes.windll = type("W", (), {"user32": Busy()})()
try:
    r = m.check_hotkey("ctrl+shift+x")
    check("**被别的程序全局占用时判为不可用并说明原因**",
          r["level"] == "bad" and any("占用" in e for e in r["errors"]),
          str(r["errors"]))
finally:
    m.ctypes.windll = _real_windll

# ---------- 7) 检测：Windows 保留组合 ----------
r = m.check_hotkey("win+l")
check("Win+L 提示被 Windows 占用（锁屏）",
      any("锁屏" in w for w in r["warnings"]), str(r["warnings"]))

# ---------- 8) 自定义对话框 ----------
calls = []


def fake_check(spec):
    calls.append(spec)
    return m.check_hotkey(spec, probe=False)


dlg = HotkeyDialog(None, "ctrl+shift+f", fake_check,
                   ["ctrl+printscreen", "ctrl+shift+x"])
check("对话框打开时立即检测了当前键", calls and calls[0] == "ctrl+shift+f",
      str(calls[:2]))
check("当前键有冲突 → 状态是警告且说明了原因",
      dlg.result_info["level"] == "warn" and "Outlook" in dlg.details.text(),
      dlg.details.text()[:60])
ok_btn = dlg.buttons.button(QDialogButtonBox.Ok)
check("有风险时仍允许确定（用户可能就是想要那个键）", ok_btn.isEnabled())

# 换成干净的键 → 变绿
dlg.edit.setKeySequence(sequence_from_spec("ctrl+printscreen"))
check("换成 Ctrl+PrtSc 后状态变可用",
      dlg.result_info["level"] == "ok" and "可以使用" in dlg.status.text(),
      dlg.status.text())
check("spec 规范化正确（Qt 的 Ctrl+Print → ctrl+printscreen）",
      dlg.chosen_spec() == "ctrl+printscreen", dlg.chosen_spec())

# 非法键 → 确定按钮禁用
dlg.edit.setKeySequence(QKeySequence("Print"))
check("**只按了主键（没有修饰键）时确定按钮禁用**", not ok_btn.isEnabled(),
      dlg.status.text())

# 推荐按钮
dlg2 = HotkeyDialog(None, "", fake_check, ["ctrl+printscreen"])
suggest = [b for b in dlg2.findChildren(type(dlg2.btn_recheck))
           if "推荐" in b.text()]
check("有推荐值时会给出「用推荐值」按钮", len(suggest) == 1,
      str([b.text() for b in dlg2.findChildren(type(dlg2.btn_recheck))]))
if suggest:
    suggest[0].click()
    check("点推荐值后填入并检测通过",
          dlg2.chosen_spec() == "ctrl+printscreen"
          and dlg2.result_info["level"] == "ok", dlg2.chosen_spec())

# ---------- 9) QKeySequence ↔ spec 转换 ----------
check("Ctrl+Shift+X 转换正确", spec_from_sequence(QKeySequence("Ctrl+Shift+X"))
      == "ctrl+shift+x")
check("Win 键映射成 win", spec_from_sequence(QKeySequence("Meta+Shift+X"))
      == "win+shift+x")

# ---------- 10) 托盘入口 ----------
class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def setContextMenu(self, menu):
        pass

    def setToolTip(self, t):
        pass

    def show(self):
        pass


class Probe(m.PyShotApp):
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

    def _cap_log(self, *a):
        pass

    def _notify(self, t, msg):
        self._notifies.append(msg)


core = Probe()
core._build_tray_menu()
hot = [a.menu() for a in core.menu.actions()
       if a.menu() is not None and a.text() == "截图热键"][0]
labels = [a.text() for a in hot.actions() if a.text()]
check("**托盘子菜单里有「自定义…」**", "自定义…" in labels, str(labels))
check("自定义项的提示说明了会检测冲突",
      any("检测" in a.toolTip() for a in hot.actions() if a.text() == "自定义…"))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("热键冲突自检 + 自定义测试通过 ✔")
