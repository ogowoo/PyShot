# -*- coding: utf-8 -*-
"""wintk.py —— Tkinter 界面框架（主题、图标、托盘、全屏覆盖层基类）。"""
import ctypes
import ctypes.wintypes as wt
import tkinter as tk
from tkinter import ttk

import winimg as wi

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
shell = ctypes.windll.shell32

# ---- Win32 句柄/指针声明（x64 下不声明会被截断成 32 位，导致创建窗口失败） ----
k32.GetModuleHandleW.restype = ctypes.c_void_p
k32.GetModuleHandleW.argtypes = [ctypes.c_void_p]
u32.CreateWindowExW.restype = ctypes.c_void_p
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_void_p]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
u32.DefWindowProcW.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.c_ssize_t,
                               ctypes.c_ssize_t]
u32.RegisterClassW.argtypes = [ctypes.c_void_p]
u32.DestroyWindow.argtypes = [ctypes.c_void_p]
u32.DestroyIcon.argtypes = [ctypes.c_void_p]
u32.CreateIconIndirect.restype = ctypes.c_void_p
u32.CreateIconIndirect.argtypes = [ctypes.c_void_p]
shell.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.c_void_p]
shell.Shell_NotifyIconW.restype = wt.BOOL

# ---------------------------------------------------------------- 主题令牌

BG = "#17181c"
SURFACE = "#1f2126"
SURFACE_2 = "#26292f"
BORDER = "#2c2f36"
BORDER_STRONG = "#3a3e47"
TEXT = "#e6e8ec"
TEXT_DIM = "#a2a8b2"
ACCENT = "#4c9aff"
ACCENT_HOVER = "#66adff"
ACCENT_ACTIVE = "#2f7fe0"
ACCENT_SOFT = "#2a3b52"
DANGER = "#ff5c5c"
FONT_UI = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)


