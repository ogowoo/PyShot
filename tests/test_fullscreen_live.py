# -*- coding: utf-8 -*-
"""实测：真实进程里按全屏热键 Ctrl+Alt+F，确认能打开编辑器窗口。

单元测试用假屏幕验证逻辑；这里跑真进程，覆盖
「热键注册 → 真实按键 → 全屏抓屏 → 打开编辑器」整条链路。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
u32 = ctypes.windll.user32
u32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_ssize_t]
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
u32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
u32.IsWindowVisible.argtypes = [ctypes.c_void_p]

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def list_windows(pid):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, lparam):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            txt = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(hwnd, cls, 256)
            u32.GetWindowTextW(hwnd, txt, 256)
            out.append((cls.value, txt.value))
        return True

    u32.EnumWindows(cb, 0)
    return out


# -u：不要缓冲，否则拿不到"热键已注册"那行输出
proc = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=HERE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace")
try:
    time.sleep(5.0)
    if proc.poll() is not None:
        print("启动即退出:", proc.returncode)
        print(proc.stdout.read()[-800:])
        sys.exit(1)

    before = list_windows(proc.pid)
    print("启动后可见窗口:", before)

    VK_CONTROL, VK_MENU, KEYUP = 0x11, 0x12, 2
    u32.keybd_event(VK_CONTROL, 0, 0, 0)
    u32.keybd_event(VK_MENU, 0, 0, 0)
    u32.keybd_event(ord("F"), 0, 0, 0)
    time.sleep(0.05)
    u32.keybd_event(ord("F"), 0, KEYUP, 0)
    u32.keybd_event(VK_MENU, 0, KEYUP, 0)
    u32.keybd_event(VK_CONTROL, 0, KEYUP, 0)
    print("已发送 Ctrl+Alt+F")
    time.sleep(3.0)

    after = list_windows(proc.pid)
    new = [w for w in after if w not in before]
    print("按键后可见窗口:", after)
    print("新增窗口:", new)
    check("按全屏热键打开了编辑器窗口",
          any("编辑器" in t for _, t in new), str(new))
    check("进程仍然存活", proc.poll() is None)
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    out = proc.stdout.read() if proc.stdout else ""
    print("--- 程序输出 ---")
    print(out.strip()[-400:])
    check("两组热键都已注册", "区域" in out and "全屏" in out)
    check("输出里没有异常", "Fatal" not in out and "Traceback" not in out)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("全屏热键实测通过 ✔")
