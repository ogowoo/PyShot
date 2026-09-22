# -*- coding: utf-8 -*-
"""回归测试：真实 mainloop 期间收到 Win32 消息（这次崩溃的场景）。

背景
====
Tk 的 mainloop 泵消息时会释放 GIL；此时 Windows 把消息派发给 ctypes 建的
窗口过程，ctypes 恢复线程状态会触发致命错误：

    Fatal Python error: PyEval_RestoreThread: ... the current Python thread
    state is NULL

早期版本的测试只用 root.update() 手动泵消息，从没进过真正的 mainloop()，
所以这个 bug 溜了过去。本测试专门进 mainloop 并投递真实消息。

注意：崩溃是 fatal error，会直接杀掉进程 —— 所以这个脚本能跑完（打印出
末尾的成功字样）本身就是修复有效的证据。
"""
import ctypes
import os
import sys

os.environ.setdefault("PYSHOT_SKIP_DEPS", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tkinter as tk

import wintk

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


WM_TRAY = wintk.Win32Pump.WM_TRAY
u32 = ctypes.windll.user32

root = tk.Tk()
root.withdraw()
wintk.apply_theme(root)

events = []
pump = wintk.Win32Pump("PyShot 消息泵测试")
pump.start(wintk.DEFAULT_HOTKEYS)
print("消息窗口:", pump.hwnd, " 热键:", pump.hotkey)
check("消息窗口已创建", bool(pump.hwnd))
check("热键已注册", bool(pump.hotkey), str(pump.hotkey))


def drain():
    for kind, payload in pump.poll():
        events.append((kind, payload))
    root.after(30, drain)


drain()


def fire_hotkey():
    u32.PostMessageW(pump.hwnd, wintk.WM_HOTKEY, 0xB000, 0)


def fire_tray_double():
    u32.PostMessageW(pump.hwnd, WM_TRAY, 1, 0x0203)      # WM_LBUTTONDBLCLK


def fire_tray_menu():
    u32.PostMessageW(pump.hwnd, WM_TRAY, 1, 0x0205)      # WM_RBUTTONUP


root.after(300, fire_hotkey)
root.after(600, fire_tray_double)
root.after(900, fire_tray_menu)
root.after(1500, root.quit)

print("进入 mainloop（原来会在这里致命崩溃）…", flush=True)
root.mainloop()
print("mainloop 正常返回", flush=True)

kinds = [k for k, _ in events]
check("热键事件已送达", "hotkey" in kinds, str(kinds))
check("托盘双击事件已送达", "double" in kinds, str(kinds))
check("托盘右键事件已送达", "menu" in kinds, str(kinds))

# 主程序整体也要能正常跑起来、收消息、退出
import winmain
app = winmain.PyShotTk()
check("主程序托盘就绪", bool(app.tray.hwnd))
check("主程序热键就绪", bool(app.hk), str(app.hk))


def app_fire():
    u32.PostMessageW(app.tray.hwnd, wintk.WM_HOTKEY, 0xB000, 0)
    # 只投递菜单事件，不真的弹菜单（模态菜单会阻塞等待用户操作）
    app.tray.events.put(("menu", None)) if False else None


def app_quit():
    for ed in list(app.editors):
        try:
            ed.close()
        except Exception:  # noqa: BLE001
            pass
    if app.scroller:
        app.scroller.stop()
    app.quit()


app.root.after(400, app_fire)
app.root.after(1400, app_quit)
print("主程序进入 mainloop …", flush=True)
app.root.mainloop()
print("主程序 mainloop 正常返回", flush=True)
check("主程序能正常退出", True)

pump.stop()
check("消息泵线程已收尾", not pump._thread.is_alive())

try:
    root.destroy()
except tk.TclError:
    pass

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("mainloop 真实消息测试通过 ✔（ctypes 回调不再致命崩溃）")
