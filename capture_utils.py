# -*- coding: utf-8 -*-
"""抓屏工具：内容空白检测 + PrintWindow 回退抓取。

为什么需要
==========
远程桌面 / 虚拟化应用（Citrix Workspace、RDP 里的应用等）常用硬件加速或
内容保护渲染，常规的屏幕 BitBlt（Qt 的 QScreen.grabWindow）可能拿到**黑屏或
纯色**。这里提供：

- is_blank()：判断抓到的画面是不是"没内容"（纯黑/纯色），用于给出明确提示
- grab_window_printwindow()：改用 Windows 的 PrintWindow(PW_RENDERFULLCONTENT)
  把指定窗口自己渲染一遍，能救回一部分 BitBlt 拿不到内容的窗口
"""
import ctypes
import ctypes.wintypes as wt

from PySide6.QtGui import QImage, QPixmap

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def _gray_stats(pix: QPixmap):
    """返回 (均值, 标准差)；无法分析时返回 None。纯 Python，不依赖 numpy。"""
    if pix is None or pix.isNull():
        return None
    img = pix.toImage().convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    if w < 4 or h < 4:
        return None
    data = bytes(img.constBits())
    row_step = max(1, h // 60)
    col_step = max(1, w // 60)
    total = total_sq = 0.0
    n = 0
    for y in range(0, h, row_step):
        row = data[y * bpl: y * bpl + w * 3]
        for x in range(0, w * 3, col_step * 3):
            v = (row[x] + row[x + 1] + row[x + 2]) / 3.0
            total += v
            total_sq += v * v
            n += 1
    if n == 0:
        return None
    mean = total / n
    var = max(0.0, total_sq / n - mean * mean)
    return mean, var ** 0.5


def pixmap_is_blank(pix: QPixmap, min_std: float = 2.0,
                    black_level: float = 12.0) -> bool:
    """判断画面是否"没内容"：整幅近乎纯色，或几乎全黑。"""
    stats = _gray_stats(pix)
    if stats is None:
        return True
    mean, std = stats
    return std < min_std or mean < black_level


def looks_like_missing_content(pix: QPixmap, black_level: float = 18.0,
                               uniform_std: float = 0.6) -> bool:
    """更像"抓不到内容"而非"用户就选了张素色图"：

    - 几乎全黑（远程桌面/受保护内容的典型表现），或
    - 完全没有变化且不是纯白（纯白页面可能是真实内容，不误报）
    """
    stats = _gray_stats(pix)
    if stats is None:
        return True
    mean, std = stats
    return mean < black_level or (std < uniform_std and mean < 250.0)


def window_at(x: int, y: int) -> int:
    """返回屏幕坐标（物理像素）处的窗口句柄。"""
    pt = wt.POINT(int(x), int(y))
    return int(user32.WindowFromPoint(pt))


def _hwnd_bitmap(hwnd: int):
    """用 PrintWindow 把窗口画进位图，返回 (hbitmap, memdc, hdc, rect)。"""
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
    if not ok:                      # 老系统不支持 PW_RENDERFULLCONTENT 时退化为 0
        user32.PrintWindow(wt.HWND(hwnd), memdc, 0)
    return bmp, memdc, hdc, rect


def _bitmap_to_image(bmp, memdc, w: int, h: int) -> QImage | None:
    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth = w
    info.biHeight = -h              # 负数 = 自上而下
    info.biPlanes = 1
    info.biBitCount = 32
    info.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    got = gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(info), DIB_RGB_COLORS)
    if not got:
        return None
    img = QImage(bytes(buf), w, h, w * 4, QImage.Format_RGB32).copy()
    return img


def grab_window_printwindow(hwnd: int) -> QPixmap | None:
    """把窗口自身渲染成 pixmap（拿不到则返回 None）。"""
    if not hwnd or hwnd == 0:
        return None
    res = _hwnd_bitmap(hwnd)
    if res is None:
        return None
    bmp, memdc, hdc, rect = res
    try:
        img = _bitmap_to_image(bmp, memdc, rect.right - rect.left,
                               rect.bottom - rect.top)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(wt.HWND(hwnd), hdc)
    if img is None or img.isNull():
        return None
    return QPixmap.fromImage(img)


def grab_region_printwindow(region_physical, dpr: float = 1.0) -> QPixmap | None:
    """按屏幕物理像素矩形，用 PrintWindow 抓该区域（常用于 BitBlt 拿不到内容时）。

    region_physical: QRect，屏幕物理像素坐标。
    """
    from PySide6.QtCore import QRect
    hwnd = window_at(region_physical.center().x(), region_physical.center().y())
    pix = grab_window_printwindow(hwnd)
    if pix is None:
        return None
    rect = wt.RECT()
    if not user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect)):
        return None
    crop = QRect(region_physical.x() - rect.left, region_physical.y() - rect.top,
                 region_physical.width(), region_physical.height())
    crop = crop.intersected(QRect(0, 0, pix.width(), pix.height()))
    if crop.width() < 4 or crop.height() < 4:
        return None
    out = pix.copy(crop)
    out.setDevicePixelRatio(dpr)
    return out


# ---------------------------------------------------------------- 原生滚动条

OBJID_VSCROLL = -5
OBJID_HSCROLL = -6
STATE_SYSTEM_INVISIBLE = 0x00008000
STATE_SYSTEM_UNAVAILABLE = 0x00000001


class SCROLLBARINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcScrollBar", wt.RECT),
        ("dxyLineButton", ctypes.c_int),
        ("xyThumbTop", ctypes.c_int),
        ("xyThumbBottom", ctypes.c_int),
        ("reserved", ctypes.c_int),
        ("rgstate", wt.DWORD * 6),
    ]


