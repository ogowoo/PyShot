# -*- coding: utf-8 -*-
"""winmain.py —— PyShot 主程序（Tkinter + ctypes，零第三方依赖）。

托盘常驻 → 全局热键 / 托盘菜单 → 截图覆盖层 → 标注编辑器 → 复制/保存/贴图。
滚动长截图支持滚轮 / 拖拽滚动条 / 按键 / 手动四种模式。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import winimg as wi
import wincapture as wc
import wintk
import winsnipper
import winscroller
import wineditor

user32 = wi.u32

# ---------------------------------------------------------------- 全局热键

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
WM_HOTKEY = 0x0312
DEFAULT_HOTKEYS = ["ctrl+alt+x", "ctrl+shift+x", "ctrl+alt+f9",
                   "ctrl+shift+f9"]


def _parse_hotkey(spec: str):
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


# ---------------------------------------------------------------- 贴图窗口

class PinWindow:
    """把图片钉在桌面最上层（Snipaste 风格），可拖动、滚轮缩放、双击关闭。"""

    def __init__(self, root, image: wi.Image):
        self.image = image
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#3d8bfd")
        self.photo = tk.PhotoImage(data=image.to_ppm(), master=self.win)
        self.label = tk.Label(self.win, image=self.photo, bd=0,
                              bg="#000000", cursor="fleur")
        self.label.pack(padx=2, pady=2)
        self.win.geometry(f"+{max(20, image.w // 2)}+{max(20, image.h // 3)}")
        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._drag)
        self.label.bind("<Double-Button-1>", lambda e: self.close())
        self.label.bind("<Button-3>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self._d = None

    def _press(self, e):
        self._d = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        if self._d:
            self.win.geometry(f"+{e.x_root - self._d[0]}+{e.y_root - self._d[1]}")

    def close(self):
        self.win.destroy()


# ---------------------------------------------------------------- 主程序

class PyShotTk:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("PyShot")
        wintk.apply_theme(self.root)
        self.editors = []
        self.pins = []
        self.scroller = None
        self.snipper = None
        self._minimized = []
        self._pending_scroll_mode = None
        self._busy = False

        self.tray = wintk.Win32Pump("PyShot 截图工具")
        self.tray.start(wintk.DEFAULT_HOTKEYS)
        self.hk = self.tray.hotkey
        self.tray.set_tooltip(
            f"PyShot 截图工具（{self.hk or '无热键'} 或双击图标截图）")
        self._poll_pump()
        self._notify("PyShot 已启动",
                     f"按 {self.hk or '双击托盘图标'} 开始截图，右键托盘图标看菜单")

    # ---------- Win32 消息泵（独立线程）→ Tk 事件 ----------
    def _poll_pump(self):
        """Tk 主线程轮询泵队列（跨线程只传数据，不碰 Tk 对象）。"""
        for kind, payload in self.tray.poll():
            if kind == "double":
                self.start_capture()
            elif kind == "menu":
                self._show_menu()
            elif kind == "hotkey":
                self.start_capture()
            elif kind == "error":
                self._notify("PyShot 启动异常", str(payload))
        try:
            self.root.after(60, self._poll_pump)
        except tk.TclError:
            pass

    # ---------- 通知 ----------
    def _notify(self, title, msg):
        try:
            self.tray.show_message(title, msg)
        except Exception:  # noqa: BLE001
            pass

    # ---------- 托盘 ----------
    def _show_menu(self):
        if getattr(self, "_menu_open", False):
            return                      # 菜单已弹出（模态），不重复弹
        self._menu_open = True
        m = tk.Menu(self.root, tearoff=0, bg=wintk.SURFACE_2, fg=wintk.TEXT,
                    activebackground=wintk.ACCENT, activeforeground="#ffffff",
                    bd=0, font=wintk.FONT_UI)
        m.add_command(label=f"截图（{self.hk or '无热键'}）",
                      command=self.start_capture)
        m.add_separator()
        m.add_command(label="滚动长截图（自动滚轮）",
                      command=lambda: self.start_scroll("wheel"))
        m.add_command(label="滚动长截图（拖拽滚动条）",
                      command=lambda: self.start_scroll("drag"))
        m.add_command(label="滚动长截图（按键翻页）",
                      command=lambda: self.start_scroll("key"))
        m.add_command(label="滚动长截图（手动滚动）",
                      command=lambda: self.start_scroll("manual"))
        m.add_separator()
        m.add_command(label="屏幕取色", command=self.start_pick)
        m.add_command(label="打开图片编辑…", command=self.open_image)
        m.add_command(label="打开编辑器", command=self.show_editor)
        m.add_separator()
        m.add_command(label="退出", command=self.quit)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()
            self._menu_open = False

    # ---------- 截图准备 ----------
    def _prepare_capture(self):
        self._minimized = []
        for ed in list(self.editors):
            try:
                if ed.win.state() == "normal":
                    ed.win.iconify()
                    self._minimized.append(ed)
            except tk.TclError:
                pass
        self.root.update()
        if self._minimized:
            import time
            time.sleep(0.18)

    def _restore_capture(self):
        for ed in self._minimized:
            try:
                ed.win.deiconify()
                ed.win.lift()
            except tk.TclError:
                pass
        self._minimized = []

    def _run_snipper(self, mode, on_ok, on_cancel=None):
        if self._busy:
            return
        self._busy = True
        self._prepare_capture()

        def done(result):
            self._busy = False
            self._restore_capture()
            on_ok(result)

        def cancel():
            self._busy = False
            self._restore_capture()
            if on_cancel:
                on_cancel()

        self.snipper = winsnipper.Snipper(self.root, mode, done, cancel)

    # ---------- 各功能入口 ----------
    def start_capture(self):
        self._run_snipper("region", self._on_region)

    def start_scroll(self, mode):
        self._pending_scroll_mode = mode
        self._run_snipper("scroll", self._on_scroll_region)

    def start_pick(self):
        def ok(color):
            if isinstance(color, tuple):
                r, g, b = color
                hexs = f"#{r:02X}{g:02X}{b:02X}"
                self.root.clipboard_clear()
                self.root.clipboard_append(hexs)
                self._notify("已复制色值", hexs)
        self._run_snipper("color", ok)

    def _on_region(self, result):
        if isinstance(result, wi.Image):
            self.open_editor(result)

    def _on_scroll_region(self, result):
        """结果是逻辑坐标的选区 (l, t, r, b)。"""
        mode = self._pending_scroll_mode or "wheel"
        self._pending_scroll_mode = None
        if not isinstance(result, tuple):
            return
        l, t, r, b = result
        dpr = wi.primary_dpi()
        region = (int(l * dpr), int(t * dpr), int((r - l) * dpr),
                  int((b - t) * dpr))
        if mode != "drag":
            self._start_scroll_capture(region, mode, None)
            return
        # 拖拽模式：再让用户点一下滚动条滑块，然后开始。
        # 用回调串起来 —— 不在回调里跑 while+update 的重入事件循环。
        self._busy = True

        def picked(pt):
            self._busy = False
            self.snipper = None
            if pt:
                self._start_scroll_capture(region, mode, pt)

        def cancelled():
            self._busy = False
            self.snipper = None

        self.snipper = winsnipper.Snipper(self.root, "point", picked, cancelled)

    def _start_scroll_capture(self, region, mode, anchor):
        sc = winscroller.ScrollCaptureTk(
            self.root, region, mode=mode, anchor=anchor,
            on_done=self._on_scroll_done, on_error=self._on_scroll_error,
            manual=(mode == "manual"))
        self.scroller = sc
        sc.start()

    def _on_scroll_done(self, image, note):
        self.scroller = None
        if note:
            self._notify("滚动截图完成", note)
        self.open_editor(image)

    def _on_scroll_error(self, msg):
        self.scroller = None
        self._notify("滚动截图失败", msg.replace("\n", " ")[:200])

    # ---------- 编辑器 ----------
    def open_editor(self, image: wi.Image):
        """已有编辑器就新增标签页（FSCapture 式），否则新建窗口。"""
        alive = []
        for ed in self.editors:
            try:
                if ed.win.winfo_exists():
                    alive.append(ed)
            except tk.TclError:
                pass
        self.editors = alive
        if self.editors:
            ed = self.editors[-1]
            try:
                ed.add_document(image)
                return
            except tk.TclError:
                self.editors.remove(ed)
        ed = wineditor.Editor(image, on_close=lambda: self._forget_editor(ed),
                              on_capture=self.start_capture)
        self.editors.append(ed)

    def _forget_editor(self, ed):
        if ed in self.editors:
            self.editors.remove(ed)

    def show_editor(self):
        if self.editors:
            ed = self.editors[-1]
            try:
                ed.win.deiconify()
                ed.win.lift()
                ed.win.focus_force()
            except tk.TclError:
                pass
        else:
            self.open_image()

    def open_image(self):
        path = filedialog.askopenfilename(
            title="打开图片编辑",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            img = _load_image_file(path)
        except Exception as ex:  # noqa: BLE001
            messagebox.showerror("打开失败", f"无法读取图片：{ex}")
            return
        self.open_editor(img)

    def pin(self, image: wi.Image):
        self.pins.append(PinWindow(self.root, image))

    # ---------- 退出 ----------
    def quit(self):
        try:
            self.tray.stop()
        except Exception:  # noqa: BLE001
            pass
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _load_image_file(path: str) -> wi.Image:
    """用 GDI+ 读图片文件（PNG/JPG/BMP）。"""
    import ctypes as C
    if not wi._gdiplus_start():
        raise RuntimeError("GDI+ 初始化失败")
    gp = wi.gplus
    gp.GdipCreateBitmapFromFile.argtypes = [C.c_wchar_p, C.c_void_p]
    gp.GdipCreateBitmapFromFile.restype = C.c_int
    gp.GdipCreateHBITMAPFromBitmap.argtypes = [C.c_void_p, C.c_void_p,
                                               C.c_uint]
    gp.GdipCreateHBITMAPFromBitmap.restype = C.c_int
    gp.GdipGetImageWidth.argtypes = [C.c_void_p, C.POINTER(C.c_uint)]
    gp.GdipGetImageHeight.argtypes = [C.c_void_p, C.POINTER(C.c_uint)]
    bmp_ptr = C.c_void_p()
    if gp.GdipCreateBitmapFromFile(path, C.byref(bmp_ptr)) != 0 or not bmp_ptr:
        raise RuntimeError("GDI+ 无法读取该文件")
    w = C.c_uint()
    h = C.c_uint()
    gp.GdipGetImageWidth(bmp_ptr, C.byref(w))
    gp.GdipGetImageHeight(bmp_ptr, C.byref(h))
    w, h = int(w.value), int(h.value)
    hbmp = C.c_void_p()
    gp.GdipCreateHBITMAPFromBitmap(bmp_ptr, C.byref(hbmp), 0xFF000000)
    gp.GdipDisposeImage(bmp_ptr)
    if not hbmp:
        raise RuntimeError("位图转换失败")
    hdc = wi.u32.GetDC(0)
    memdc = wi.g32.CreateCompatibleDC(hdc)
    wi.g32.SelectObject(memdc, hbmp)
    buf = C.create_string_buffer(w * h * 4)
    wi.g32.GetDIBits(memdc, hbmp, 0, h, buf, C.byref(wi._bmi(w, h)), 0)
    wi.g32.DeleteObject(hbmp)
    wi.g32.DeleteDC(memdc)
    wi.u32.ReleaseDC(0, hdc)
    return wi.Image(w, h, buf.raw)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check-deps" in argv:
        print("PyShot 依赖检查：")
        print(f"  内嵌依赖目录: {'有' if os.path.isdir(os.path.join(HERE, 'libs')) else '无（使用标准库）'}")
        print(f"  界面框架: tkinter（Python 标准库）")
        print(f"  Python: {sys.version.split()[0]}  解释器: {sys.executable}")
        return 0
    app = PyShotTk()
    if argv and os.path.isfile(argv[0]):
        try:
            app.open_editor(_load_image_file(argv[0]))
        except Exception as ex:  # noqa: BLE001
            print(f"打开失败：{ex}")
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
