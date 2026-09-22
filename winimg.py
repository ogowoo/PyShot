# -*- coding: utf-8 -*-
"""winimg.py —— 纯 ctypes 的图像核心（零第三方依赖）。

只用 Windows GDI / GDI+ / Win32 API：
- 抓屏（区域 / 整个虚拟桌面，物理像素，天然支持多显示器与缩放）
- 绘制图形与文字（在 DIB Section 上用 GDI 画：线/矩形/椭圆/多边形/文字，ClearType）
- 高亮（AlphaBlend）、马赛克（纯 Python 像素块）、裁剪、缩放
- 编码：PNG（zlib 纯 Python）、BMP（纯 Python）、JPEG（GDI+）
- 复制到剪贴板（CF_DIB）

Image 的内部布局是 **BGRA**（与 GDI 的 32bpp 一致），像素坐标系 y 向下。
"""
import ctypes
import ctypes.wintypes as wt
import struct
import zlib

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32
gplus = ctypes.windll.gdiplus
msimg = ctypes.windll.msimg32

# ctypes 默认把返回值按 32 位 int 处理，x64 下会截断 64 位句柄/指针。
# 给返回句柄/指针的函数显式声明 c_void_p（否则 GlobalLock 等会拿到坏指针）。
for _mod in (u32, g32, k32, gplus):
    for _name in (
            "GetDC", "CreateCompatibleDC", "CreateCompatibleBitmap",
            "CreateDIBSection", "CreatePen", "CreateSolidBrush",
            "CreateFontIndirectW", "GetStockObject", "SelectObject",
            "GlobalAlloc", "GlobalLock", "GetDpiForMonitor",
            "GdipCreateBitmapFromHBITMAP"):
        try:
            getattr(_mod, _name).restype = ctypes.c_void_p
        except AttributeError:
            pass

# 带句柄参数的常用函数：声明参数类型，避免 64 位句柄被截断
try:
    u32.GetDC.argtypes = [wt.HWND]
    u32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
    g32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    g32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_int]
    g32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    g32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                           ctypes.c_int, ctypes.c_int, wt.DWORD]
    g32.DeleteDC.argtypes = [ctypes.c_void_p]
    g32.DeleteObject.argtypes = [ctypes.c_void_p]
    g32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                              wt.UINT, ctypes.c_void_p, ctypes.c_void_p,
                              wt.UINT]
    g32.SetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                              wt.UINT, ctypes.c_void_p, ctypes.c_void_p,
                              wt.UINT]
    k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalFree.argtypes = [ctypes.c_void_p]
    u32.OpenClipboard.argtypes = [wt.HWND]
    u32.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]

    _HDC = ctypes.c_void_p
    g32.CreateDIBSection.argtypes = [_HDC, ctypes.c_void_p, wt.UINT,
                                     ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
    g32.MoveToEx.argtypes = [_HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    g32.LineTo.argtypes = [_HDC, ctypes.c_int, ctypes.c_int]
    g32.Polygon.argtypes = [_HDC, ctypes.c_void_p, ctypes.c_int]
    g32.Ellipse.argtypes = [_HDC, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int]
    g32.Rectangle.argtypes = g32.Ellipse.argtypes
    g32.RoundRect.argtypes = [_HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int]
    g32.TextOutW.argtypes = [_HDC, ctypes.c_int, ctypes.c_int,
                             ctypes.c_wchar_p, ctypes.c_int]
    u32.DrawTextW.argtypes = [_HDC, ctypes.c_wchar_p, ctypes.c_int,
                              ctypes.c_void_p, wt.UINT]
    g32.GetTextExtentPoint32W.argtypes = [_HDC, ctypes.c_wchar_p,
                                          ctypes.c_int, ctypes.c_void_p]
    g32.SetBkMode.argtypes = [_HDC, ctypes.c_int]
    g32.SetTextColor.argtypes = [_HDC, wt.DWORD]
    g32.SetStretchBltMode.argtypes = [_HDC, ctypes.c_int]
    g32.StretchBlt.argtypes = [_HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, _HDC, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, wt.DWORD]
except AttributeError:
    pass

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
TRANSPARENT = 0x00000001
PS_SOLID = 0
NULL_BRUSH = 5
DT_CENTER = 0x1
DT_VCENTER = 0x4
DT_SINGLELINE = 0x20
DT_NOCLIP = 0x100
DT_LEFT = 0x0
DT_TOP = 0x0


# ---------------------------------------------------------------- 结构体

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


class LOGFONTW(ctypes.Structure):
    _fields_ = [("lfHeight", ctypes.c_long), ("lfWidth", ctypes.c_long),
                ("lfEscapement", ctypes.c_long), ("lfOrientation", ctypes.c_long),
                ("lfWeight", ctypes.c_long), ("lfItalic", wt.BYTE),
                ("lfUnderline", wt.BYTE), ("lfStrikeOut", wt.BYTE),
                ("lfCharSet", wt.BYTE), ("lfOutPrecision", wt.BYTE),
                ("lfClipPrecision", wt.BYTE), ("lfQuality", wt.BYTE),
                ("lfPitchAndFamily", wt.BYTE), ("lfFaceName", wt.WCHAR * 32)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPCWSTR),
                ("lpDesktop", wt.LPCWSTR), ("lpTitle", wt.LPCWSTR),
                ("dwX", wt.DWORD), ("dwY", wt.DWORD),
                ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
                ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD),
                ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
                ("hStdError", wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", wt.UINT),
                ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", ctypes.c_int),
                ("SuppressExternalCodecs", ctypes.c_int)]


class GdiplusStartupOutput(ctypes.Structure):
    _fields_ = [("NotificationHook", ctypes.c_void_p),
                ("NotificationUnhook", ctypes.c_void_p)]


class CLSID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_guid(cls, g: str):
        c = cls()
        h = g.strip("{}").split("-")
        c.Data1 = int(h[0], 16)
        c.Data2 = int(h[1], 16)
        c.Data3 = int(h[2], 16)
        c.Data4 = (ctypes.c_ubyte * 8)(*[int(h[3] + h[4], 16) >> (8 * (7 - i)) & 0xFF
                                         for i in range(8)])
        return c


class EncoderParameter(ctypes.Structure):
    _fields_ = [("Guid", CLSID), ("NumberOfValues", wt.ULONG),
                ("Type", wt.ULONG), ("Value", ctypes.c_void_p)]


class EncoderParameters(ctypes.Structure):
    _fields_ = [("Count", wt.UINT), ("Parameter", EncoderParameter * 1)]


JPEG_CLSID = CLSID.from_guid("{557cf401-1a04-11d3-9a73-0000f81ef32e}")
ENCODER_QUALITY_GUID = CLSID.from_guid("{1d5be4b5-fa4a-452d-9cdd-5db35105e7eb}")

for _name in ("GdipCreateBitmapFromHBITMAP",):
    getattr(gplus, _name).argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p]
    getattr(gplus, _name).restype = ctypes.c_int
