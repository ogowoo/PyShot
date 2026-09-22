# -*- coding: utf-8 -*-
"""wincapture.py —— 抓屏工具（纯 ctypes，配 winimg.Image）。

- 空白/纯色检测（识别硬件加速或内容保护窗口）
- PrintWindow 回退（BitBlt 拿不到内容时，如 Citrix/远程桌面）
- 原生滚动条 API（读滑块位置、程序化设置滚动位置）
"""
import ctypes
import ctypes.wintypes as wt

import winimg as wi

user32 = wi.u32
gdi32 = wi.g32

PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0

# 句柄参数声明（x64 下不声明会被截断成 32 位）
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetWindowDC.argtypes = [wt.HWND]
user32.GetWindowDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
user32.PrintWindow.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT]
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.GetScrollBarInfo.argtypes = [wt.HWND, ctypes.c_long, ctypes.c_void_p]
user32.GetScrollInfo.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetScrollInfo.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p,
                                 wt.BOOL]


# ---------------------------------------------------------------- 空白检测

def image_gray_stats(img: wi.Image):
    """返回 (均值, 标准差)。纯 Python 抽样统计。"""
    if img is None or img.w < 4 or img.h < 4:
        return None
    d = img.data
    row_step = max(1, img.h // 60)
    col_step = max(1, img.w // 60)
    total = total_sq = 0.0
    n = 0
    for y in range(0, img.h, row_step):
        base = y * img.w * 4
        for x in range(0, img.w, col_step):
            i = base + x * 4
            v = (d[i] + d[i + 1] + d[i + 2]) / 3.0
            total += v
            total_sq += v * v
            n += 1
    if n == 0:
        return None
    mean = total / n
    var = max(0.0, total_sq / n - mean * mean)
    return mean, var ** 0.5


def image_is_blank(img: wi.Image, min_std: float = 2.0,
                   black_level: float = 12.0, uniform_std: float = 2.5) -> bool:
    """空白（纯黑 / 纯色）判定。"""
    st = image_gray_stats(img)
    if st is None:
        return False
    mean, std = st
    return mean < black_level or (std < uniform_std and mean < 250.0)


def looks_like_missing_content(img: wi.Image, black_level: float = 18.0,
                               uniform_std: float = 2.5) -> bool:
    """像"没抓到内容"（黑屏或极均匀），但不误判正常白色页面。"""
    st = image_gray_stats(img)
    if st is None:
        return False
    mean, std = st
    return mean < black_level or (std < uniform_std and mean < 250.0)


# ---------------------------------------------------------------- 窗口/PrintWindow

def window_at(x: int, y: int) -> int:
    return int(user32.WindowFromPoint(wt.POINT(int(x), int(y))) or 0)


def _hwnd_bitmap(hwnd: int):
    rect = wt.RECT()
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    hdc = user32.GetWindowDC(wt.HWND(hwnd))
    if not hdc:
        return None
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)
    ok = user32.PrintWindow(wt.HWND(hwnd), memdc, PW_RENDERFULLCONTENT)
    if not ok:
        user32.PrintWindow(wt.HWND(hwnd), memdc, 0)
    return bmp, memdc, hdc, rect


def grab_window_printwindow(hwnd: int):
    """把窗口自身渲染成 Image（拿不到返回 None）。"""
    if not hwnd:
        return None
    res = _hwnd_bitmap(hwnd)
    if res is None:
        return None
    bmp, memdc, hdc, rect = res
    w, h = rect.right - rect.left, rect.bottom - rect.top
    try:
        buf = ctypes.create_string_buffer(w * h * 4)
        got = gdi32.GetDIBits(memdc, bmp, 0, h, buf,
                              ctypes.byref(wi._bmi(w, h)), DIB_RGB_COLORS)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(wt.HWND(hwnd), hdc)
    if not got:
        return None
    return wi.Image(w, h, buf.raw)


def grab_region_printwindow(x: int, y: int, w: int, h: int,
                            dpr: float = 1.0):
    """按屏幕物理像素矩形用 PrintWindow 抓（BitBlt 拿不到内容时用）。"""
    hwnd = window_at(x + w // 2, y + h // 2)
    img = grab_window_printwindow(hwnd)
    if img is None:
        return None
    rect = wt.RECT()
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect)):
        return None
    cx = x - rect.left
    cy = y - rect.top
    cx = max(0, min(cx, img.w))
    cy = max(0, min(cy, img.h))
    cw = max(0, min(w, img.w - cx))
    ch = max(0, min(h, img.h - cy))
    if cw < 4 or ch < 4:
        return None
    out = img.crop(cx, cy, cw, ch)
    out.dpr = dpr
    return out


