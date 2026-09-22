# -*- coding: utf-8 -*-
"""wintk.py —— Tkinter 界面框架（主题、图标、托盘、Win32 消息泵）。"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import threading
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
wi.g32.SetBitmapBits.argtypes = [ctypes.c_void_p, ctypes.c_long,
                                 ctypes.c_void_p]
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
_SENTINEL = (255, 0, 255)      # 品红哨兵：画完仍是这个颜色 = 没画到 = 透明


class _ScaledRenderer:
    """按倍数缩放坐标的绘制代理。

    GDI 的画笔不做抗锯齿，而图标绘制函数是按 22x22 写死坐标的。
    先在 ss 倍尺寸上画、再降采样平均，就能得到干净的抗锯齿边缘和 alpha。
    """

    def __init__(self, r, ss: int):
        self._r = r
        self._ss = ss

    def use_pen(self, color, width):
        self._r.use_pen(color, max(1, int(round(width * self._ss))))

    def use_brush(self, color=None):
        self._r.use_brush(color)

    def line(self, x1, y1, x2, y2, color, width=1):
        s = self._ss
        self._r.line(x1 * s, y1 * s, x2 * s, y2 * s, color,
                     max(1, int(round(width * s))))

    def rect(self, x, y, w, h, color, width=1, fill=False, round_=0):
        s = self._ss
        self._r.rect(x * s, y * s, w * s, h * s, color,
                     max(1, int(round(width * s))), fill, round_ * s)

    def ellipse(self, x, y, w, h, color, width=1, fill=False):
        s = self._ss
        self._r.ellipse(x * s, y * s, w * s, h * s, color,
                        max(1, int(round(width * s))), fill)

    def polygon(self, pts, color, width=1, fill=False):
        s = self._ss
        self._r.polygon([(x * s, y * s) for x, y in pts], color,
                        max(1, int(round(width * s))), fill)

    def text(self, x, y, s_, color, family="Microsoft YaHei", size_px=18,
             bold=False, italic=False):
        s = self._ss
        self._r.text(x * s, y * s, s_, color, family,
                     max(1, int(round(size_px * s))), bold, italic)

    def text_center(self, x, y, w, h, s_, color, family="Microsoft YaHei",
                    size_px=18, bold=False):
        s = self._ss
        self._r.text_center(x * s, y * s, w * s, h * s, s_, color, family,
                            max(1, int(round(size_px * s))), bold)


def register_icon(name, fn):
    _icon_drawers[name] = fn


def make_icon_image(name: str, color=(230, 57, 53), size: int = 22,
                    ss: int = 4) -> wi.Image:
    """把矢量图标画成一张**带 alpha** 的 Image。

    做法：哨兵色铺底 → 在 ss 倍尺寸上用 GDI 画 → 降采样时
    alpha = 覆盖到的子像素比例、RGB = 覆盖像素的颜色均值。
    这样既有抗锯齿边缘，背景又真透明（Tk 会把它合到控件底色上）。
    """
    big = size * ss
    buf = wi.Image(big, big)
    sr, sg, sb = _SENTINEL
    buf.data = bytearray(bytes((sb, sg, sr, 255)) * (big * big))   # BGRA 哨兵
    r = buf.renderer()
    _icon_drawers[name](_ScaledRenderer(r, ss), color)
    r.close()

    out = wi.Image(size, size)
    d = buf.data
    o = out.data
    denom = ss * ss
    for y in range(size):
        for x in range(size):
            tr = tg = tb = cnt = 0
            for dy in range(ss):
                base = ((y * ss + dy) * big + x * ss) * 4
                for dx in range(ss):
                    i = base + dx * 4
                    b, g, rr = d[i], d[i + 1], d[i + 2]
                    if b == sb and g == sg and rr == sr:
                        continue          # 哨兵色 = 没画到
                    tr += rr
                    tg += g
                    tb += b
                    cnt += 1
            j = (y * size + x) * 4
            if cnt:
                o[j] = tb // cnt          # B
                o[j + 1] = tg // cnt      # G
                o[j + 2] = tr // cnt      # R
                o[j + 3] = min(255, int(round(cnt * 255 / denom)))   # A
            # 否则保持全 0（完全透明）
    return out


def make_icon_photo(name: str, color=(230, 57, 53), size: int = 22,
                    master=None):
    """生成图标 PhotoImage（带透明通道，背景不会挡住控件底色）。

    必须传 master（通常是它所属的窗口）：tk.PhotoImage 默认绑到**默认
    解释器**上，多 Tk 窗口时会报 image doesn't exist。
    """
    img = make_icon_image(name, color, size)
    return tk.PhotoImage(data=img.to_png_rgba(), master=master)


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

# 热键修饰键与默认组合
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
WM_HOTKEY = 0x0312
DEFAULT_HOTKEYS = ["ctrl+alt+x", "ctrl+shift+x", "ctrl+alt+f9",
                   "ctrl+shift+f9"]


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


class Win32Pump:
    """在**独立线程**里跑 Win32 消息循环，承载托盘图标与全局热键。

    为什么不能放在 Tk 主线程
    ------------------------
    Tk 的 mainloop 泵消息时会释放 GIL。此时 Windows 把消息派发给我们用
    ctypes 建的窗口过程，ctypes 要恢复 Python 线程状态，而主线程的状态已被
    分离 —— 直接触发致命错误：

        Fatal Python error: PyEval_RestoreThread: the function must be called
        with the GIL held, ... but the GIL is released
        (the current Python thread state is NULL)

    所以把消息窗口、托盘图标、热键都放进自己的线程：它有正常线程状态，
    回调里只做"入队"这一件事；Tk 主线程用 after() 轮询队列取事件
    （跨线程只传数据，绝不碰 Tk 对象）。
    """

    WM_TRAY = WM_USER + 512
    WM_PUMP_QUIT = 0x8000 + 1
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT,
                                 ctypes.c_ssize_t, ctypes.c_ssize_t)

    def __init__(self, tooltip: str = "PyShot"):
        self.events = queue.Queue()
        self.hwnd = None
        self.hotkey = None
        self._tooltip = tooltip
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._nid = None
        self._hicon = None
        self._wndproc = None
        self._cls = None

    # ---------- 生命周期 ----------
    def start(self, hotkey_specs=None, timeout: float = 8.0):
        """启动线程：建消息窗口 → 加托盘图标 → 注册热键 → 跑消息循环。"""
        self._thread = threading.Thread(target=self._run, args=(hotkey_specs,),
                                        name="pyshot-win32", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self

    def stop(self, timeout: float = 3.0):
        """请求线程收尾（清理必须在它自己的线程里做）。"""
        if self.hwnd:
            u32.PostMessageW(self.hwnd, self.WM_PUMP_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def poll(self, max_items: int = 32):
        """Tk 主线程调用：取出待处理事件 [(kind, payload), ...]。"""
        out = []
        for _ in range(max_items):
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    # ---------- 线程内部 ----------
    def _run(self, hotkey_specs):
        try:
            self._create_window()
            self._add_tray()
            self._register_hotkeys(hotkey_specs)
        except Exception as ex:  # noqa: BLE001
            self.events.put(("error", f"{type(ex).__name__}: {ex}"))
        finally:
            self._ready.set()
        if not self.hwnd:
            return
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_PUMP_QUIT:
                break
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        self._cleanup()

    def _create_window(self):
        self._thread_id = k32.GetCurrentThreadId()
        self._wndproc = Win32Pump.WNDPROC(self._proc)
        self._cls = f"PyShotPump_{self._thread_id}"
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        u32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = u32.CreateWindowExW(0, self._cls, self._cls, 0, 0, 0, 0, 0,
                                        -3, None, hinst, None)   # HWND_MESSAGE

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            if lparam == WM_LBUTTONDBLCLK:
                self.events.put(("double", None))
            elif lparam == WM_RBUTTONUP:
                self.events.put(("menu", None))
        elif msg == WM_HOTKEY:
            self.events.put(("hotkey", int(wparam)))
        elif msg == self.WM_PUMP_QUIT:
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------- 托盘 ----------
    def _add_tray(self):
        self._hicon = _make_tray_hicon()
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = self.WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self._tooltip
        self._nid = nid
        shell.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        nid.uVersion = NOTIFYICON_VERSION
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def show_message(self, title: str, msg: str):
        if self._nid is None:
            return
        self._nid.uFlags = NIF_INFO
        self._nid.szInfo = msg[:250]
        self._nid.szInfoTitle = title[:60]
        self._nid.dwInfoFlags = 1
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def set_tooltip(self, text: str):
        if self._nid is None:
            return
        self._nid.uFlags = NIF_TIP
        self._nid.szTip = text[:120]
        shell.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    # ---------- 热键 ----------
    def _register_hotkeys(self, specs):
        specs = list(specs or DEFAULT_HOTKEYS)
        env = os.environ.get("PYSHOT_HOTKEY")
        if env:
            specs = [env] + specs
        for i, spec in enumerate(specs):
            mods, vk = parse_hotkey(spec)
            if not vk:
                continue
            if u32.RegisterHotKey(self.hwnd, 0xB000 + i, mods, vk):
                self.hotkey = spec
                return

    def _cleanup(self):
        try:
            if self._nid is not None:
                shell.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            if self._hicon:
                u32.DestroyIcon(self._hicon)
            if self.hwnd:
                u32.DestroyWindow(self.hwnd)
        except Exception:  # noqa: BLE001
            pass
        self.hwnd = None


def _make_tray_hicon():
    """画出托盘图标并转成 HICON（圆角处的透明用 AND 掩码表达）。"""
    img = wi.Image(32, 32)
    r = img.renderer()
    r.rect(0, 0, 32, 32, (76, 154, 255), 0, fill=True, round_=10)
    r.rect(6, 11, 20, 13, (255, 255, 255), 1.5, fill=True)
    r.rect(12, 7, 8, 5, (255, 255, 255), 1.5, fill=True)
    r.ellipse(12, 13, 8, 8, (76, 154, 255), 1.5, fill=True)
    r.ellipse(14.5, 15.5, 3, 3, (255, 255, 255), 1.5, fill=True)
    r.close()
    # 画到 DIB 上取回 32bpp 数据
    hdc = u32.GetDC(None)
    memdc = wi.g32.CreateCompatibleDC(hdc)
    color_bmp = wi.g32.CreateCompatibleBitmap(hdc, 32, 32)
    wi.g32.SelectObject(memdc, color_bmp)
    buf = ctypes.create_string_buffer(bytes(img.data), len(img.data))
    wi.g32.SetDIBits(memdc, color_bmp, 0, 32, buf,
                     ctypes.byref(wi._bmi(32, 32)), 0)
    wi.g32.DeleteDC(memdc)
    u32.ReleaseDC(None, hdc)
    # 圆角外缘（未绘制到 → alpha 0）用 1bpp AND 掩码标出来，否则 Windows 会画成黑角
    row_bytes = ((32 + 31) // 32) * 4
    mask = bytearray(row_bytes * 32)
    for y in range(32):
        for x in range(32):
            if img.data[(y * 32 + x) * 4 + 3] < 128:
                mask[y * row_bytes + (x // 8)] |= 0x80 >> (x % 8)
    mask_bmp = wi.g32.CreateBitmap(32, 32, 1, 1, None)
    wi.g32.SetBitmapBits(mask_bmp, len(mask), bytes(mask))

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD),
                    ("yHotspot", wt.DWORD), ("hbmMask", wt.HANDLE),
                    ("hbmColor", wt.HANDLE)]

    info = ICONINFO(True, 0, 0, mask_bmp, color_bmp)
    return u32.CreateIconIndirect(ctypes.byref(info))


def parse_hotkey(spec: str):
    """'ctrl+alt+x' → (mods, vk)。"""
    parts = [p.strip().lower() for p in spec.split("+")]
    mods = 0
    vk = 0
    for p in parts:
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p == "win":
            mods |= MOD_WIN
        elif len(p) == 1:
            vk = ord(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x70 + int(p[1:]) - 1
    return mods, vk


# ---------------------------------------------------------------- 通用窗口

def center_window(win: tk.Toplevel, w: int, h: int):
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
