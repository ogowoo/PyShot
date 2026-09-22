# -*- coding: utf-8 -*-
"""winscroller.py —— 滚动长截图（Tk 版）。

复用 scroller.py 里的纯 Python 拼接算法（Frame / find_scroll / static_strips /
content_band_residuals），把 Qt 的驱动与定时器换成 ctypes + Tk。
"""
import ctypes
import ctypes.wintypes as wt
import tkinter as tk

import winimg as wi
import wincapture as wc
import wintk
from stitch import (Frame, best_candidate_offset, content_band_residuals,
                    find_scroll, static_strips)

user32 = wi.u32
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
VK_PAGEDOWN, VK_SPACE, VK_DOWN, VK_NEXT = 0x22, 0x20, 0x28, 0x22

_UNIT_DEFAULTS = {"wheel": 100.0, "drag": 2.0, "key": 200.0}
_UNIT_BOUNDS = {"wheel": (10.0, 400.0), "drag": (0.2, 80.0),
                "key": (30.0, 1200.0)}
_PROBE_START = 4.0
_DRAG_MAX = 160.0


def _sleep_ms(ms: int):
    """保持界面响应的等待。"""
    loop = tk.Tcl()
    loop.eval(f"after {ms} set _done 1")
    loop.eval("vwait _done")


def _set_cursor(x, y):
    user32.SetCursorPos(int(x), int(y))


def _send_vk(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)


def _drag_scrollbar(anchor, dy: float, steps: int = 6):
    ax, ay = int(anchor[0]), int(anchor[1])
    _set_cursor(ax, ay)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    for i in range(1, steps + 1):
        _set_cursor(ax, int(ay + dy * i / steps))
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