gplus.GdipSaveImageToFile.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                      ctypes.c_void_p, ctypes.c_void_p]
gplus.GdipSaveImageToFile.restype = ctypes.c_int
gplus.GdipDisposeImage.argtypes = [ctypes.c_void_p]
gplus.GdiplusStartup.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p]
gplus.GdiplusStartup.restype = ctypes.c_int


def _bmi(w: int, h: int) -> BITMAPINFO:
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    return info


# ---------------------------------------------------------------- Image

class Image:
    """BGRA 图像。data 是 bytearray，长度 w*h*4。"""

    __slots__ = ("w", "h", "data", "dpr")

    def __init__(self, w: int, h: int, data=None, dpr: float = 1.0):
        self.w = int(w)
        self.h = int(h)
        self.data = bytearray(data) if data is not None \
            else bytearray(self.w * self.h * 4)
        self.dpr = float(dpr or 1.0)

    # ---------- 基础 ----------
    def copy(self) -> "Image":
        return Image(self.w, self.h, self.data, self.dpr)

    def crop(self, x: int, y: int, w: int, h: int) -> "Image":
        x, y = max(0, x), max(0, y)
        w = max(0, min(w, self.w - x))
        h = max(0, min(h, self.h - y))
        if w <= 0 or h <= 0:
            return Image(1, 1, dpr=self.dpr)
        out = Image(w, h, dpr=self.dpr)
        for yy in range(h):
            src = (y + yy) * self.w * 4 + x * 4
            out.data[yy * w * 4:(yy + 1) * w * 4] = self.data[src:src + w * 4]
        return out

    def sub(self, x, y, w, h):
        """返回 (bytes 行, ...) 便于局部处理（马赛克等）。"""
        return self.crop(x, y, w, h)

    # ---------- 像素级处理 ----------
    def dim(self, color=(0, 0, 0), alpha: float = 0.55) -> "Image":
        """全图压暗：返回新图。"""
        out = self.copy()
        r, g, b = color
        inv = 1.0 - alpha
        d = out.data
        for i in range(0, len(d), 4):
            d[i] = int(d[i] * inv + b * alpha)
            d[i + 1] = int(d[i + 1] * inv + g * alpha)
            d[i + 2] = int(d[i + 2] * inv + r * alpha)
        return out

    def blend_rect(self, x: int, y: int, w: int, h: int, color, alpha: float):
        """把一块矩形区域用 color 以 alpha 混合（高亮用）。"""
        r, g, b = color
        inv = 1.0 - alpha
        d = self.data
        for yy in range(max(0, y), min(self.h, y + h)):
            for xx in range(max(0, x), min(self.w, x + w)):
                i = (yy * self.w + xx) * 4
                d[i] = int(d[i] * inv + b * alpha)
                d[i + 1] = int(d[i + 1] * inv + g * alpha)
                d[i + 2] = int(d[i + 2] * inv + r * alpha)

    def mosaic(self, x: int, y: int, w: int, h: int, block: int = 12):
        """把区域做马赛克（先缩到小块再放大，nearest）。"""
        if w < 1 or h < 1:
            return
        small_w = max(1, w // block)
        small_h = max(1, h // block)
        # 采样小块
        small = [[0, 0, 0, 0] for _ in range(small_w * small_h)]
        d = self.data
        for sy in range(small_h):
            for sx in range(small_w):
                src_x = x + sx * block
                src_y = y + sy * block
                i = (src_y * self.w + src_x) * 4
                small[sy * small_w + sx] = [d[i], d[i + 1], d[i + 2], 255]
        for sy in range(small_h):
            for sx in range(small_w):
                px = small[sy * small_w + sx]
                y0 = y + sy * block
                y1 = min(y + (sy + 1) * block, y + h)
                x0 = x + sx * block
                x1 = min(x + (sx + 1) * block, x + w)
                for yy in range(y0, y1):
                    for xx in range(x0, x1):
                        i = (yy * self.w + xx) * 4
                        d[i], d[i + 1], d[i + 2] = px[0], px[1], px[2]

    # ---------- GDI 渲染 ----------
    def renderer(self) -> "Renderer":
        """得到一个能在本图上用 GDI 画图的上下文（用完要 close）。"""
        return Renderer(self)

    def darken_overlay(self, color=(0, 0, 0), alpha: int = 110) -> "Image":
        """GDI 加速的平滑压暗（AlphaBlend），用于截图遮罩，~10ms 全屏。"""
        out = self.copy()
        hdc = u32.GetDC(0)
        g32.SetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                 wt.DWORD]
        msimg.AlphaBlend.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     BLENDFUNCTION]
        dst = g32.CreateCompatibleDC(hdc)
        dst_bmp = g32.CreateCompatibleBitmap(hdc, out.w, out.h)
        g32.SelectObject(dst, dst_bmp)
        tmp = ctypes.create_string_buffer(bytes(out.data), len(out.data))
        g32.SetDIBits(dst, dst_bmp, 0, out.h, tmp,
                      ctypes.byref(_bmi(out.w, out.h)), DIB_RGB_COLORS)
        # 1x1 纯色源位图
        src = g32.CreateCompatibleDC(hdc)
        src_bmp = g32.CreateCompatibleBitmap(hdc, 2, 2)
        g32.SelectObject(src, src_bmp)
        r, g, b = color
        g32.SetPixel(src, 0, 0, r | (g << 8) | (b << 16))
        g32.SetPixel(src, 1, 1, r | (g << 8) | (b << 16))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha & 0xFF, 0)
        msimg.AlphaBlend(dst, 0, 0, out.w, out.h, src, 0, 0, 2, 2, blend)
        g32.GetDIBits(dst, dst_bmp, 0, out.h, tmp,
                      ctypes.byref(_bmi(out.w, out.h)), DIB_RGB_COLORS)
        out.data[:] = tmp.raw
        for o in (src_bmp, dst_bmp):
            g32.DeleteObject(o)
        for dc in (src, dst):
            g32.DeleteDC(dc)
        u32.ReleaseDC(0, hdc)
        return out

    # ---------- 编码 ----------
    def to_png(self) -> bytes:
        return _png_bytes(self.data, self.w, self.h)

    def save_png(self, path: str):
        with open(path, "wb") as f:
            f.write(self.to_png())

    def to_bmp(self) -> bytes:
        return _bmp_bytes(self.data, self.w, self.h)

    def save_bmp(self, path: str):
        with open(path, "wb") as f:
            f.write(self.to_bmp())

    def save_jpeg(self, path: str, quality: int = 90) -> bool:
        return _save_jpeg_gdiplus(self, path, quality)

    def copy_to_clipboard(self) -> bool:
        return _clipboard_set_image(self)

    # ---------- Tk 桥接 ----------
    def rgb_bytes(self) -> bytes:
        """BGRA → RGB（切片交错赋值，C 速度，比逐像素循环快几十倍）。"""
        d = self.data
        out = bytearray(self.w * self.h * 3)
        out[0::3] = d[2::4]
        out[1::3] = d[1::4]
        out[2::3] = d[0::4]
        return bytes(out)

    def to_ppm(self) -> bytes:
        """PPM 格式，给 tk.PhotoImage(data=...) 用（免压缩，~30ms 全屏）。"""
        return (f"P6\n{self.w} {self.h}\n255\n".encode() + self.rgb_bytes())

    def photo_bytes(self) -> bytes:
        """给 tk.PhotoImage(data=...) 用（PNG）。"""
        return self.to_png()

    # ---------- 与 stitch.Frame 桥接（拼接用纯 Python 行数据） ----------
    def to_frame(self):
        """Image → stitch.Frame（RGB 行）。"""
        from stitch import Frame
        rgb = self.rgb_bytes()
        rows = [rgb[y * self.w * 3:(y + 1) * self.w * 3] for y in range(self.h)]
        return Frame(rows, self.w, self.h, self.dpr)

    @classmethod
    def from_frame(cls, frame) -> "Image":
        """stitch.Frame（RGB 行）→ Image。"""
        rgb = b"".join(frame.rows)
        out = cls(frame.w, frame.h, dpr=frame.dpr)
        # RGB → BGRA
        out.data[0::4] = rgb[2::3]      # B
        out.data[1::4] = rgb[1::3]      # G
        out.data[2::4] = rgb[0::3]      # R
        out.data[3::4] = b"\xff" * (frame.w * frame.h)
        return out