def thumb_rect_from_info(info) -> tuple:
    """从 SCROLLBARINFO 算出滑块矩形（屏幕物理像素）。返回 (QRect, 是否可见)。"""
    from PySide6.QtCore import QRect
    sb = info.rcScrollBar
    visible = not (info.rgstate[0] & (STATE_SYSTEM_INVISIBLE
                                      | STATE_SYSTEM_UNAVAILABLE))
    top = sb.top + info.xyThumbTop
    height = max(1, info.xyThumbBottom - info.xyThumbTop)
    return QRect(sb.left, top, max(1, sb.right - sb.left), height), visible


def scrollbar_thumb_at(x: int, y: int, vertical: bool = True):
    """尽力找到 (x, y) 所在窗口的原生滚动条滑块矩形（屏幕物理像素）。

    只对使用系统标准滚动条的窗口有效；自绘滚动条（浏览器/Qt/虚拟桌面里的画面）
    会返回 None —— 那种情况只能相信用户点击的位置。
    """
    hwnd = window_at(x, y)
    if not hwnd:
        return None
    info = SCROLLBARINFO()
    info.cbSize = ctypes.sizeof(SCROLLBARINFO)
    obj = OBJID_VSCROLL if vertical else OBJID_HSCROLL
    if not user32.GetScrollBarInfo(wt.HWND(hwnd), obj, ctypes.byref(info)):
        return None
    rect, visible = thumb_rect_from_info(info)
    if not visible or rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return None
    return rect


# ---------------------------------------------------------------- 滚动位置 API

SB_VERT, SB_HORZ = 1, 0
SIF_RANGE, SIF_PAGE, SIF_POS, SIF_TRACKPOS, SIF_ALL = 0x1, 0x2, 0x4, 0x8, 0xF


class SCROLLINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("fMask", wt.UINT),
        ("nMin", ctypes.c_int), ("nMax", ctypes.c_int),
        ("nPage", wt.UINT), ("nPos", ctypes.c_int),
        ("nTrackPos", ctypes.c_int),
    ]


def _get_scroll_info(hwnd: int) -> dict | None:
    """读取窗口的垂直滚动条信息（GetScrollInfo）。无滚动条返回 None。"""
    info = SCROLLINFO()
    info.cbSize = ctypes.sizeof(SCROLLINFO)
    info.fMask = SIF_RANGE | SIF_PAGE | SIF_POS
    if not user32.GetScrollInfo(wt.HWND(hwnd), SB_VERT, ctypes.byref(info)):
        return None
    if info.nMax <= info.nMin or info.nPage <= 0:
        return None
    return {"hwnd": int(hwnd), "min": int(info.nMin), "max": int(info.nMax),
            "page": int(info.nPage), "pos": int(info.nPos)}


def get_scroll_info_at(x: int, y: int, max_ancestors: int = 6) -> dict | None:
    """在 (x, y) 物理像素处寻找可程序化滚动的窗口（向上找几层父窗口）。

    返回 {hwnd, min, max, page, pos} 或 None。
    """
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
    """用 SetScrollInfo 直接设置滚动位置（完全不用动鼠标）。返回设置后的位置。"""
    info = SCROLLINFO()
    info.cbSize = ctypes.sizeof(SCROLLINFO)
    info.fMask = SIF_POS
    info.nPos = int(pos)
    return int(user32.SetScrollInfo(wt.HWND(hwnd), SB_VERT,
                                    ctypes.byref(info), True))

def exclude_from_capture(hwnd: int, enable: bool = True) -> bool:
    """让某个窗口**不被屏幕抓取**（WDA_EXCLUDEFROMCAPTURE）。

    用途：截图遮罩可以先 show() 出来（用户马上就看见反应），再抓屏回填底图；
    有了这个排除，抓屏就不会把遮罩自己拍进去（否则截出来是黑的/带遮罩）。
    enable=False 表示恢复（WDA_NONE）——抓完底图就恢复，免得遮罩在别的抓屏
    （录屏工具、我们自己的测试）里也一并隐身。
    Windows 10 2004+ 支持；更老的系统退回 WDA_MONITOR（拍出来是纯黑），
    再不行返回 False，调用方就保持"先抓屏再显示"的老顺序。
    """
    try:
        user32 = ctypes.windll.user32
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        WDA_MONITOR = 0x00000001
        WDA_NONE = 0x00000000
        user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p,
                                                    ctypes.c_uint]
        if not enable:
            user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_NONE)
            return True
        if user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd),
                                           WDA_EXCLUDEFROMCAPTURE):
            return True
        if user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), WDA_MONITOR):
            return False          # 拍出来会是黑的，不能用来"先显示后抓屏"
    except Exception:             # noqa: BLE001
        pass
    return False

def force_foreground(hwnd: int) -> bool:
    """把窗口抢到最前并争取键盘焦点（Windows 专用兜底）。

    为什么需要：当本进程**没有任何可见窗口**时（例如用户刚把编辑器关掉），
    新建的全屏置顶窗口有时拿不到前台激活 —— 窗口是画出来了，但收不到键盘
    事件（Esc 失效），看起来就是"遮罩挡住了、怎么都关不掉"。
    这里显式 SetWindowPos 置顶 + SetForegroundWindow。
    """
    try:
        user32 = ctypes.windll.user32
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
        user32.SetActiveWindow(ctypes.c_void_p(hwnd))
        return True
    except Exception:                              # noqa: BLE001
        return False
