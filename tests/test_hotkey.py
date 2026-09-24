# -*- coding: utf-8 -*-
"""全局热键测试：解析、候选降级、实际注册、文案同步。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

import ctypes

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from editor import EditorWindow
from main import (DEFAULT_HOTKEYS, MOD_ALT, MOD_CONTROL, MOD_SHIFT,
                  parse_hotkey, register_global_hotkeys)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# --- 解析 ---
check("解析 ctrl+alt+x", parse_hotkey("ctrl+alt+x")[2] == "Ctrl+Alt+X")
check("修饰键位正确", parse_hotkey("ctrl+alt+x")[0] & MOD_CONTROL
      and parse_hotkey("ctrl+alt+x")[0] & MOD_ALT)
check("解析功能键", parse_hotkey("ctrl+shift+f9")[2] == "Ctrl+Shift+F9")
check("大小写/空格不敏感", parse_hotkey(" Ctrl + Alt + X ")[2] == "Ctrl+Alt+X")
check("拒绝无修饰键", parse_hotkey("x") is None)
check("拒绝无主键", parse_hotkey("ctrl+alt") is None)
check("拒绝乱写", parse_hotkey("ctrl+alt+不存在的键") is None)
check("拒绝双主键", parse_hotkey("ctrl+a+b") is None)
check("拒绝空", parse_hotkey("") is None)

# --- 默认候选不应包含系统/常用软件占用的组合 ---
joined = " ".join(DEFAULT_HOTKEYS).lower()
check("默认不含 printscreen", "printscreen" not in joined)
check("默认不含 Ctrl+Alt+A（QQ/微信）", "ctrl+alt+a" not in DEFAULT_HOTKEYS)
check("默认不含 Ctrl+Shift+A（QQ）", "ctrl+shift+a" not in DEFAULT_HOTKEYS)
check("默认不含 Alt+A（微信）", "alt+a" not in DEFAULT_HOTKEYS)
check("首选是 Ctrl+Alt+X", DEFAULT_HOTKEYS[0] == "ctrl+alt+x")

# --- 真实注册：降级逻辑（用测试专用按键，不依赖系统当前占用情况） ---
user32 = ctypes.windll.user32
# 先自己占住 Ctrl+Alt+J，模拟被别的软件抢走
TEST_KEY_VK = 0x4A          # J
taken = user32.RegisterHotKey(None, 0x7001, MOD_CONTROL | MOD_ALT | 0x4000, TEST_KEY_VK)
check("成功占位测试按键 Ctrl+Alt+J", bool(taken))
got = register_global_hotkeys(["ctrl+alt+j", "ctrl+shift+j"])
check("首选被占用时自动降级", list(got.values()) == ["Ctrl+Shift+J"], str(got))
for hid in got:
    user32.UnregisterHotKey(None, hid)
user32.UnregisterHotKey(None, 0x7001)

# 空闲时应拿到首选
got2 = register_global_hotkeys(["ctrl+alt+j"])
check("空闲时使用首选热键", list(got2.values()) == ["Ctrl+Alt+J"], str(got2))
for hid in got2:
    user32.UnregisterHotKey(None, hid)

# 单个指定（模拟 PYSHOT_HOTKEY）
got3 = register_global_hotkeys(["ctrl+alt+j"])
check("支持自定义单个热键", list(got3.values()) == ["Ctrl+Alt+J"], str(got3))
for hid in got3:
    user32.UnregisterHotKey(None, hid)

# 信息性：报告默认首选键当前是否空闲（用户可能正开着 PyShot 占着它）
probe = user32.RegisterHotKey(None, 0x7002, MOD_CONTROL | MOD_ALT | 0x4000, 0x58)
if probe:
    user32.UnregisterHotKey(None, 0x7002)
    print("提示：Ctrl+Alt+X 当前空闲")
else:
    err = ctypes.get_last_error()
    print(f"提示：Ctrl+Alt+X 已被其他程序占用（err={err}），程序会自动降级到下一个候选")

# --- 编辑器按钮提示同步 ---
app = QApplication([])
win = EditorWindow(QPixmap(200, 150))
win.set_hotkey_hint("Ctrl+Alt+X")
check("编辑器按钮提示含热键", "Ctrl+Alt+X" in win.btn_shot.toolTip())
win.set_hotkey_hint("")
check("无热键时提示不报错", "Ctrl+Alt+X" not in win.btn_shot.toolTip())

# --- 应用级：热键文本应注入托盘与编辑器 ---
from main import PyShotApp
core = PyShotApp(app)
check("应用注册到可用热键", bool(core.hotkey_text), core.hotkey_text)
check("热键不是 PrintScreen", core.hotkey_text != "PrintScreen")
if core.tray_available:
    check("托盘菜单显示热键", core.hotkey_text in core.act_region.text(),
          core.act_region.text())
    check("托盘提示显示热键", core.hotkey_text in core.tray.toolTip())
core.open_editor(QPixmap(100, 80))
check("编辑器按钮带上实际热键",
      core.hotkey_text in core.editors[0].btn_shot.toolTip())
core.shutdown()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("热键测试全部通过 ✔")