# ---------------------------------------------------------------- 抓屏

def _make_dpi_aware():
    """让进程按每显示器 DPI 工作（抓屏/坐标才能对应真实物理像素）。"""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4))          # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_make_dpi_aware()


def _bit_blt_to_buffer(x, y, w, h) -> bytearray:
    hdc = u32.GetDC(0)
    memdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(memdc, bmp)
    g32.BitBlt(memdc, 0, 0, w, h, hdc, x, y, SRCCOPY)
    buf = ctypes.create_string_buffer(w * h * 4)
    info = _bmi(w, h)
    g32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(info), DIB_RGB_COLORS)
    g32.DeleteObject(bmp)
    g32.DeleteDC(memdc)
    u32.ReleaseDC(0, hdc)
    return bytearray(buf.raw)


def grab_region(x: int, y: int, w: int, h: int, dpr: float = 1.0) -> Image:
    """抓一块屏幕区域（物理像素坐标）。"""
    return Image(w, h, _bit_blt_to_buffer(x, y, w, h), dpr)


def virtual_desktop_rect() -> tuple:
    """返回 (left, top, width, height) —— 整个虚拟桌面的物理像素矩形。"""
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    left = u32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = u32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = u32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = u32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, w, h


def primary_dpi() -> float:
    """主屏 DPI 缩放（1.0 = 100%）。"""
    try:
        return u32.GetDpiForSystem() / 96.0
    except Exception:
        return 1.0