def apply_theme(root: tk.Tk):
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=TEXT,
                    fieldbackground=SURFACE_2, bordercolor=BORDER,
                    font=FONT_UI)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Dim.TLabel", background=BG, foreground=TEXT_DIM)
    style.configure("TButton", background=SURFACE_2, foreground=TEXT,
                    borderwidth=0, focusthickness=0, padding=(10, 5))
    style.map("TButton",
              background=[("active", BORDER_STRONG), ("pressed", ACCENT_SOFT)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
    style.map("Accent.TButton",
              background=[("active", ACCENT_HOVER), ("pressed", ACCENT_ACTIVE)])
    style.configure("TSpinbox", fieldbackground=SURFACE_2, foreground=TEXT,
                    arrowcolor=TEXT, bordercolor=BORDER, padding=(4, 2))
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=SURFACE, foreground=TEXT_DIM,
                    padding=(12, 5), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", TEXT)])
    style.configure("Horizontal.TScale", background=ACCENT,
                    troughcolor=BORDER, borderwidth=0)


def top_bar_button(parent, text, command=None, accent=False, tooltip=None):
    """顶栏按钮（扁平、悬浮高亮）。"""
    bg = ACCENT if accent else SURFACE_2
    fg = "#ffffff" if accent else TEXT
    hover = ACCENT_HOVER if accent else BORDER_STRONG
    btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                    bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                    font=FONT_UI, padx=12, pady=4, cursor="hand2",
                    highlightthickness=0)
    if tooltip:
        attach_tooltip(btn, tooltip)
    return btn


_tooltips = {}


def attach_tooltip(widget, text: str):
    tip = _Tooltip(widget, text)


class _Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, e=None):
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        self.tw.configure(bg=SURFACE_2)
        lab = tk.Label(self.tw, text=self.text, justify="left", bg=SURFACE_2,
                       fg=TEXT, font=FONT_SMALL, padx=8, pady=5,
                       highlightthickness=1, highlightbackground=BORDER_STRONG)
        lab.pack()

    def _hide(self, e=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None


# ---------------------------------------------------------------- 图标（沿用现有矢量图标）

_icon_drawers = {}


def register_icon(name, fn):
    _icon_drawers[name] = fn


def make_icon_image(name: str, color=(230, 57, 53), size: int = 22) -> wi.Image:
    """把矢量图标画成一张 Image（透明底）。"""
    img = wi.Image(size, size)
    img.data = bytearray(size * size * 4)      # 全透明
    r = img.renderer()
    fn = _icon_drawers[name]
    # 图标绘制函数约定：在 22x22 区域内，线条宽约 1.8，颜色为 color
    r.use_pen(color, 1.8)
    fn(r, color)
    r.close()
    return img


def make_icon_photo(name: str, color=(230, 57, 53), size: int = 22):
    return tk.PhotoImage(data=make_icon_image(name, color, size).photo_bytes())


# 由 winshapes / wineditor 注册图标；这里先内置几个基础图标
def _d_select(r, c):
    r.polygon([(6, 3), (6, 16), (10, 12), (12, 18), (15, 16), (13, 11),
               (18, 11)], c, 1.8, fill=True)


def _d_rect(r, c):
    r.rect(4, 6, 14, 10, c, 1.8)


def _d_ellipse(r, c):
    r.ellipse(4, 6, 14, 10, c, 1.8)


def _d_line(r, c):
    r.line(4, 18, 18, 4, c, 1.8)


def _d_arrow(r, c):
    r.line(4, 18, 16, 6, c, 1.8)
    r.line(16, 6, 9, 6.5, c, 1.8)
    r.line(16, 6, 15.5, 12, c, 1.8)


def _d_step(r, c):
    r.ellipse(3, 3, 16, 16, c, 1.8, fill=True)
    r.use_pen((255, 255, 255), 1.0)
    r.text_center(3, 3, 16, 16, "1", (255, 255, 255), size_px=11, bold=True)


def _d_text(r, c):
    r.text_center(3, 2, 16, 19, "T", c, size_px=16, bold=True)


def _d_highlight(r, c):
    r.rect(3, 9, 16, 7, c, 1.6, fill=True)


def _d_mosaic(r, c):
    s = 4.5
    for i in range(3):
        for j in range(3):
            if (i + j) % 2 == 0:
                r.rect(int(3.5 + j * (s + 1)), int(3.5 + i * (s + 1)),
                       int(s), int(s), c, 0, fill=True)


def _d_pick(r, c):
    r.line(4.5, 17.5, 12.5, 9.5, c, 1.8)
    r.rect(11.5, 3, 7, 7, c, 1.6)
    r.ellipse(3.5, 17.5, 2.5, 2.5, c, 1.5, fill=True)


def _d_crop(r, c):
    for x1, y1, x2, y2, x3, y3 in [(5, 10, 5, 5, 10, 5),
                                   (12, 5, 17, 5, 17, 10),
                                   (17, 12, 17, 17, 12, 17),
                                   (10, 17, 5, 17, 5, 12)]:
        r.line(x1, y1, x2, y2, c, 1.8)
        r.line(x2, y2, x3, y3, c, 1.8)


def _d_pen(r, c):
    # 折线画笔
    pts = [(4, 18), (7, 12), (9, 14), (11, 10), (13, 12), (15, 8), (18, 4)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        r.line(x1, y1, x2, y2, c, 1.8)


def _d_camera(r, c):
    r.rect(3, 8, 16, 11, c, 1.8)
    r.rect(8, 4.5, 6, 4, c, 1.8)
    r.ellipse(8.5, 10.5, 5, 5, c, 1.8)


def _d_undo(r, c):
    # 左向弧线箭头（用折线近似）
    pts = [(18, 8), (13, 4), (8, 5), (4, 9), (5, 14), (9, 18), (13, 17)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        r.line(x1, y1, x2, y2, c, 1.8)
    r.line(18, 8, 18, 4, c, 1.8)
    r.line(18, 8, 14, 8, c, 1.8)


def _d_redo(r, c):
    pts = [(4, 8), (9, 4), (14, 5), (18, 9), (17, 14), (13, 18), (9, 17)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        r.line(x1, y1, x2, y2, c, 1.8)
    r.line(4, 8, 4, 4, c, 1.8)
    r.line(4, 8, 8, 8, c, 1.8)


for _n, _f in [("select", _d_select), ("rect", _d_rect), ("ellipse", _d_ellipse),
               ("line", _d_line), ("arrow", _d_arrow), ("pen", _d_pen),
               ("step", _d_step), ("text", _d_text), ("highlight", _d_highlight),
               ("mosaic", _d_mosaic), ("pick", _d_pick), ("crop", _d_crop),
               ("camera", _d_camera), ("undo", _d_undo), ("redo", _d_redo)]:
    register_icon(_n, _f)


# ---------------------------------------------------------------- 托盘图标

NOTIFYICON_VERSION = 0x4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
WM_USER = 0x0400
WM_TRAY = WM_USER + 512
WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0203, 0x0205
MF_STRING, MF_SEPARATOR, MF_RIGHTJUSTIFY = 0, 0x800, 0x100
TPM_BOTTOMALIGN, TPM_LEFTALIGN = 0x0020, 0x0
TPM_LEFTBUTTON, TPM_RIGHTBUTTON = 0x0, 0x2
IDM_EXIT = 9999


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                ("hIcon", wt.HANDLE), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
                ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", wi.CLSID), ("hBalloonIcon", wt.HANDLE)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HANDLE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class TrayIcon:
    """系统托盘图标（纯 ctypes Shell_NotifyIcon + 隐藏消息窗口）。

    回调事件通过 on_event(event) 派发：'double' 双击, 'menu' 右键。
    需要在创建后调用 show()，结束时调用 destroy()。
    """

    _next_id = 0x5001
    WNDPROC = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT,
                                 wt.WPARAM, wt.LPARAM)

    def __init__(self, tk_root: tk.Tk, on_event, tooltip: str = "PyShot"):
        self.on_event = on_event
        self.tk_root = tk_root
        self.id = TrayIcon._next_id
        TrayIcon._next_id += 1
        self.hwnd = self._create_message_window()
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = self.id
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAY
        self.nid.hIcon = self._make_icon()
        self.nid.szTip = tooltip

    def _make_icon(self):
        # 相机图标（蓝底白圈）→ HBITMAP → HICON
        img = wi.Image(32, 32)
        r = img.renderer()
        r.rect(0, 0, 32, 32, (76, 154, 255), 0, fill=True, round_=10)
        r.rect(6, 11, 20, 13, (255, 255, 255), 1.5, fill=True)
        r.rect(12, 7, 8, 5, (255, 255, 255), 1.5, fill=True)
        r.ellipse(12, 13, 8, 8, (76, 154, 255), 1.5, fill=True)
        r.ellipse(14.5, 15.5, 3, 3, (255, 255, 255), 1.5, fill=True)
        r.close()

        hdc = u32.GetDC(0)
        memdc = wi.g32.CreateCompatibleDC(hdc)
        color_bmp = wi.g32.CreateCompatibleBitmap(hdc, 32, 32)
        wi.g32.SelectObject(memdc, color_bmp)
        tmp = ctypes.create_string_buffer(bytes(img.data), len(img.data))
        info = wi._bmi(32, 32)
        wi.g32.SetDIBits(memdc, color_bmp, 0, 32, tmp, ctypes.byref(info), 0)
        wi.g32.DeleteDC(memdc)
        u32.ReleaseDC(0, hdc)
        # 掩码位图（全不透明）
        mask_bmp = wi.g32.CreateBitmap(32, 32, 1, 1, None)

        class ICONINFO(ctypes.Structure):
            _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD),
                        ("yHotspot", wt.DWORD), ("hbmMask", wt.HANDLE),
                        ("hbmColor", wt.HANDLE)]
        info2 = ICONINFO(True, 0, 0, mask_bmp, color_bmp)
        hicon = u32.CreateIconIndirect(ctypes.byref(info2))
        return hicon

    def _create_message_window(self):
        wndproc = TrayIcon.WNDPROC(self._wndproc)
        self._wndproc_ref = wndproc            # 保住引用，避免被 GC
        clsname = f"PyShotTray_{self.id}"
        hinstance = k32.GetModuleHandleW(0)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(wndproc, ctypes.c_void_p)
        wc.hInstance = hinstance
        wc.lpszClassName = clsname
        u32.RegisterClassW(ctypes.byref(wc))
        hwnd = u32.CreateWindowExW(0, clsname, clsname, 0,
                                   0, 0, 0, 0, -3, 0, hinstance, 0)  # -3 = HWND_MESSAGE
        return hwnd

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam == WM_LBUTTONDBLCLK:
                self.tk_root.after_idle(lambda: self.on_event("double"))
            elif lparam == WM_RBUTTONUP:
                self.tk_root.after_idle(lambda: self.on_event("menu"))
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def show(self):
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        shell.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        self.nid.uVersion = NOTIFYICON_VERSION
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def show_message(self, title: str, msg: str):
        self.nid.uFlags = NIF_INFO
        self.nid.szInfo = msg
        self.nid.szInfoTitle = title
        self.nid.dwInfoFlags = 1               # NIIF_INFO
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def set_tooltip(self, text: str):
        self.nid.uFlags = NIF_TIP
        self.nid.szTip = text
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def destroy(self):
        shell.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
        if self.nid.hIcon:
            u32.DestroyIcon(self.nid.hIcon)
        if self.hwnd:
            u32.DestroyWindow(self.hwnd)


# ---------------------------------------------------------------- 通用窗口

def center_window(win: tk.Toplevel, w: int, h: int):
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