def grab_region_smart(x: int, y: int, w: int, h: int, dpr: float = 1.0):
    """常规 BitBlt 抓取；若结果是空白/纯色（硬件加速、内容保护）则回退 PrintWindow。"""
    out = wi.grab_region(x, y, w, h, dpr)
    if image_is_blank(out):
        alt = grab_region_printwindow(x, y, w, h, dpr)
        if alt is not None and not image_is_blank(alt):
            return alt
    return out


# ---------------------------------------------------------------- 原生滚动条

OBJID_VSCROLL = -5
OBJID_HSCROLL = -6
STATE_SYSTEM_INVISIBLE = 0x00008000
STATE_SYSTEM_UNAVAILABLE = 0x00000001
SB_VERT, SB_HORZ = 1, 0
SIF_RANGE, SIF_PAGE, SIF_POS, SIF_TRACKPOS, SIF_ALL = 0x1, 0x2, 0x4, 0x8, 0xF


class SCROLLBARINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcScrollBar", wt.RECT),
                ("dxyLineButton", ctypes.c_int),
                ("xyThumbTop", ctypes.c_int),
                ("xyThumbBottom", ctypes.c_int),
                ("reserved", ctypes.c_int),
                ("rgstate", wt.DWORD * 6)]


class SCROLLINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT),
                ("nMin", ctypes.c_int), ("nMax", ctypes.c_int),
                ("nPage", wt.UINT), ("nPos", ctypes.c_int),
                ("nTrackPos", ctypes.c_int)]


def scrollbar_thumb_rect(x: int, y: int, vertical: bool = True):
    """(x, y) 处窗口的原生滚动条滑块矩形（屏幕物理像素），返回 (l, t, w, h)。"""
    hwnd = window_at(x, y)
    if not hwnd:
        return None
    info = SCROLLBARINFO()
    info.cbSize = ctypes.sizeof(SCROLLBARINFO)
    obj = OBJID_VSCROLL if vertical else OBJID_HSCROLL
    if not user32.GetScrollBarInfo(wt.HWND(hwnd), obj, ctypes.byref(info)):
        return None
    if info.rgstate[0] & (STATE_SYSTEM_INVISIBLE | STATE_SYSTEM_UNAVAILABLE):
        return None
    sb = info.rcScrollBar
    top = sb.top + info.xyThumbTop
    height = max(1, info.xyThumbBottom - info.xyThumbTop)
    return sb.left, top, max(1, sb.right - sb.left), height


def _get_scroll_info(hwnd: int):
    info = SCROLLINFO()
    info.cbSize = ctypes.sizeof(SCROLLINFO)
    info.fMask = SIF_RANGE | SIF_PAGE | SIF_POS
    if not user32.GetScrollInfo(wt.HWND(hwnd), SB_VERT, ctypes.byref(info)):
        return None
    if info.nMax <= info.nMin or info.nPage <= 0:
        return None
    return {"hwnd": int(hwnd), "min": int(info.nMin), "max": int(info.nMax),
            "page": int(info.nPage), "pos": int(info.nPos)}


def get_scroll_info_at(x: int, y: int, max_ancestors: int = 6):
    """在 (x, y) 物理像素处向上找可程序化滚动的窗口。"""
    hwnd = window_at(x, y)
    tried = set()
    while hwnd and hwnd not in tried and max_ancestors > 0:
        tried.add(hwnd)
        info = _get_scroll_info(hwnd)
        if info is not None:
            return info
        parent = user32.GetParent(wt.HWND(hwnd))
        hwnd = int(parent) if parent else 0
        max_ancestors -= 1
    return None


def set_scroll_pos(hwnd: int, pos: int) -> int:
    """SetScrollInfo 直接设置滚动位置（不动鼠标）。"""
    info = SCROLLINFO()
    info.cbSize = ctypes.sizeof(SCROLLINFO)
    info.fMask = SIF_POS
    info.nPos = int(pos)
    return int(user32.SetScrollInfo(wt.HWND(hwnd), SB_VERT,
                                    ctypes.byref(info), True))
