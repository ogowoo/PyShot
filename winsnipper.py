# -*- coding: utf-8 -*-
"""winsnipper.py —— 全屏截图覆盖层（框选 / 取色 / 选点，带放大镜与提示）。

用 tkinter 实现：
- 冻结桌面（GDI 抓屏 + AlphaBlend 平滑压暗）作为背景
- 拖拽框选：选区高亮显示 + 尺寸标签 + 对齐参考线
- 放大镜：跟随光标显示局部放大
- Esc / 右键取消
"""
import tkinter as tk

import winimg as wi
import wintk

MAG_ZOOM = 9
MAG_CELL = 15
MAG_SIZE = MAG_CELL * MAG_ZOOM
GUIDE = "#4c9aff"


class Snipper:
    """全屏截图覆盖层。

    mode: "region" 框选截图 | "color" 取色 | "point" 选点 | "scroll" 滚动截图选区
    on_capture(image_or_color_or_point) / on_cancel() 回调。
    """

    def __init__(self, root: tk.Tk, mode: str, on_capture, on_cancel):
        self.mode = mode
        self.on_capture = on_capture
        self.on_cancel = on_cancel

        self.bg_img, (self.vx, self.vy) = wi.grab_virtual_desktop()
        self.dpr = self.bg_img.dpr
        self.dim_img = self.bg_img.darken_overlay()

        self._origin = None
        self._cur = None
        self._sel = None               # 当前选区（逻辑坐标）
        self._dragging = False
        self._finished = False
        self._last_crop_rect = None
        self._photo_bg = tk.PhotoImage(data=self.dim_img.to_ppm())
        self._photo_sel = None

        self.win = tk.Toplevel(root)
        self.win.configure(bg=wintk.BG)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)
        self.win.geometry(f"{self.win.winfo_screenwidth()}x"
                          f"{self.win.winfo_screenheight()}+{self.vx}+{self.vy}")
        self.win.config(cursor="crosshair")

        self.cv = tk.Canvas(self.win, highlightthickness=0, bg=wintk.BG,
                            cursor="crosshair")
        self.cv.pack(fill="both", expand=True)
        self.cv.create_image(0, 0, anchor="nw", image=self._photo_bg,
                             tags="bg")

        self._make_items()
        self._bind()
        self._update_hint()
        self.win.lift()
        self.win.focus_force()
        self.cv.focus_set()

    # ---------------------------------------------------------------- 画布项

    def _make_items(self):
        cv = self.cv
        # 选区高亮图
        self.sel_img_item = cv.create_image(0, 0, anchor="nw", tags="selimg")
        # 选区边框
        self.sel_rect_item = cv.create_rectangle(0, 0, 0, 0,
                                                 outline=GUIDE, width=2)
        # 尺寸标签
        self.size_item = cv.create_text(0, 0, anchor="nw", fill="#ffffff",
                                        font=("Consolas", 11, "bold"),
                                        text="")
        # 尺寸标签底
        self.size_bg_item = cv.create_rectangle(0, 0, 0, 0, fill="#000000",
                                                outline="")
        # 对齐参考线
        self.guide_h_item = cv.create_line(0, 0, 0, 0, fill=GUIDE, dash=(6, 4),
                                           width=1)
        self.guide_v_item = cv.create_line(0, 0, 0, 0, fill=GUIDE, dash=(6, 4),
                                           width=1)
        # 十字准线
        self.cross_h = cv.create_line(0, 0, 0, 0, fill=GUIDE, width=1)
        self.cross_v = cv.create_line(0, 0, 0, 0, fill=GUIDE, width=1)
        # 放大镜底 + 图
        self.mag_bg = cv.create_rectangle(0, 0, 0, 0, fill="#1e1f24",
                                          outline="#ffffff", width=2)
        self.mag_img_item = cv.create_image(0, 0, anchor="nw", tags="magimg")
        self.mag_center = cv.create_rectangle(0, 0, 0, 0, outline="#e53935",
                                              width=2)
        self._photo_mag = None
        # 顶部提示
        self.hint_bg = cv.create_rectangle(0, 0, 0, 0, fill="#000000",
                                           outline="")
        self.hint_item = cv.create_text(0, 0, anchor="n", fill="#ffffff",
                                        font=wintk.FONT_UI)

        for tag in ("selimg", "selrect", "sizebg", "size", "guideh", "guidev",
                    "crossh", "crossv", "magbg", "magimg", "magcenter",
                    "hintbg", "hint"):
            cv.itemconfigure(tag, state="hidden")

    def _bind(self):
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<ButtonPress-3>", lambda e: self.cancel())
        self.cv.bind("<Motion>", self._motion)
        self.win.bind("<Escape>", lambda e: self.cancel())

    # ---------------------------------------------------------------- 坐标换算

    def _to_logical(self, x, y):
        """物理像素 → 逻辑坐标（考虑虚拟桌面原点与 dpr）。"""
        return (x - self.vx) / self.dpr, (y - self.vy) / self.dpr

    def _to_physical(self, x, y):
        return int(x * self.dpr) + self.vx, int(y * self.dpr) + self.vy

    def _clamp_logical(self, x, y):
        w = self.cv.winfo_width()
        h = self.cv.winfo_height()
        return min(max(0.0, x), float(w)), min(max(0.0, y), float(h))

    # ---------------------------------------------------------------- 交互

    def _press(self, e):
        if self._finished:
            return
        x, y = self._clamp_logical(e.x, e.y)
        if self.mode == "color":
            self._pick_color(x, y)
            return
        if self.mode == "point":
            px, py = self._to_physical(x, y)
            self._finish()
            self.on_capture((px, py))
            return
        self._origin = (x, y)
        self._cur = (x, y)
        self._dragging = True
        self._sel = None

    def _drag(self, e):
        if not self._dragging:
            return
        x, y = self._clamp_logical(e.x, e.y)
        self._cur = (x, y)
        self._update_selection()
        self._motion(e)

    def _release(self, e):
        if not self._dragging:
            return
        self._dragging = False
        x, y = self._clamp_logical(e.x, e.y)
        x0, y0 = self._origin
        x1, y1 = min(x0, x), min(y0, y)
        x2, y2 = max(x0, x), max(y0, y)
        if (x2 - x1) < 6 or (y2 - y1) < 6:
            self._sel = None
            self._hide_selection()
            return
        self._sel = (x1, y1, x2, y2)
        self._confirm()

    def _motion(self, e):
        self._update_crosshair(e.x, e.y)
        self._update_magnifier(e.x, e.y)

    def cancel(self):
        if self._finished:
            return
        self._finish()
        self.on_cancel()

    # ---------------------------------------------------------------- 绘制

    def _update_crosshair(self, x, y):
        w = self.cv.winfo_width()
        h = self.cv.winfo_height()
        self.cv.coords(self.cross_h, 0, y, w, y)
        self.cv.coords(self.cross_v, x, 0, x, h)
        if self.mode != "point":
            for t in ("crossh", "crossv"):
                self.cv.itemconfigure(t, state="normal")

    def _norm_rect(self):
        if not self._sel:
            return None
        x1, y1, x2, y2 = self._sel
        return x1, y1, x2, y2

    def _update_selection(self):
        x0, y0 = self._origin
        x1, y1 = self._cur
        rx1, ry1 = min(x0, x1), min(y0, y1)
        rx2, ry2 = max(x0, x1), max(y0, y1)
        self._sel = (rx1, ry1, rx2, ry2)
        if self.mode not in ("region", "scroll"):
            return
        # 高亮选区（亮图）
        self._show_selection_image(rx1, ry1, rx2, ry2)
        self.cv.coords(self.sel_rect_item, rx1, ry1, rx2, ry2)
        self.cv.itemconfigure(self.sel_rect_item, state="normal")
        # 参考线
        self.cv.coords(self.guide_h_item, 0, ry1, self.cv.winfo_width(), ry1)
        self.cv.coords(self.guide_v_item, rx1, 0, rx1, self.cv.winfo_height())
        for t in ("guideh", "guidev"):
            self.cv.itemconfigure(t, state="normal")
        # 尺寸标签
        w = int(rx2 - rx1)
        h = int(ry2 - ry1)
        label = f"{w} × {h}"
        self.cv.itemconfigure(self.size_item, text=label)
        bx = rx1
        by = ry1 - 26 if ry1 - 26 > 4 else ry2 + 4
        self.cv.coords(self.size_item, bx, by)
        bb = self.cv.bbox(self.size_item)
        if bb:
            self.cv.coords(self.size_bg_item, bb[0] - 4, bb[1] - 2,
                           bb[2] + 4, bb[3] + 2)
            self.cv.tag_raise(self.size_item, self.size_bg_item)
        self.cv.itemconfigure(self.size_item, state="normal")
        self.cv.itemconfigure(self.size_bg_item, state="normal")

    def _show_selection_image(self, rx1, ry1, rx2, ry2):
        """把选区部分用亮色原图覆盖。"""
        w, h = int(rx2 - rx1), int(ry2 - ry1)
        if w < 1 or h < 1:
            return
        rect = (rx1, ry1, w, h)
        if rect == self._last_crop_rect:
            return
        self._last_crop_rect = rect
        px1, py1 = self._to_physical(rx1, ry1)
        px2, py2 = self._to_physical(rx2, ry2)
        crop = self.bg_img.crop(px1, py1, px2 - px1, py2 - py1)
        if w < 1 or h < 1 or crop.w < 1 or crop.h < 1:
            return
        # 显示为逻辑尺寸（物理/ dpr = 逻辑）
        self._photo_sel = tk.PhotoImage(data=crop.to_ppm())
        self.cv.itemconfigure(self.sel_img_item, image=self._photo_sel)
        self.cv.coords(self.sel_img_item, rx1, ry1)
        self.cv.itemconfigure(self.sel_img_item, state="normal")
        # 让高亮图在最上层、边框之上
        self.cv.tag_raise(self.sel_img_item)
        self.cv.tag_raise(self.sel_rect_item)

    def _hide_selection(self):
        for t in ("selimg", "selrect", "size", "sizebg", "guideh", "guidev"):
            self.cv.itemconfigure(t, state="hidden")
        self._last_crop_rect = None

    def _update_magnifier(self, x, y):
        if self.mode == "point":
            return
        # 物理像素位置
        px, py = self._to_physical(x, y)
        half = MAG_CELL // 2
        crop = self.bg_img.crop(px - half, py - half, MAG_CELL, MAG_CELL)
        if crop.w < 1:
            for t in ("magbg", "magimg", "magcenter"):
                self.cv.itemconfigure(t, state="hidden")
            return
        # 放大 MAG_ZOOM 倍（nearest）
        big = self._upscale_nearest(crop, MAG_ZOOM)
        self._photo_mag = tk.PhotoImage(data=big.to_ppm())
        mx = x + 18
        my = y + 18
        sw = self.cv.winfo_width()
        sh = self.cv.winfo_height()
        if mx + MAG_SIZE > sw - 4:
            mx = x - MAG_SIZE - 18
        if my + MAG_SIZE + 30 > sh - 4:
            my = y - MAG_SIZE - 48
        self.cv.coords(self.mag_bg, mx, my, mx + MAG_SIZE, my + MAG_SIZE + 24)
        self.cv.itemconfigure(self.mag_img_item, image=self._photo_mag)
        self.cv.coords(self.mag_img_item, mx + 1, my + 1)
        self.cv.coords(self.mag_center,
                       mx + half * MAG_ZOOM, my + half * MAG_ZOOM,
                       mx + (half + 1) * MAG_ZOOM, my + (half + 1) * MAG_ZOOM)
        for t in ("magbg", "magimg", "magcenter"):
            self.cv.itemconfigure(t, state="normal")
        self.cv.tag_raise(self.mag_bg)
        self.cv.tag_raise(self.mag_img_item)
        self.cv.tag_raise(self.mag_center)
        # 色值标签（取色模式也显示）
        c = self.bg_img.data
        idx = (min(max(0, py), self.bg_img.h - 1) * self.bg_img.w
               + min(max(0, px), self.bg_img.w - 1)) * 4
        r_, g_, b_ = c[idx + 2], c[idx + 1], c[idx]
        self.cv.itemconfigure(self.hint_item,
                              text=f"#{r_:02X}{g_:02X}{b_:02X}")
        self.cv.coords(self.hint_item, mx + MAG_SIZE / 2, my + MAG_SIZE + 4)
        hb = self.cv.bbox(self.hint_item)
        if hb:
            self.cv.coords(self.hint_bg, hb[0] - 4, hb[1] - 1,
                           hb[2] + 4, hb[3] + 1)
        self.cv.itemconfigure(self.hint_item, state="normal")
        self.cv.itemconfigure(self.hint_bg, state="normal")

    @staticmethod
    def _upscale_nearest(img: wi.Image, factor: int) -> wi.Image:
        w, h = img.w, img.h
        out = wi.Image(w * factor, h * factor, dpr=img.dpr)
        for yy in range(out.h):
            src_y = yy // factor
            for xx in range(out.w):
                src_x = xx // factor
                si = (src_y * w + src_x) * 4
                di = (yy * out.w + xx) * 4
                out.data[di:di + 4] = img.data[si:si + 4]
        return out

    def _update_hint(self):
        if self.mode == "color":
            text = "屏幕取色：单击复制色值    ·    Esc / 右键 取消"
        elif self.mode == "scroll":
            text = "拖拽选择要滚动截图的区域    ·    Esc / 右键 取消"
        elif self.mode == "point":
            text = "单击目标窗口的滚动条【滑块】    ·    Esc / 右键 取消"
        else:
            text = "拖拽选择截图区域    ·    Esc / 右键 取消"
        if self.mode == "color" or self.mode == "point":
            return
        self.cv.itemconfigure(self.hint_item, text=text)
        self.cv.coords(self.hint_item, self.cv.winfo_width() / 2, 14)
        bb = self.cv.bbox(self.hint_item)
        if bb:
            self.cv.coords(self.hint_bg, bb[0] - 8, bb[1] - 3,
                           bb[2] + 8, bb[3] + 3)
            self.cv.itemconfigure(self.hint_item, state="normal")
            self.cv.itemconfigure(self.hint_bg, state="normal")
            self.cv.tag_raise(self.hint_item, self.hint_bg)

    # ---------------------------------------------------------------- 取色/确认

    def _pick_color(self, x, y):
        px, py = self._to_physical(x, y)
        px = min(max(0, px), self.bg_img.w - 1)
        py = min(max(0, py), self.bg_img.h - 1)
        i = (py * self.bg_img.w + px) * 4
        c = self.bg_img.data
        self._finish()
        self.on_capture((c[i + 2], c[i + 1], c[i]))

    def _confirm(self):
        if self._finished:
            return
        self._finished = True
        rect = self._norm_rect()
        self._finish()
        if rect is None:
            self.on_cancel()
            return
        rx1, ry1, rx2, ry2 = rect
        px1, py1 = self._to_physical(rx1, ry1)
        px2, py2 = self._to_physical(rx2, ry2)
        crop = self.bg_img.crop(px1, py1, px2 - px1, py2 - py1)
        crop.dpr = self.dpr
        if self.mode == "scroll":
            self.on_capture((rx1 + self.vx / self.dpr,
                             ry1 + self.vy / self.dpr,
                             rx2 + self.vx / self.dpr,
                             ry2 + self.vy / self.dpr))
        else:
            self.on_capture(crop)

    def _finish(self):
        self._finished = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------- 便捷入口

def snip(mode, on_capture, on_cancel):
    """启动一次截图覆盖层。root 由调用方提供。"""
    root = tk.Tk()
    root.withdraw()
    Snipper(root, mode, on_capture, on_cancel)
    root.mainloop()