def grab_virtual_desktop() -> tuple:
    """抓整个虚拟桌面，返回 (Image, (left, top))。"""
    left, top, w, h = virtual_desktop_rect()
    return grab_region(left, top, w, h, primary_dpi()), (left, top)


# ---------------------------------------------------------------- Renderer（GDI 绘制）

class Renderer:
    """在一张 Image 上用 GDI 画图。用完 close() 释放 GDI 对象。"""

    def __init__(self, image: Image):
        self.img = image
        self._gdi_objects = []
        w, h = image.w, image.h
        self.dc = g32.CreateCompatibleDC(0)
        self.bmp = g32.CreateDIBSection(self.dc, ctypes.byref(_bmi(w, h)),
                                        DIB_RGB_COLORS, None, None, 0)
        self.old_bmp = g32.SelectObject(self.dc, self.bmp)
        self._gdi_objects += [self.dc, self.bmp]
        # 把现有图像内容搬进去
        tmp = ctypes.create_string_buffer(bytes(image.data), len(image.data))
        g32.SetDIBits(self.dc, self.bmp, 0, h, tmp,
                      ctypes.byref(_bmi(w, h)), DIB_RGB_COLORS)
        g32.SetBkMode(self.dc, TRANSPARENT)
        self._font = None
        self._pen_cache = {}
        self._brush_cache = {}

    def _pen(self, color, width: int = 1):
        key = (color, width)
        if key not in self._pen_cache:
            r, g, b = color
            # COLORREF = 0x00BBGGRR（低位红、次绿、高位蓝）
            pen = g32.CreatePen(PS_SOLID, int(width), r | (g << 8) | (b << 16))
            self._pen_cache[key] = pen
        return self._pen_cache[key]

    def _brush(self, color):
        if color not in self._brush_cache:
            r, g, b = color
            self._brush_cache[color] = g32.CreateSolidBrush(
                r | (g << 8) | (b << 16))
        return self._brush_cache[color]

    def use_pen(self, color, width: int):
        g32.SelectObject(self.dc, self._pen(color, width))

    def use_brush(self, color=None):
        if color is None:
            g32.SelectObject(self.dc, g32.GetStockObject(NULL_BRUSH))
        else:
            g32.SelectObject(self.dc, self._brush(color))

    def line(self, x1, y1, x2, y2, color, width=1):
        self.use_pen(color, width)
        self.use_brush(None)
        g32.MoveToEx(self.dc, int(x1), int(y1), None)
        g32.LineTo(self.dc, int(x2), int(y2))

    def polygon(self, pts, color, width=1, fill=False):
        self.use_pen(color, width)
        self.use_brush(color if fill else None)
        arr = (wt.POINT * len(pts))()
        for i, (x, y) in enumerate(pts):
            arr[i] = wt.POINT(int(x), int(y))
        g32.Polygon(self.dc, arr, len(pts))

    def rect(self, x, y, w, h, color, width=1, fill=False, round_=0):
        self.use_pen(color, width)
        self.use_brush(color if fill else None)
        if round_ > 0:
            g32.RoundRect(self.dc, int(x), int(y), int(x + w), int(y + h),
                          int(round_), int(round_))
        else:
            g32.Rectangle(self.dc, int(x), int(y), int(x + w), int(y + h))

    def ellipse(self, x, y, w, h, color, width=1, fill=False):
        self.use_pen(color, width)
        self.use_brush(color if fill else None)
        g32.Ellipse(self.dc, int(x), int(y), int(x + w), int(y + h))

    def set_font(self, family: str, size_px: int, bold=False, italic=False):
        lf = LOGFONTW()
        lf.lfHeight = -abs(int(size_px))
        lf.lfWeight = 700 if bold else 400
        lf.lfItalic = 1 if italic else 0
        lf.lfFaceName = family
        self._font = g32.CreateFontIndirectW(ctypes.byref(lf))
        g32.SelectObject(self.dc, self._font)

    def _text_color(self, color):
        r, g, b = color
        g32.SetTextColor(self.dc, r | (g << 8) | (b << 16))

    def text(self, x, y, s: str, color, family="Microsoft YaHei",
             size_px=18, bold=False, italic=False):
        self.set_font(family, size_px, bold, italic)
        self._text_color(color)
        g32.TextOutW(self.dc, int(x), int(y), s, len(s))

    def text_center(self, x, y, w, h, s: str, color,
                    family="Microsoft YaHei", size_px=18, bold=False):
        self.set_font(family, size_px, bold)
        self._text_color(color)
        rc = RECT(int(x), int(y), int(x + w), int(y + h))
        u32.DrawTextW(self.dc, s, len(s), ctypes.byref(rc),
                      DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOCLIP)

    def measure(self, s: str, family="Microsoft YaHei", size_px=18,
                bold=False) -> tuple:
        self.set_font(family, size_px, bold)
        size = wt.SIZE()
        g32.GetTextExtentPoint32W(self.dc, s, len(s), ctypes.byref(size))
        return size.cx, size.cy

    def close(self):
        # 把画好的内容取回 Python 缓冲
        img = self.img
        tmp = ctypes.create_string_buffer(img.w * img.h * 4)
        g32.GetDIBits(self.dc, self.bmp, 0, img.h, tmp,
                      ctypes.byref(_bmi(img.w, img.h)), DIB_RGB_COLORS)
        img.data[:] = tmp.raw
        # 释放
        g32.SelectObject(self.dc, self.old_bmp)
        for pen in self._pen_cache.values():
            g32.DeleteObject(pen)
        for br in self._brush_cache.values():
            g32.DeleteObject(br)
        if self._font:
            g32.DeleteObject(self._font)
        g32.DeleteObject(self.bmp)
        g32.DeleteDC(self.dc)