class WinScrollDriver:
    """把"想滚动多少内容像素"翻译成输入，并用实测位移自我校准。

    mode: wheel（滚轮）/ drag（拖滚动条滑块）/ key（PageDown 等按键）
    """

    def __init__(self, mode: str, region, anchor=None, key_vk: int = VK_PAGEDOWN):
        self.mode = mode
        self.region = tuple(region)          # (l, t, w, h) 物理像素
        self.anchor = tuple(anchor) if anchor else (
            region[0] + region[2] // 2, region[1] + region[3] // 2)
        self.key_vk = key_vk
        self.px_per_unit = float(_UNIT_DEFAULTS.get(mode, 100.0))
        self.last_units = 0.0
        self.observations = 0
        self.moved_ever = False
        self.probe_px = _PROBE_START
        self.probing = (mode == "drag")
        self.snapped = False
        self.native = None
        self.used_fallback = None

    def prepare(self):
        if self.mode == "key":
            hwnd = wc.window_at(self.region[0] + self.region[2] // 2,
                                self.region[1] + self.region[3] // 2)
            if hwnd:
                try:
                    user32.SetForegroundWindow(wt.HWND(hwnd))
                    _sleep_ms(120)
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.mode != "drag":
            return
        try:
            ax, ay = int(self.anchor[0]), int(self.anchor[1])
            self.native = wc.get_scroll_info_at(ax, ay)
            if self.native is not None:
                return
            thumb = wc.scrollbar_thumb_rect(ax, ay)
            if thumb:
                l, t, w, h = thumb
                cx, cy = l + w // 2, t + h // 2
                if abs(cx - ax) + abs(cy - ay) <= 60:
                    self.anchor = (cx, cy)
                    self.snapped = True
        except Exception:  # noqa: BLE001
            pass

    def __call__(self, step_px: float):
        units = step_px / max(0.05, self.px_per_unit)
        if self.mode == "wheel":
            notches = int(min(15, max(1, round(units))))
            self.last_units = float(notches)
            _set_cursor(self.region[0] + self.region[2] // 2,
                        self.region[1] + self.region[3] // 2)
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -120 * notches, 0)
        elif self.mode == "key":
            times = int(min(5, max(1, round(units))))
            self.last_units = float(times)
            for _ in range(times):
                _send_vk(self.key_vk)
        else:
            if self.native is not None:
                info = self.native
                step_pos = max(1, int(info["page"] * 0.45))
                new_pos = min(info["max"], info["pos"] + step_pos)
                self.last_units = float(max(1, new_pos - info["pos"]))
                wc.set_scroll_pos(info["hwnd"], new_pos)
                info["pos"] = new_pos
                return
            dy = self.probe_px if self.probing else float(
                min(_DRAG_MAX, max(4.0, units)))
            self.last_units = dy
            _drag_scrollbar(self.anchor, dy)
            self.anchor = (self.anchor[0], int(self.anchor[1] + dy))

    def recovery_after_jump(self) -> bool:
        self._recovery_count = getattr(self, "_recovery_count", 0) + 1
        if self.observations >= 2 or self._recovery_count > 4:
            return False
        if self.mode == "drag":
            self.probing = True
            self.probe_px = max(1.5, self.probe_px / 2)
            self.px_per_unit = min(_UNIT_BOUNDS["drag"][1],
                                   self.px_per_unit * 2)
            return True
        lo, hi = _UNIT_BOUNDS.get(self.mode, (0.1, 10000.0))
        self.px_per_unit = min(hi, self.px_per_unit * 2)
        return True

    def observe(self, actual_px: int):
        if self.last_units <= 0 or actual_px <= 0:
            return
        measured = actual_px / self.last_units
        lo, hi = _UNIT_BOUNDS.get(self.mode, (0.1, 10000.0))
        if not (lo <= measured <= hi):
            return
        weight = 0.6 if self.observations == 0 else 0.35
        self.px_per_unit = (1 - weight) * self.px_per_unit + weight * measured
        self.observations += 1
        if self.mode == "drag":
            self.probing = False

    def describe(self) -> str:
        return {"wheel": "滚轮", "drag": "拖拽滚动条", "key": "按键"}.get(
            self.mode, self.mode)


class ScrollCaptureTk:
    """滚动截图流程（Tk 定时循环版）。

    region: (left, top, w, h) 屏幕物理像素
    mode: wheel / drag / key / manual
    on_done(Image) / on_error(str) 回调
    """

    def __init__(self, root: tk.Tk, region, mode="wheel", anchor=None,
                 on_done=None, on_error=None, interval_ms=650, max_frames=60,
                 manual=False):
        self.root = root
        self.region = tuple(int(v) for v in region)
        self.mode = mode
        self.manual = manual or mode == "manual"
        self.interval_ms = interval_ms
        self.max_frames = max_frames
        self.on_done = on_done
        self.on_error = on_error
        self.driver = None
        if not self.manual:
            self.driver = WinScrollDriver(mode, self.region, anchor)
        self.frames = 0
        self.acc: Frame | None = None
        self.prev: Frame | None = None
        self.no_progress = 0
        self.stopped = False
        self.dpr = wi.primary_dpi()
        self._bar = None

    # ---------- 生命周期 ----------
    def start(self):
        if self.driver:
            self.driver.prepare()
        self._show_bar()
        self.root.after(80, self._tick)

    def stop(self):
        self.stopped = True
        self._finish()

    # ---------- 抓帧 ----------
    def _grab(self):
        l, t, w, h = self.region
        img = wc.grab_region_smart(l, t, w, h, self.dpr)
        return img.to_frame()

    def _grab_settled(self) -> Frame:
        fr = self._grab()
        if not (self.manual or (self.driver and self.driver.mode == "drag")):
            return fr
        prev = fr
        for wait in (90, 180):
            self._sleep(wait)
            again = self._grab()
            if self._frame_diff(prev, again) < 1.0:
                return again
            fr, prev = again, again
        return fr

    @staticmethod
    def _frame_diff(a: Frame, b: Frame, step: int = 4) -> float:
        if a.h != b.h:
            return 999.0
        total = n = 0
        for y in range(0, a.h, step):
            ra, rb = a.rows[y], b.rows[y]
            if ra == rb:
                continue
            for x in range(0, len(ra), 18):
                total += abs(ra[x] - rb[x])
                n += 1
        return total / max(1, n)

    def _sleep(self, ms):
        self.root.update()
        _sleep_ms(ms)

    # ---------- 主循环 ----------
    def _tick(self):
        if self.stopped:
            return
        try:
            self._tick_once()
        except Exception as ex:  # noqa: BLE001
            self._error(f"滚动截图出错：{type(ex).__name__}: {ex}")

    def _tick_once(self):
        fr = self._grab_settled()
        if fr.w < 8 or fr.h < 80:
            self._error("抓帧失败：区域过小或被遮挡")
            return
        if self.prev is None and self.frames == 0:
            if wc.image_is_blank(wi.Image.from_frame(fr), min_std=1.2,
                                 black_level=10):
                self._error(
                    "抓到的画面是空白/纯色，无法拼接。\n"
                    "目标窗口可能启用了硬件加速或内容保护，系统抓屏拿不到内容。\n"
                    "可尝试：① 关闭硬件加速；② 用托盘菜单的「滚动长截图（手动滚动）」；"
                    "③ 把窗口最大化后重试。")
                return

        s = 0
        if self.prev is None:
            self.acc = fr
        else:
            if fr.h != self.prev.h or fr.w != self.prev.w:
                self._error("抓帧尺寸发生变化，已停止（请确保窗口未移动/缩放）")
                return
            s, diff = find_scroll(self.prev, fr)
            if s < 0:
                if self.driver and self.driver.recovery_after_jump():
                    self.prev = fr
                    self.frames += 1
                    self._progress()
                    self._do_scroll()
                    return
                if self.manual and self.frames < self.max_frames:
                    self.prev = fr
                    self.frames += 1
                    self._progress()
                    self._schedule()
                    return
                if (self.frames >= 3 and self.acc is not None
                        and self.acc.h > fr.h * 1.5):
                    self.no_progress += 1
                    self.prev = fr
                    self.frames += 1
                    self._progress()
                    if self.no_progress >= 2:
                        self._finish()
                    else:
                        self._schedule()
                    return
                from stitch import best_candidate_offset
                guess = best_candidate_offset(self.prev, fr)
                if guess > 0:
                    t2, b2 = static_strips(self.prev, fr)
                    res = content_band_residuals(self.prev, fr, guess, t2,
                                                 fr.h - b2)
                    valid = [r for r in res if r is not None]
                    if len(valid) >= 2 and max(valid) > max(
                            6.0, min(valid) * 3.0 + 4.0):
                        self._error(
                            "选区里似乎包含多块独立滚动的区域（例如上方列表 + "
                            "下方明细面板），它们滚动量不同，拼不到一起。\n"
                            "请只框选其中一个面板后重试。")
                        return
                self._error(
                    "画面内容变化过快，无法对齐拼接。\n"
                    + ("拖拽滚动条模式：最常见是点在了滚动条**轨道**而不是**滑块**上——"
                       "那样会翻整页，无法拼接。请重新框选并点中滑块本身。\n"
                       if self.driver and self.driver.mode == "drag" else
                       "（请关闭动画/视频后重试）\n"))
                return
            if s == 0:
                self.no_progress += 1
            else:
                H = fr.h
                top, bpad = static_strips(self.prev, fr)
                bottom = H - bpad
                if self.frames == 1:
                    kept = self.acc.rows[top:bottom]
                    self.acc = Frame(kept, self.acc.w, len(kept), self.acc.dpr)
                start = max(top, bottom - s)
                if bottom - start > 0:
                    self.acc.rows.extend(fr.rows[start:bottom])
                    self.acc.h = len(self.acc.rows)
                self.no_progress = 0
                if self.driver:
                    self.driver.moved_ever = True
                    self.driver.observe(s)
        self.prev = fr
        self.frames += 1
        self._progress()

        if not self.manual and self.no_progress >= 3:
            d = self.driver
            if (d is not None and d.mode == "drag" and not d.moved_ever
                    and d.used_fallback is None):
                d.used_fallback = "wheel"
                d.mode = "wheel"
                d.px_per_unit = _UNIT_DEFAULTS["wheel"]
                self.no_progress = 0
                if self._bar:
                    self._bar.set_title("拖拽没生效，改用滚轮重试")
                self._schedule()
                return
            self._finish()
            return
        if not self.manual and self.frames >= self.max_frames:
            self._finish()
            return
        self._do_scroll()

    def _do_scroll(self):
        if self.manual:
            self._schedule()
            return
        step = max(60.0, self.region[3] * 0.45)
        self.driver(step)
        self._schedule()

    def _schedule(self):
        if self.stopped:
            return
        self.root.after(max(60, self.interval_ms), self._tick)

    def _progress(self):
        if self._bar and self.acc is not None:
            self._bar.set_progress(self.frames,
                                   int(self.acc.h / max(0.01, self.dpr)))

    def _finish(self):
        if self.stopped and self.acc is None:
            return
        self.stopped = True
        self._close_bar()
        if self.acc is None or self.acc.h < 20:
            self._error("没能拼出内容，请重试")
            return
        img = wi.Image.from_frame(self.acc)
        img.dpr = 1.0
        if self.driver and self.driver.used_fallback:
            note = "（拖拽无效，已自动改用滚轮）"
        else:
            note = ""
        if self.on_done:
            self.on_done(img, note)

    def _error(self, msg):
        self.stopped = True
        self._close_bar()
        if self.on_error:
            self.on_error(msg)

    # ---------- 控制条 ----------
    def _show_bar(self):
        self._bar = ScrollBarTk(self.root, self.region, self.manual,
                                on_stop=self.stop,
                                mode_text=(self.driver.describe()
                                           if self.driver else "手动滚动"))

    def _close_bar(self):
        if self._bar:
            self._bar.close()
            self._bar = None


class ScrollBarTk:
    """浮在选区外的小控制条：显示帧数/总长，提供停止按钮。"""

    def __init__(self, root, region, manual, on_stop, mode_text=""):
        self.on_stop = on_stop
        l, t, w, h = region
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=wintk.SURFACE_2)
        x = l + w - 260
        y = max(8, t - 46)
        self.win.geometry(f"260x38+{max(8, x)}+{y}")
        outer = tk.Frame(self.win, bg=wintk.BORDER_STRONG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        inner = tk.Frame(outer, bg=wintk.SURFACE_2)
        inner.pack(fill="both", expand=True)
        self.title = tk.Label(inner, text=mode_text, bg=wintk.SURFACE_2,
                              fg=wintk.TEXT, font=wintk.FONT_SMALL)
        self.title.pack(side="left", padx=8)
        self.progress = tk.Label(inner, text="", bg=wintk.SURFACE_2,
                                 fg=wintk.TEXT_DIM, font=wintk.FONT_SMALL)
        self.progress.pack(side="left", padx=4)
        stop = tk.Button(inner, text="完成" if manual else "停止", relief="flat",
                         bd=0, bg=wintk.ACCENT, fg="#ffffff",
                         activebackground=wintk.ACCENT_HOVER,
                         font=wintk.FONT_SMALL, padx=10, cursor="hand2",
                         command=self.on_stop)
        stop.pack(side="right", padx=6, pady=5)
        self.win.lift()

    def set_title(self, text):
        self.title.config(text=text)

    def set_progress(self, frames, height, offset=None):
        s = f"第 {frames} 帧 · 已拼 {height}px"
        if offset:
            s += f" · +{offset}"
        self.progress.config(text=s)

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
