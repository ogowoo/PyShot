# -*- coding: utf-8 -*-
"""wineditor.py —— 标注编辑器（Tkinter）：画布 + 工具轨道 + 顶栏 + 标签页 + 状态栏。

数据模型：shapes 是 winshapes 的 Shape 列表（图像像素坐标）。
交互渲染：Tk Canvas 上按 zoom 显示；最终导出用 GDI 把 shapes 画到原图上。
"""
import ctypes
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk

import winimg as wi
import wintk
import winshapes as ws

PALETTE = ["#e53935", "#ff8a00", "#ffd600", "#43a047", "#00acc1",
           "#1e88e5", "#8e24aa", "#ffffff", "#000000"]
DARK = "#2b2e33"


class Doc:
    """一个编辑文档（一张图 + 它的标注与撤销栈）——对应一个标签页。"""

    def __init__(self, image: wi.Image, name: str):
        self.image = image
        self.name = name
        self.shapes = []
        self.undo = []
        self.redo = []
        self.crop_rect = None


class Editor:
    """标注编辑器窗口（支持多标签页）。"""

    def __init__(self, image: wi.Image, on_save=None, on_copy=None,
                 on_close=None, on_capture=None):
        self.docs = [Doc(image.copy(), "截图 1")]
        self.cur = 0
        self.on_save = on_save
        self.on_copy = on_copy
        self.on_close = on_close
        self.on_capture = on_capture

        self.tool = "select"
        self.color = PALETTE[0]
        self.pen_width = 3
        self.font_size = 18
        self.step_diameter = 36
        self.step_counter = 1
        self.zoom = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self._selected = None
        self._drag = None
        self._draw_shape = None
        self._pan_start = None
        self._text_entry = None
        self._sel_items = []
        self._photo = None
        self._tab_widgets = []

        self.win = tk.Toplevel()
        self.win.title("PyShot 编辑器")
        self.win.configure(bg=wintk.BG)
        self.win.geometry(f"{max(900, image.w + 240)}x"
                          f"{max(600, image.h + 140)}")
        wintk.apply_theme(self.win)
        self.win.minsize(560, 420)

        self._build_ui()
        self._render_all()
        self._bind()
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    # ---------- 文档/标签页 ----------
    @property
    def doc(self) -> Doc:
        return self.docs[self.cur]

    @property
    def image(self) -> wi.Image:
        return self.doc.image

    @image.setter
    def image(self, value):
        self.doc.image = value

    @property
    def shapes(self):
        return self.doc.shapes

    @shapes.setter
    def shapes(self, value):
        self.doc.shapes = value

    @property
    def undo_stack(self):
        return self.doc.undo

    @property
    def redo_stack(self):
        return self.doc.redo

    @property
    def _crop_rect(self):
        return self.doc.crop_rect

    @_crop_rect.setter
    def _crop_rect(self, value):
        self.doc.crop_rect = value

    def add_document(self, image: wi.Image, name: str | None = None):
        """新增一个标签页（FSCapture 式：多次截图累积在一个编辑器里）。"""
        n = len(self.docs) + 1
        self.docs.append(Doc(image.copy(), name or f"截图 {n}"))
        self.cur = len(self.docs) - 1
        self._selected = None
        self._drag = None
        self._zoom_fit()
        self._render_all()
        self._build_tabs()
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except tk.TclError:
            pass

    def close_document(self, index: int):
        if len(self.docs) <= 1:
            self.close()
            return
        self.docs.pop(index)
        self.cur = min(self.cur, len(self.docs) - 1)
        self._selected = None
        self._render_all()
        self._build_tabs()

    def _switch_document(self, index: int):
        if index == self.cur or not (0 <= index < len(self.docs)):
            return
        self._finish_text_edit()
        self.cur = index
        self._selected = None
        self._render_all()
        self._build_tabs()

    def _build_tabs(self):
        for w in self._tab_widgets:
            w.destroy()
        self._tab_widgets = []
        only = len(self.docs) <= 1
        for i, d in enumerate(self.docs):
            active = (i == self.cur)
            holder = tk.Frame(self.tabbar, bg=wintk.BG if active
                              else wintk.SURFACE)
            holder.pack(side="left", padx=(0, 2))
            lab = tk.Label(holder, text=d.name, bg=wintk.BG if active
                           else wintk.SURFACE,
                           fg=wintk.TEXT if active else wintk.TEXT_DIM,
                           font=wintk.FONT_UI, padx=12, pady=6,
                           cursor="hand2")
            lab.pack(side="left")
            lab.bind("<Button-1>", lambda e, idx=i: self._switch_document(idx))
            if active:
                tk.Frame(holder, bg=wintk.ACCENT, height=2).pack(
                    side="bottom", fill="x")
            if not only:
                x = tk.Label(holder, text="✕", bg=wintk.BG if active
                             else wintk.SURFACE, fg=wintk.TEXT_DIM,
                             font=("Segoe UI", 9), padx=4, cursor="hand2")
                x.pack(side="left")
                x.bind("<Button-1>",
                       lambda e, idx=i: self.close_document(idx))
            self._tab_widgets.append(holder)
        add = tk.Label(self.tabbar, text="＋", bg=wintk.SURFACE,
                       fg=wintk.TEXT_DIM, font=("Segoe UI", 11), padx=8,
                       pady=4, cursor="hand2")
        add.pack(side="left", padx=2)
        wintk.attach_tooltip(add, "截取新区域并新增标签页")
        add.bind("<Button-1>", lambda e: self._on_capture())
        self._tab_widgets.append(add)

    # ---------------------------------------------------------------- UI 构建

    def _build_ui(self):
        # 顶栏
        top = tk.Frame(self.win, bg=wintk.SURFACE)
        top.pack(fill="x")
        top_inner = tk.Frame(top, bg=wintk.SURFACE)
        top_inner.pack(fill="x", padx=8, pady=6)

        shot = wintk.top_bar_button(
            top_inner, "  截图", accent=True,
            tooltip="截取新区域（编辑器会先最小化，截完回来）")
        shot._icon = wintk.make_icon_photo("camera", (255, 255, 255))
        shot.config(image=shot._icon, compound="left")
        shot.config(command=self._on_capture)
        shot.pack(side="left", padx=(0, 6))
        self._sep(top_inner)

        # 颜色
        tk.Label(top_inner, text="颜色", bg=wintk.SURFACE,
                 fg=wintk.TEXT_DIM, font=wintk.FONT_UI).pack(side="left",
                                                             padx=(4, 4))
        self.swatch_frame = tk.Frame(top_inner, bg=wintk.SURFACE)
        self.swatch_frame.pack(side="left")
        self.swatches = []
        for hexs in PALETTE:
            b = tk.Button(self.swatch_frame, width=2, height=1,
                          bg=hexs, relief="flat", bd=0,
                          activebackground=hexs,
                          command=lambda c=hexs: self._set_color(c))
            b.pack(side="left", padx=1)
            self.swatches.append((hexs, b))
        more = tk.Button(self.swatch_frame, text="…", width=2,
                         bg=wintk.SURFACE_2, fg=wintk.TEXT, relief="flat",
                         bd=0, command=self._pick_color)
        more.pack(side="left", padx=2)
        self._sep(top_inner)

        self.width_spin = self._spin(top_inner, "线宽", 1, 20, self.pen_width,
                                     self._on_width)
        self.font_spin = self._spin(top_inner, "字号", 10, 96, self.font_size,
                                    self._on_font)
        self.step_spin = self._spin(top_inner, "序号", 16, 240,
                                    self.step_diameter, self._on_step)
        self._sep(top_inner)

        # 撤销 / 重做
        self.btn_undo = self._icon_btn(top_inner, "undo",
                                       lambda: self._undo(), "撤销 (Ctrl+Z)")
        self.btn_redo = self._icon_btn(top_inner, "redo",
                                       lambda: self._redo(), "重做 (Ctrl+Y)")
        self._sep(top_inner)

        for label, fn, tip in [
                ("应用裁剪", self._apply_crop, "应用裁剪框 (Enter)"),
                ("复制", self._copy, "复制到剪贴板 (Ctrl+C)"),
                ("保存", self._save, "保存为文件 (Ctrl+S)"),
                ("关闭", self.close, "关闭编辑器 (Esc)")]:
            b = wintk.top_bar_button(top_inner, label, command=fn, tooltip=tip)
            b.pack(side="left", padx=2)

        # 主区：左工具轨道 + 画布
        main = tk.Frame(self.win, bg=wintk.BG)
        main.pack(fill="both", expand=True)

        rail = tk.Frame(main, bg=wintk.SURFACE, width=56)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self._build_rail(rail)

        # 标签页栏
        self.tabbar = tk.Frame(main, bg=wintk.SURFACE)
        self.tabbar.pack(side="top", fill="x")
        self._build_tabs()

        # 画布（滚动）
        canvas_frame = tk.Frame(main, bg=BG_DARK)
        canvas_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, bg=DARK, highlightthickness=0,
                                cursor="crosshair")
        self.vbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                  command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(main_frame2 := main, orient="horizontal",
                                  command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set,
                              xscrollcommand=self.hbar.set)
        self.hbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vbar.pack(side="right", fill="y")

        # 状态栏
        sb = tk.Frame(self.win, bg=wintk.SURFACE)
        sb.pack(fill="x", side="bottom")
        self.status_label = tk.Label(sb, text="", bg=wintk.SURFACE,
                                     fg=wintk.TEXT_DIM, font=wintk.FONT_SMALL,
                                     anchor="w")
        self.status_label.pack(side="left", padx=8)
        # 缩放控件（右侧）
        zoom = tk.Frame(sb, bg=wintk.SURFACE)
        zoom.pack(side="right", padx=6, pady=2)
        wintk.top_bar_button(zoom, "−", command=lambda: self._zoom_by(1 / 1.2),
                             tooltip="缩小").pack(side="left", padx=1)
        self.zoom_label = tk.Label(zoom, text="100%", bg=wintk.SURFACE,
                                   fg="#ffffff", font=("Segoe UI", 10, "bold"),
                                   width=6, anchor="center")
        self.zoom_label.pack(side="left")
        wintk.top_bar_button(zoom, "＋", command=lambda: self._zoom_by(1.2),
                             tooltip="放大").pack(side="left", padx=1)
        self._sep(zoom, horizontal=False)
        wintk.top_bar_button(zoom, "100%", command=lambda: self._set_zoom(1.0),
                             tooltip="实际像素").pack(side="left", padx=1)
        wintk.top_bar_button(zoom, "适应", command=self._zoom_fit,
                             tooltip="适应窗口").pack(side="left", padx=1)

        self._update_status()

    def _build_rail(self, rail):
        self.tool_btns = {}
        groups = [["select"], ["rect", "ellipse", "line", "arrow", "pen"],
                  ["step", "text", "highlight", "mosaic"], ["pick", "crop"]]
        first = True
        for group in groups:
            if not first:
                tk.Frame(rail, bg=wintk.BORDER, height=1).pack(
                    fill="x", padx=10, pady=5)
            first = False
            for tid in group:
                icon = wintk.make_icon_photo(tid, (170, 175, 185))
                b = tk.Label(rail, image=icon, bg=wintk.SURFACE, width=42,
                             height=40, cursor="hand2")
                b._icon = icon
                b.bind("<Button-1>", lambda e, t=tid: self.set_tool(t))
                b.bind("<Enter>", lambda e, t=tid: self._tool_hover(t, True))
                b.bind("<Leave>", lambda e, t=tid: self._tool_hover(t, False))
                b.pack(pady=2)
                self.tool_btns[tid] = (b, icon)
        self.set_tool("select")

    def _tool_hover(self, tid, hover):
        btn, _ = self.tool_btns[tid]
        if tid == self.tool:
            return
        btn.configure(bg=wintk.SURFACE_2 if hover else wintk.SURFACE)

    def _sep(self, parent, horizontal=True):
        if horizontal:
            tk.Frame(parent, bg=wintk.BORDER_STRONG, width=1).pack(
                side="left", fill="y", padx=6, pady=8)
        else:
            tk.Frame(parent, bg=wintk.BORDER_STRONG, height=18, width=1).pack(
                side="left", padx=3, pady=2)

    def _spin(self, parent, label, frm, to, val, cmd):
        box = tk.Frame(parent, bg=wintk.SURFACE)
        box.pack(side="left", padx=4)
        tk.Label(box, text=label, bg=wintk.SURFACE, fg=wintk.TEXT_DIM,
                 font=wintk.FONT_UI).pack(side="left")
        sb = ttk.Spinbox(box, from_=frm, to=to, width=4, command=cmd,
                         font=wintk.FONT_UI)
        sb.set(val)
        sb.bind("<<Increment>>", lambda e: cmd())
        sb.bind("<<Decrement>>", lambda e: cmd())
        sb.bind("<FocusOut>", lambda e: cmd())
        sb.pack(side="left", padx=3)
        return sb

    def _icon_btn(self, parent, icon_name, cmd, tip):
        icon = wintk.make_icon_photo(icon_name, (200, 205, 215))
        b = tk.Button(parent, image=icon, command=cmd, relief="flat", bd=0,
                      bg=wintk.SURFACE, activebackground=wintk.SURFACE_2,
                      cursor="hand2", width=34, height=30)
        b._icon = icon
        b.pack(side="left", padx=2)
        wintk.attach_tooltip(b, tip)
        return b

    # ---------------------------------------------------------------- 绑定

    def _bind(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<ButtonPress-3>", lambda e: self._cancel_drawing())
        c.bind("<Double-Button-1>", lambda e: self._finish_text_edit())
        self.win.bind("<Escape>", lambda e: self._escape())
        self.win.bind("<Return>", lambda e: self._enter())
        self.win.bind("<Delete>", lambda e: self._delete_selected())
        self.win.bind("<BackSpace>", lambda e: self._delete_selected())
        self.win.bind("<Control-z>", lambda e: self._undo())
        self.win.bind("<Control-y>", lambda e: self._redo())
        self.win.bind("<Control-c>", lambda e: self._copy())
        self.win.bind("<Control-s>", lambda e: self._save())
        self.win.bind("<Control-a>", lambda e: self._select_all())
        self.canvas.bind("<MouseWheel>", self._wheel_zoom)
        self.win.bind("<Configure>", lambda e: self._on_resize())

    # ---------------------------------------------------------------- 工具

    def set_tool(self, tool):
        self.tool = tool
        for tid, (btn, icon) in self.tool_btns.items():
            if tid == tool:
                btn.configure(bg=wintk.ACCENT_SOFT)
                # 强调色图标
                new_icon = wintk.make_icon_photo(tid, (92, 164, 255))
                btn.configure(image=new_icon)
                btn._icon = new_icon
            else:
                btn.configure(bg=wintk.SURFACE)
                btn.configure(image=icon)
        cursors = {"select": "arrow", "text": "xterm", "pick": "crosshair",
                   "crop": "crosshair"}
        if hasattr(self, "canvas"):
            self.canvas.config(cursor=cursors.get(tool, "crosshair"))
        self._update_status()

    def _set_color(self, hexs):
        self.color = hexs
        for c, b in self.swatches:
            b.configure(highlightthickness=2,
                        highlightbackground="#ffffff" if c == hexs else hexs)
        if self._selected is not None:
            self._push_undo()
            self._selected.color = hexs
            self._render_all()

    def _pick_color(self):
        c = colorchooser.askcolor(initialcolor=self.color, parent=self.win)
        if c and c[1]:
            self._set_color(c[1])

    def _on_width(self):
        self.pen_width = int(float(self.width_spin.get()))
        if self._selected is not None:
            self._push_undo()
            self._selected.width = self.pen_width
            self._render_all()

    def _on_font(self):
        self.font_size = int(float(self.font_spin.get()))

    def _on_step(self):
        self.step_diameter = int(float(self.step_spin.get()))
        if isinstance(self._selected, ws.StepShape):
            self._push_undo()
            self._selected.diameter = float(self.step_diameter)
            self._render_all()

    # ---------------------------------------------------------------- 坐标换算

    def _to_image(self, cx, cy):
        """画布坐标 → 图像像素坐标。"""
        return (cx - self.ox) / self.zoom, (cy - self.oy) / self.zoom

    def _to_canvas(self, ix, iy):
        return self.ox + ix * self.zoom, self.oy + iy * self.zoom

    # ---------------------------------------------------------------- 交互

    def _press(self, e):
        self._finish_text_edit()
        ix, iy = self._to_image(self.canvas.canvasx(e.x),
                                self.canvas.canvasy(e.y))
        if self.tool == "select":
            self._select_at(ix, iy, e)
            return
        if self.tool == "text":
            self._start_text_edit(ix, iy)
            return
        if self.tool == "crop":
            self._drag = ("crop", ix, iy)
            return
        # 绘制类工具
        self._push_undo()
        if self.tool in ("rect", "ellipse", "highlight", "mosaic"):
            self._drag = (self.tool, ix, iy)
        elif self.tool in ("line", "arrow"):
            self._drag = (self.tool, ix, iy)
        elif self.tool == "pen":
            sh = ws.PenShape(self.color, self.pen_width, [(ix, iy)])
            self.shapes.append(sh)
            self._draw_shape = sh
            self._drag = ("pen", ix, iy)
        elif self.tool == "step":
            sh = ws.StepShape(self.color, 2, (ix, iy), self.step_counter,
                              self.step_diameter, self.font_size)
            self.shapes.append(sh)
            self.step_counter += 1
            self._render_all()
            return

    def _drag(self, e):
        ix, iy = self._to_image(self.canvas.canvasx(e.x),
                                self.canvas.canvasy(e.y))
        if self._drag and self._drag[0] == "select-move":
            dx = ix - self._drag[1]
            dy = iy - self._drag[2]
            if self._selected is not None:
                self._selected.move_by(dx, dy)
                self._drag = ("select-move", ix, iy)
                self._render_all()
            return
        if self._drag and self._drag[0] == "resize":
            index = self._drag[3]
            self._selected.resize_by_handle(index, (ix, iy))
            self._render_all()
            return
        if self._drag and self._drag[0] == "pen":
            self._draw_shape.add_point((ix, iy))
            self._render_all()
            return
        if self._drag and self._drag[0] in ("rect", "ellipse", "highlight",
                                            "mosaic", "crop"):
            _, ox, oy = self._drag
            self._show_preview(ox, oy, ix, iy)
            return
        if self._drag and self._drag[0] in ("line", "arrow"):
            _, ox, oy = self._drag
            self._show_preview(ox, oy, ix, iy)

    def _release(self, e):
        ix, iy = self._to_image(self.canvas.canvasx(e.x),
                                self.canvas.canvasy(e.y))
        if self._drag is None:
            return
        kind = self._drag[0]
        if kind == "select-move" or kind == "resize":
            self._drag = None
            self._render_all()
            return
        if kind == "pen":
            self._drag = None
            self._draw_shape = None
            self._render_all()
            return
        if kind in ("rect", "ellipse", "highlight", "mosaic", "crop",
                    "line", "arrow"):
            _, ox, oy = self._drag
            self._drag = None
            self._delete_preview()
            x0, y0 = min(ox, ix), min(oy, iy)
            w, h = abs(ix - ox), abs(iy - oy)
            if w < 4 or h < 4:
                if self.undo_stack:
                    self.undo_stack.pop()
                self._render_all()
                return
            if kind == "crop":
                self._crop_rect = (x0, y0, w, h)
                self._render_all()
                return
            sh = self._make_shape(kind, (x0, y0, w, h))
            self.shapes.append(sh)
            self._render_all()

    def _make_shape(self, kind, rect):
        if kind == "rect":
            return ws.RectShape(self.color, self.pen_width, rect)
        if kind == "ellipse":
            return ws.EllipseShape(self.color, self.pen_width, rect)
        if kind == "highlight":
            return ws.HighlightShape(self.color, self.pen_width, rect)
        if kind == "mosaic":
            return ws.MosaicShape(self.color, self.pen_width, rect)
        if kind == "line":
            x, y, w, h = rect
            return ws.LineShape(self.color, self.pen_width, (x, y),
                                (x + w, y + h))
        if kind == "arrow":
            x, y, w, h = rect
            return ws.ArrowShape(self.color, self.pen_width, (x, y),
                                 (x + w, y + h))

    # ---------------------------------------------------------------- 选中/移动

    def _select_at(self, ix, iy, e):
        # 命中句柄？
        if self._selected is not None:
            for i, (hx, hy) in enumerate(self._selected.handles()):
                cx, cy = self._to_canvas(hx, hy)
                if abs(self.canvas.canvasx(e.x) - cx) < 8 \
                        and abs(self.canvas.canvasy(e.y) - cy) < 8:
                    self._drag = ("resize", ix, iy, i)
                    return
        # 命中图形？
        for sh in reversed(self.shapes):
            if sh.contains(ix, iy):
                self._selected = sh
                self._drag = ("select-move", ix, iy)
                self._render_all()
                return
        self._selected = None
        self._drag = None
        self._render_all()

    def _delete_selected(self):
        if self._selected is not None and self._selected in self.shapes:
            self._push_undo()
            self.shapes.remove(self._selected)
            self._selected = None
            self._render_all()

    def _select_all(self):
        if self.shapes:
            self._selected = self.shapes[-1]
            self._render_all()

    # ---------------------------------------------------------------- 预览/文字

    def _show_preview(self, ox, oy, ix, iy):
        self._delete_preview()
        kind = self._drag[0]
        if kind in ("rect", "ellipse", "highlight", "mosaic", "crop"):
            x0, y0 = min(ox, ix), min(oy, iy)
            x1, y1 = max(ox, ix), max(oy, iy)
            cx0, cy0 = self._to_canvas(x0, y0)
            cx1, cy1 = self._to_canvas(x1, y1)
            color = "#ffffff" if kind == "crop" else self.color
            dash = (5, 4) if kind in ("highlight", "mosaic") else None
            self._preview = self.canvas.create_rectangle(
                cx0, cy0, cx1, cy1, outline=color, width=2, dash=dash)
        elif kind in ("line", "arrow"):
            cx0, cy0 = self._to_canvas(ox, oy)
            cx1, cy1 = self._to_canvas(ix, iy)
            self._preview = self.canvas.create_line(
                cx0, cy0, cx1, cy1, fill=self.color, width=self.pen_width)

    def _delete_preview(self):
        if getattr(self, "_preview", None):
            self.canvas.delete(self._preview)
            self._preview = None

    def _start_text_edit(self, ix, iy):
        cx, cy = self._to_canvas(ix, iy)
        entry = tk.Text(self.canvas, height=3, width=24, font=("Microsoft YaHei UI",
                                                             self.font_size),
                        fg=self.color, bg="#ffffff", wrap="word", bd=2,
                        relief="solid")
        win = self.canvas.create_window(cx, cy, anchor="nw", window=entry,
                                        width=int(240 * self.zoom))
        self._text_entry = (ix, iy, entry, win)
        entry.focus_set()

    def _finish_text_edit(self):
        if self._text_entry is None:
            return
        ix, iy, entry, win = self._text_entry
        text = entry.get("1.0", "end").strip()
        self.canvas.delete(win)
        entry.destroy()
        self._text_entry = None
        if text:
            self._push_undo()
            self.shapes.append(ws.TextShape(self.color, 2, (ix, iy), text,
                                            self.font_size))
            self._render_all()

    def _cancel_drawing(self):
        self._delete_preview()
        self._drag = None
        self._selected = None
        self._finish_text_edit()
        self._render_all()

    def _escape(self):
        if self._text_entry is not None:
            self._finish_text_edit()
            return
        if getattr(self, "_crop_rect", None):
            self._crop_rect = None
            self._render_all()
            return
        if self._selected is not None:
            self._selected = None
            self._render_all()
            return
        self.close()

    def _enter(self):
        if getattr(self, "_crop_rect", None):
            self._apply_crop()
        elif self._text_entry is not None:
            self._finish_text_edit()

    # ---------------------------------------------------------------- 撤销/重做

    def _push_undo(self):
        import copy
        self.undo_stack.append(copy.deepcopy(self.shapes))
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._update_status()

    def _undo(self):
        if not self.undo_stack:
            return
        import copy
        self.redo_stack.append(copy.deepcopy(self.shapes))
        self.shapes = self.undo_stack.pop()
        self._selected = None
        self._render_all()

    def _redo(self):
        if not self.redo_stack:
            return
        import copy
        self.undo_stack.append(copy.deepcopy(self.shapes))
        self.shapes = self.redo_stack.pop()
        self._selected = None
        self._render_all()

    # ---------------------------------------------------------------- 裁剪

    def _apply_crop(self):
        if not getattr(self, "_crop_rect", None):
            return
        x, y, w, h = self._crop_rect
        self.image = self.image.crop(int(x), int(y), int(w), int(h))
        # 把图形平移到裁剪后的坐标
        for sh in self.shapes:
            sh.move_by(-x, -y)
        self._crop_rect = None
        self._selected = None
        self._render_all()

    # ---------------------------------------------------------------- 缩放

    def _set_zoom(self, z):
        self.zoom = max(0.1, min(6.0, z))
        self._render_all()

    def _zoom_by(self, factor):
        self._set_zoom(self.zoom * factor)

    def _zoom_fit(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw > 10 and ch > 10:
            self._set_zoom(min((cw - 40) / self.image.w,
                               (ch - 40) / self.image.h))

    def _wheel_zoom(self, e):
        if e.state & 0x4:      # Ctrl
            self._set_zoom(self.zoom * (1.1 if e.delta > 0 else 1 / 1.1))

    def _on_resize(self):
        pass

    # ---------------------------------------------------------------- 渲染

    def _render_all(self):
        """重画整张画布：图像 + 图形（Tk 画布项）+ 选中框。"""
        c = self.canvas
        c.delete("all")
        # 图像
        disp = self.image
        if self.zoom != 1.0:
            disp = self._scale_for_display(self.image)
        self._photo = tk.PhotoImage(data=disp.to_ppm())
        c.create_image(self.ox, self.oy, anchor="nw", image=self._photo,
                       tags="base")
        # 裁剪框（最上层背景之下）
        # 图形
        for sh in self.shapes:
            sh.draw_tk(c, self.ox, self.oy, self.zoom)
        # 裁剪框
        if getattr(self, "_crop_rect", None):
            x, y, w, h = self._crop_rect
            cx0, cy0 = self._to_canvas(x, y)
            cx1, cy1 = self._to_canvas(x + w, y + h)
            c.create_rectangle(cx0, cy0, cx1, cy1, outline="#ffffff", width=2,
                               dash=(6, 4), tags="crop")
        # 选中框 + 句柄
        if self._selected is not None:
            x0, y0, x1, y1 = self._selected.bounding()
            cx0, cy0 = self._to_canvas(x0 - 2, y0 - 2)
            cx1, cy1 = self._to_canvas(x1 + 2, y1 + 2)
            c.create_rectangle(cx0, cy0, cx1, cy1, outline=wintk.ACCENT,
                               width=1.5, tags="selbox")
            for hx, hy in self._selected.handles():
                chx, chy = self._to_canvas(hx, hy)
                c.create_rectangle(chx - 4, chy - 4, chx + 4, chy + 4,
                                   fill="#ffffff", outline=wintk.ACCENT,
                                   tags="selhandle")
        c.configure(scrollregion=c.bbox("all"))
        self._update_status()

    def _scale_for_display(self, img: wi.Image) -> wi.Image:
        """按 zoom 缩放（显示用，GDI StretchBlt HALFTONE）。"""
        nw = max(1, int(img.w * self.zoom))
        nh = max(1, int(img.h * self.zoom))
        hdc = wi.u32.GetDC(0)
        src = wi.g32.CreateCompatibleDC(hdc)
        src_bmp = wi.g32.CreateCompatibleBitmap(hdc, img.w, img.h)
        wi.g32.SelectObject(src, src_bmp)
        src_buf = ctypes.create_string_buffer(bytes(img.data), len(img.data))
        wi.g32.SetDIBits(src, src_bmp, 0, img.h, src_buf,
                         ctypes.byref(wi._bmi(img.w, img.h)), 0)
        dst = wi.g32.CreateCompatibleDC(hdc)
        dst_bmp = wi.g32.CreateCompatibleBitmap(hdc, nw, nh)
        wi.g32.SelectObject(dst, dst_bmp)
        wi.g32.SetStretchBltMode(dst, 4)          # HALFTONE
        wi.g32.StretchBlt(dst, 0, 0, nw, nh, src, 0, 0, img.w, img.h,
                          wi.SRCCOPY)
        # 目标缓冲必须按缩放后的尺寸分配
        dst_buf = ctypes.create_string_buffer(nw * nh * 4)
        wi.g32.GetDIBits(dst, dst_bmp, 0, nh, dst_buf,
                         ctypes.byref(wi._bmi(nw, nh)), 0)
        out = wi.Image(nw, nh, dst_buf.raw, dpr=img.dpr)
        for o in (src_bmp, dst_bmp):
            wi.g32.DeleteObject(o)
        for dc in (src, dst):
            wi.g32.DeleteDC(dc)
        wi.u32.ReleaseDC(0, hdc)
        return out

    def _update_status(self):
        tool_names = dict(select="选择", rect="矩形", ellipse="椭圆",
                          line="直线", arrow="箭头", pen="画笔", step="序号",
                          text="文字", highlight="高亮", mosaic="马赛克",
                          pick="取色", crop="裁剪")
        name = tool_names.get(self.tool, self.tool)
        if hasattr(self, "status_label"):
            self.status_label.config(
                text=f"工具：{name}   {self.doc.name}  "
                     f"{self.image.w}×{self.image.h}")
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text=f"{int(self.zoom * 100)}%")

    # ---------------------------------------------------------------- 导出

    def flatten(self) -> wi.Image:
        """把图形渲染到图像上，返回最终图。"""
        out = self.image.copy()
        r = out.renderer()
        for sh in self.shapes:
            if isinstance(sh, (ws.HighlightShape, ws.MosaicShape)):
                sh.draw_gdi(None, out)
            else:
                sh.draw_gdi(r, out)
        r.close()
        return out

    def _copy(self):
        img = self.flatten()
        img.copy_to_clipboard()
        self.status_label.config(text="已复制到剪贴板")

    def _save(self):
        path = filedialog.asksaveasfilename(
            parent=self.win, defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("BMP", "*.bmp")],
            initialfile="PyShot.png")
        if not path:
            return
        img = self.flatten()
        if path.lower().endswith((".jpg", ".jpeg")):
            img.save_jpeg(path, 90)
        elif path.lower().endswith(".bmp"):
            img.save_bmp(path)
        else:
            img.save_png(path)
        self.status_label.config(text=f"已保存：{path}")

    def _on_capture(self):
        if self.on_capture:
            self.on_capture()

    def close(self):
        if self.on_close:
            self.on_close()
        self.win.destroy()


BG_DARK = "#15161a"