# ---------------------------------------------------------------- 编码

def _png_bytes(bgra: bytearray, w: int, h: int) -> bytes:
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    # BGRA → RGB（切片交错赋值，C 速度）
    out = bytearray(w * h * 3)
    out[0::3] = bgra[2::4]
    out[1::3] = bgra[1::4]
    out[2::3] = bgra[0::4]
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += out[y * w * 3:(y + 1) * w * 3]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def _bmp_bytes(bgra: bytearray, w: int, h: int) -> bytes:
    row_size = (w * 4 + 3) // 4 * 4
    pad = row_size - w * 4
    pixel_size = row_size * h
    off = 14 + 40
    filesize = off + pixel_size
    out = bytearray()
    out += b"BM"
    out += struct.pack("<IHHI", filesize, 0, 0, off)
    out += struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, BI_RGB, pixel_size,
                       2835, 2835, 0, 0)
    zero = b"\x00" * pad
    for y in range(h):
        out += bgra[y * w * 4:(y + 1) * w * 4]
        out += zero
    return bytes(out)


# ---------------------------------------------------------------- JPEG（GDI+）

_gplus_token = ctypes.c_ulong(0)
_gplus_started = False


def _gdiplus_start():
    global _gplus_started
    if _gplus_started:
        return True
    inp = GdiplusStartupInput()
    inp.GdiplusVersion = 1
    out = GdiplusStartupOutput()
    status = gplus.GdiplusStartup(ctypes.byref(_gplus_token),
                                  ctypes.byref(inp), ctypes.byref(out))
    if status == 0:
        _gplus_started = True
    return _gplus_started


