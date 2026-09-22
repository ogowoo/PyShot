# -*- coding: utf-8 -*-
"""端到端：真实启动 winmain.py 子进程，向它投递 Win32 消息验证不崩溃。

这是**用户实际场景**的复现：在控制台 `python winmain.py`，
然后按下热键 Ctrl+Alt+X（= 系统投递 WM_HOTKEY）。

为什么要有这个测试：进程级的致命错误（Fatal Python error）无法被单元测试
捕获 —— 它会直接杀掉测试进程。所以这里另起一个进程，从外部投递消息，
再检查它的输出里有没有致命错误。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
u32 = ctypes.windll.user32
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
u32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_wchar_p, ctypes.c_wchar_p]
u32.FindWindowExW.restype = ctypes.c_void_p

WM_HOTKEY = 0x0312
WM_TRAY = 0x0400 + 512
WM_LBUTTONDBLCLK = 0x0203
HWND_MESSAGE = ctypes.c_void_p(-3)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def find_pump_window(pid):
    """消息窗口是 message-only 窗口，EnumWindows 看不到，要 FindWindowExW。"""
    child = ctypes.c_void_p(0)
    while True:
        child = u32.FindWindowExW(HWND_MESSAGE, child, None, None)
        if not child:
            return None
        wpid = wt.DWORD()
        u32.GetWindowThreadProcessId(child, ctypes.byref(wpid))
        if wpid.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(child, buf, 256)
            if buf.value.startswith("PyShotPump_"):
                return child


env = dict(os.environ, PYSHOT_SKIP_DEPS="1")
proc = subprocess.Popen([sys.executable, "winmain.py"], cwd=HERE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", env=env)
try:
    print("启动 winmain.py, pid =", proc.pid)
    time.sleep(3.0)
    check("启动后存活", proc.poll() is None,
          "" if proc.poll() is None else f"退出码 {proc.returncode}")

    hwnd = None
    deadline = time.time() + 5
    while time.time() < deadline and hwnd is None:
        hwnd = find_pump_window(proc.pid)
        if hwnd is None:
            time.sleep(0.3)
    check("找到消息窗口（托盘/热键线程已就绪）", hwnd is not None,
          hex(hwnd) if hwnd else "未找到")
    if hwnd:
        u32.PostMessageW(hwnd, WM_HOTKEY, 0xB000, 0)
        time.sleep(2.5)
        check("收到 WM_HOTKEY 后仍存活", proc.poll() is None)
        u32.PostMessageW(hwnd, WM_TRAY, 1, WM_LBUTTONDBLCLK)
        time.sleep(2.0)
        check("收到托盘双击后仍存活", proc.poll() is None)
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = proc.stdout.read() if proc.stdout else ""
    check("输出中没有致命错误", "Fatal Python error" not in out)
    if "Fatal Python error" in out:
        print(out[-1200:])

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("真实进程端到端测试通过 ✔")
