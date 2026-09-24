# -*- coding: utf-8 -*-
"""通知去重测试：启动过程只应弹一条气泡（曾经"已启动"和"已就绪"各弹一条）。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from main import PyShotApp

failures = []
messages = []

# 拦截通知的唯一出口 _notify（托盘可用时会转发到 showMessage）
_real_notify = PyShotApp._notify


def spy(self, title, msg):
    messages.append((title, msg))


PyShotApp._notify = spy

# 同时确认没有任何代码绕过 _notify 直接弹气泡
_tray_calls = []
_real_show = QSystemTrayIcon.showMessage
QSystemTrayIcon.showMessage = lambda self, t, m="", *a, **k: _tray_calls.append(t)


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


app = QApplication([])

# 1) 仅构造应用（等价于启动早段）不应发任何通知
core = PyShotApp(app)
check("构造应用不发通知（避免与就绪提示重复）", len(messages) == 0,
      f"实际 {len(messages)} 条: {[m[0] for m in messages]}")

# 2) notify_ready 只发一条
messages.clear()
core.notify_ready()
check("就绪提示只有一条", len(messages) == 1,
      f"实际 {len(messages)} 条: {[m[0] for m in messages]}")
if messages:
    title, body = messages[0]
    check("就绪提示包含热键", core.hotkey_text in body)
    check("就绪提示包含退出方式", "退出" in body)
    check("就绪提示包含托盘定位提示", "∧" in body)

# 3) 热键不可用时的提示同样只有一条
messages.clear()
core._hotkey_ok = False
core.notify_ready()
check("热键不可用提示只有一条", len(messages) == 1,
      f"实际 {len(messages)} 条: {[m[0] for m in messages]}")
if messages:
    check("提示说明被占用且可自定义",
          "占用" in messages[0][1] and "PYSHOT_HOTKEY" in messages[0][1])

# 4) 其它一次性通知不应重复
messages.clear()
core._hotkey_ok = True
app.clipboard().clear()
core.pin_clipboard()
check("剪贴板无图时只提示一条", len(messages) == 1,
      f"实际 {len(messages)} 条: {[m[0] for m in messages]}")

# 5) 静态检查：主程序里只允许 _notify 内部出现一处**托盘气泡**调用
#    （编辑器状态栏的 showMessage 是另一回事，不该算进来）
import re

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"),
           encoding="utf-8").read()
count = len(re.findall(r"\btray\.showMessage\(", src))
check("主程序只有一处托盘气泡调用点（都在 _notify 内）", count == 1,
      f"实际 {count} 处")
check("确实没有别的气泡通道（QSystemTrayIcon.showMessage 只出现在 _notify 里）",
      len(re.findall(r"QSystemTrayIcon\.showMessage\(", src)) == 0,
      str(re.findall(r"QSystemTrayIcon\.showMessage\(", src)))

check("没有绕过 _notify 的气泡调用", len(_tray_calls) == 0)
core.shutdown()
PyShotApp._notify = _real_notify
QSystemTrayIcon.showMessage = _real_show

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("通知去重测试通过 ✔")