def _save_jpeg_gdiplus(img: Image, path: str, quality: int = 90) -> bool:
    if not _gdiplus_start():
        return False
    hdc = u32.GetDC(0)
    memdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, img.w, img.h)
    g32.SelectObject(memdc, bmp)
    tmp = ctypes.create_string_buffer(bytes(img.data), len(img.data))
    g32.SetDIBits(memdc, bmp, 0, img.h, tmp,
                  ctypes.byref(_bmi(img.w, img.h)), DIB_RGB_COLORS)
    bitmap = ctypes.c_void_p()
    status = gplus.GdipCreateBitmapFromHBITMAP(bmp, 0, ctypes.byref(bitmap))
    g32.DeleteObject(bmp)
    g32.DeleteDC(memdc)
    u32.ReleaseDC(0, hdc)
    if status != 0 or not bitmap:
        return False
    quality_val = ctypes.c_ulong(int(quality))
    enc = EncoderParameters()
    enc.Count = 1
    enc.Parameter[0].Guid = ENCODER_QUALITY_GUID
    enc.Parameter[0].NumberOfValues = 1
    enc.Parameter[0].Type = 4  # EncoderParameterValueTypeLong
    enc.Parameter[0].Value = ctypes.cast(ctypes.byref(quality_val),
                                         ctypes.c_void_p)
    status = gplus.GdipSaveImageToFile(bitmap, path,
                                       ctypes.byref(JPEG_CLSID),
                                       ctypes.byref(enc))
    gplus.GdipDisposeImage(bitmap)
    return status == 0


# ---------------------------------------------------------------- 剪贴板

def _clipboard_set_image(img: Image) -> bool:
    """把图像放进剪贴板（CF_DIB）。"""
    w, h = img.w, img.h
    row_size = w * 4
    dib_size = 40 + row_size * h
    handle = k32.GlobalAlloc(0x0002, dib_size)      # GMEM_MOVEABLE
    if not handle:
        return False
    ptr = k32.GlobalLock(handle)
    try:
        ctypes.memmove(ptr, ctypes.byref(_bmi(w, h).bmiHeader), 40)
        ctypes.memmove(ptr + 40, bytes(img.data), len(img.data))
    finally:
        k32.GlobalUnlock(handle)
    if not u32.OpenClipboard(0):
        k32.GlobalFree(handle)
        return False
    try:
        u32.EmptyClipboard()
        u32.SetClipboardData(8, handle)             # CF_DIB
    finally:
        u32.CloseClipboard()
    return True
