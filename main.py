# -*- coding: utf-8 -*-
"""PyShot —— 仿 FSCapture 的截图 + 标注编辑工具。

功能
====
- 区域截图：全屏覆盖层拖拽框选，带放大镜与尺寸提示
- 全屏截图：一键截取整个虚拟桌面
- 打开图片编辑：把已有图片载入编辑器
- 标注工具：选择 / 矩形 / 椭圆 / 直线 / 箭头 / 画笔 / 序号步骤 / 文字 / 高亮 / 马赛克 / 裁剪
- 撤销(Ctrl+Z) / 重做(Ctrl+Y)、复制(Ctrl+C)、保存(Ctrl+S)
- 系统托盘常驻，PrintScreen 全局热键唤起截图

运行::

    python main.py
"""
import ctypes
import ctypes.wintypes
import os
import sys
from pathlib import Path

# 依赖自举：缺 PySide6 / numpy 时自动 pip 安装（必须在导入 PySide6 之前）
from bootstrap import deps_report, ensure_deps

if not ensure_deps():
    raise SystemExit(1)

from PySide6.QtCore import (QAbstractNativeEventFilter, QObject, QPoint, QRect,
                            Qt, QTimer)
from PySide6.QtGui import (QAction, QColor, QCursor, QGuiApplication, QIcon,
                           QPainter, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMenu,
                               QSystemTrayIcon)

from editor import EditorWindow
from pinboard import PinWindow
from scroller import ScrollCapture, ScrollDriver
from snipper import SnipperOverlay, grab_screen, grab_virtual_desktop
from style import apply_theme, make_menu_icon

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID_BASE = 0x5053          # "PS"

# 候选全局热键（按优先级尝试，选第一个没被占用的）。
# 刻意避开被系统或常用软件注册的组合：
#   PrintScreen / Win+Shift+S  → Windows 11 截图工具
#   Ctrl+Alt+A / Ctrl+Shift+A / Alt+A → QQ、微信的截图
DEFAULT_HOTKEYS = ["ctrl+alt+x", "ctrl+shift+x", "ctrl+alt+f9", "ctrl+shift+f9"]

# 全屏截图热键（截"鼠标所在的那块显示器"），与区域截图分开注册、互不干扰
FULLSCREEN_HOTKEYS = ["ctrl+alt+f", "ctrl+shift+f", "ctrl+alt+f10",
                      "ctrl+shift+f10"]

_VK_NAMES = {
    "printscreen": 0x2C, "prtsc": 0x2C, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B,
}
for _i in range(1, 13):                     # F1..F12
    _VK_NAMES[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz":     # A..Z
    _VK_NAMES[_c] = ord(_c.upper())
for _d in "0123456789":                     # 0..9
    _VK_NAMES[_d] = ord(_d)


def parse_hotkey(spec: str):
    """解析 "ctrl+alt+x" 这类热键描述，返回 (modifiers, vk, 显示名)；非法返回 None。"""
    if not spec:
        return None
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    labels = []
    vk = None
    for part in parts:
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
            labels.append("Ctrl")
        elif part == "alt":
            mods |= MOD_ALT
            labels.append("Alt")
        elif part == "shift":
            mods |= MOD_SHIFT
            labels.append("Shift")
        elif part in ("win", "super", "meta"):
            mods |= MOD_WIN
            labels.append("Win")
        elif part in _VK_NAMES:
            if vk is not None:
                return None                 # 两个主键，非法
            vk = _VK_NAMES[part]
            labels.append(part.upper() if len(part) == 1 else part.capitalize())
        else:
            return None
    if vk is None or mods == 0:
        return None                          # 必须有主键，且至少一个修饰键
    return mods | MOD_NOREPEAT, vk, "+".join(labels)


def register_global_hotkeys(candidates, id_offset: int = 0) -> dict:
    """依次尝试注册，返回 {热键 id: 显示名}（只注册第一个成功的）。

    candidates 为空表示不注册。注册失败（被其他程序占用）会自动尝试下一个。
    id_offset 把多组热键的 id 错开（同进程内 id 不能重复）。
    """
    user32 = ctypes.windll.user32
    for i, spec in enumerate(candidates):
        parsed = parse_hotkey(spec)
        if parsed is None:
            continue
        mods, vk, name = parsed
        hid = HOTKEY_ID_BASE + id_offset + i
        if user32.RegisterHotKey(None, hid, mods, vk):
            return {hid: name}
    return {}


def make_tray_icon() -> QIcon:
    """自绘一个醒目的相机图标，避免系统标准图标在任务栏里认不出来。"""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1e88e5"))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(14, 22, 36, 26, 5, 5)          # 机身
    p.drawRect(24, 15, 16, 9)                         # 顶部凸起
    p.setBrush(QColor("#1e88e5"))
    p.drawEllipse(24, 26, 16, 16)                     # 镜头
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(29, 31, 6, 6)
    p.end()
    return QIcon(pix)


class HotkeyFilter(QAbstractNativeEventFilter):
    """监听已注册的全局热键（Windows WM_HOTKEY）。

    回调带上热键 id，便于区分"区域截图"和"全屏截图"。
    """

    def __init__(self, ids, callback):
        super().__init__()
        self.ids = set(ids)
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self.ids:
                self.callback(msg.wParam)
        return False, 0


class PyShotApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.snipper: SnipperOverlay | None = None
        self._overlay: SnipperOverlay | None = None   # 主屏覆盖层（兼容）
        self._overlays: list = []                     # 每块屏一个
        self._overlay_screens: list = []
        self._want_scroll = False
        self.scroller: ScrollCapture | None = None
        self.editors: list[EditorWindow] = []
        self.pins: list[PinWindow] = []
        self._minimized_by_capture: list[EditorWindow] = []
        self._hotkey_ok = False
        self.hotkey_text = ""
        self._hotkeys: dict = {}
        self._scroll_mode: str | None = None   # None / "wheel" / "drag" / "key" / "manual"
        self._pending_scroll_region = None

        self._init_hotkey()   # 先注册热键，托盘文案才知道该显示哪个按键
        self._init_tray()
        # 启动后台预热（延迟一点，不影响启动速度）
        QTimer.singleShot(400, self._warmup)

    # ---------- 全局热键 ----------
    def _init_hotkey(self):
        """注册两组全局热键：区域截图 + 全屏截图（各自挑第一个没被占用的组合）。"""
        env_spec = os.environ.get("PYSHOT_HOTKEY")
        region_cands = [env_spec] if env_spec else DEFAULT_HOTKEYS
        self._region_hotkeys = register_global_hotkeys(region_cands, 0)
        self._full_hotkeys = register_global_hotkeys(FULLSCREEN_HOTKEYS, 100)
        self._hotkeys = {**self._region_hotkeys, **self._full_hotkeys}
        self._hotkey_ok = bool(self._hotkeys)
        self.hotkey_text = next(iter(self._region_hotkeys.values()), "")
        self.full_hotkey_text = next(iter(self._full_hotkeys.values()), "")
        # id → 动作，供 nativeEventFilter 分发
        self._hotkey_actions = {}
        for hid in self._region_hotkeys:
            self._hotkey_actions[hid] = "region"
        for hid in self._full_hotkeys:
            self._hotkey_actions[hid] = "fullscreen"
        if self._hotkey_ok:
            self._filter = HotkeyFilter(self._hotkeys.keys(), self._on_hotkey)
            self.app.installNativeEventFilter(self._filter)
            parts = []
            if self.hotkey_text:
                parts.append(f"区域 {self.hotkey_text}")
            if self.full_hotkey_text:
                parts.append(f"全屏 {self.full_hotkey_text}")
            print("[PyShot] 全局热键已注册：" + "、".join(parts))
        else:
            print("[PyShot] 热键注册失败，已尝试：" + "、".join(region_cands))

    # ---------- 托盘 ----------
    def _init_tray(self):
        if not self.tray_available:
            # 无托盘环境：关掉最后一个窗口就退出，避免程序"隐身"
            self.app.setQuitOnLastWindowClosed(True)
            return
        self.tray = QSystemTrayIcon(make_tray_icon(), self.app)
        menu = QMenu()
        self.menu = menu

        # ---------- 截图 ----------
        # 高频动作置顶；快捷键用 "\t" 放到右侧列（只是显示，不注册 Qt 快捷键，
        # 避免与全局热键同时触发一次截图）
        act_region = QAction(make_menu_icon("crop"), "区域截图", self.app)
        act_region.setToolTip("框选一块区域截图")
        act_region.triggered.connect(lambda: self._deferred(self.capture_region))
        menu.addAction(act_region)
        self.act_region = act_region

        act_full = QAction(make_menu_icon("camera"), "全屏截图", self.app)
        act_full.setToolTip("截取鼠标所在的那块显示器")
        act_full.triggered.connect(lambda: self._deferred(self.capture_fullscreen))
        menu.addAction(act_full)
        self.act_full = act_full

        # 选择显示器（含"所有显示器拼一张"）：弹出时按当前屏幕列表重建
        self.menu_screens = QMenu("选择显示器截图", menu)
        self.menu_screens.setIcon(make_menu_icon("monitor"))
        self.menu_screens.aboutToShow.connect(self._rebuild_screen_menu)
        menu.addMenu(self.menu_screens)

        menu.addSeparator()

        # ---------- 滚动长截图（收进子菜单，避免主菜单过长）----------
        menu_scroll = QMenu("滚动长截图", menu)
        menu_scroll.setIcon(make_menu_icon("scroll"))
        for label, tip, fn in [
                ("自动滚轮",
                 "框选可滚动区域，程序自己发滚轮逐屏拼接（普通网页/文档）",
                 lambda: self.capture_scrolling()),
                ("拖拽滚动条",
                 "框选区域后点一下滚动条滑块，程序按住滑块匀速拖拽。\n"
                 "远程桌面 / Citrix 里最稳：步长会实测标定",
                 lambda: self.capture_scrolling(mode="drag")),
                ("按键翻页",
                 "框选区域后程序发送 PageDown 翻页（适合没有滚动条的应用）",
                 lambda: self.capture_scrolling(mode="key")),
                ("手动滚动",
                 "自己用滚轮滚动，程序只负责逐帧拼接",
                 lambda: self.capture_scrolling(manual=True))]:
            act = QAction(label, menu_scroll)
            act.setToolTip(tip)
            act.triggered.connect(
                lambda checked=False, f=fn: self._deferred(f))
            menu_scroll.addAction(act)
        menu.addMenu(menu_scroll)

        menu.addSeparator()

        # ---------- 小工具 ----------
        act_color = QAction(make_menu_icon("pick"), "屏幕取色", self.app)
        act_color.setToolTip("单击屏幕任意位置，把色值复制到剪贴板")
        act_color.triggered.connect(lambda: self._deferred(self.pick_color))
        menu.addAction(act_color)

        act_pin_clip = QAction(make_menu_icon("pin"), "贴出剪贴板图片", self.app)
        act_pin_clip.setToolTip("把剪贴板里的图片钉在屏幕最上层")
        act_pin_clip.triggered.connect(self.pin_clipboard)
        menu.addAction(act_pin_clip)

        menu.addSeparator()

        # ---------- 窗口 ----------
        act_open = QAction(make_menu_icon("image"), "打开图片编辑…", self.app)
        act_open.setToolTip("打开一张已有图片进行标注")
        act_open.triggered.connect(self.open_image)
        menu.addAction(act_open)

        act_editor = QAction(make_menu_icon("window"), "打开编辑器", self.app)
        act_editor.setToolTip(
            "把编辑器窗口恢复到前台（取消截图后找不到编辑器时点这里）")
        act_editor.triggered.connect(self.show_editor)
        menu.addAction(act_editor)

        menu.addSeparator()
        act_quit = QAction(make_menu_icon("exit"), "退出 PyShot", self.app)
        act_quit.triggered.connect(self.app.quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        # 快捷键写进右侧列（\t 之后的部分由 Qt 右对齐显示）
        if self.hotkey_text:
            act_region.setText(f"区域截图\t{self.hotkey_text}")
        if self.full_hotkey_text:
            act_full.setText(f"全屏截图\t{self.full_hotkey_text}")
        hints = []
        if self.hotkey_text:
            hints.append(f"{self.hotkey_text} 区域截图")
        if self.full_hotkey_text:
            hints.append(f"{self.full_hotkey_text} 全屏截图")
        if hints:
            self.tray.setToolTip(
                "PyShot 截图工具\n" + " · ".join(hints) + "\n双击图标截图")
        else:
            self.tray.setToolTip(
                "PyShot 截图工具\n双击图标截图 · 右键菜单")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        # 注意：启动提示不在这里弹 —— 由 notify_ready() 统一负责，
        # 否则构造托盘和 main() 会各弹一次，用户看到两个气泡。

    def _on_hotkey(self, hotkey_id=None):
        """来自原生消息回调（WM_HOTKEY）——按热键 id 分发，延后一拍再动作。"""
        action = self._hotkey_actions.get(hotkey_id, "region")
        if action == "fullscreen":
            self._deferred(self.capture_fullscreen, delay=30)
        else:
            self._deferred(self.capture_region, delay=30)

    def shutdown(self):
        if getattr(self, "_hotkeys", None):
            user32 = ctypes.windll.user32
            for hid in self._hotkeys:
                user32.UnregisterHotKey(None, hid)

    # ---------- 截图流程 ----------
    def capture_region(self):
        self._start_snipper("region")

    def _start_snipper(self, mode: str, scroll_mode: str | None = None,
                       point_region: QRect | None = None):
        if self.snipper is not None:
            return  # 已有覆盖层在运行
        self._prepare_capture()
        self._scroll_mode = scroll_mode      # None / "wheel" / "drag" / "key" / "manual"
        overlays = self._ensure_overlays()
        self.snipper = overlays[0]           # 代表整个会话（哪个屏先按就用哪个屏）
        for ov in overlays:
            ov.start(mode)
            if mode == "point" and point_region is not None:
                # 选区挖空后可穿透点击（能真的点到应用里的滚动条）
                ov.set_point_hole(point_region)

    # ---------- 截图触发（统一延后到事件循环） ----------
    def _deferred(self, fn, delay: int = 40):
        """把截图动作延后到 Qt 事件循环里执行。

        托盘双击/托盘菜单都发生在 shell 的原生消息回调中，此时直接创建并显示
        全屏覆盖层会被前台激活锁和鼠标捕获影响，表现为"窗口在但没画出来"。
        延后一拍即可稳定显示；延迟保持很小，避免拖慢首帧。
        """
        QTimer.singleShot(delay, fn)

    def _rebuild_screen_menu(self):
        """按当前显示器列表重建子菜单（插拔显示器后自动更新）。

        除了每块屏一项，末尾再放"所有显示器拼成一张"——都属于"截哪块屏"这件事。
        """
        self.menu_screens.clear()
        primary = QGuiApplication.primaryScreen()
        for i, scr in enumerate(QGuiApplication.screens()):
            geo = scr.geometry()
            dpr = float(scr.devicePixelRatio() or 1.0)
            tag = "主屏" if scr is primary else f"显示器 {i + 1}"
            scale = f" @{int(round(dpr * 100))}%" if abs(dpr - 1.0) > 1e-6 else ""
            act = QAction(
                f"{tag}：{geo.width()}×{geo.height()}{scale}  ({scr.name()})",
                self.menu_screens)
            act.setIcon(make_menu_icon("monitor"))
            act.triggered.connect(
                lambda checked=False, s=scr: self._deferred(
                    lambda: self.capture_fullscreen(s)))
            self.menu_screens.addAction(act)
        if not self.menu_screens.actions():
            act = QAction("（未检测到显示器）", self.menu_screens)
            act.setEnabled(False)
            self.menu_screens.addAction(act)
        self.menu_screens.addSeparator()
        act_all = QAction("所有显示器拼成一张", self.menu_screens)
        act_all.setIcon(make_menu_icon("monitor"))
        act_all.setToolTip("把每块显示器按逻辑位置拼成一张长图")
        act_all.triggered.connect(
            lambda: self._deferred(self.capture_all_screens))
        self.menu_screens.addAction(act_all)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._deferred(self.capture_region)

    # ---------- 覆盖层复用与预热 ----------
    def _ensure_overlays(self) -> list:
        """确保每一块显示器都有一个覆盖层。

        多屏必须"一屏一窗"：单个窗口横跨多显示器时，Windows 的每显示器 DPI
        会让非主屏部分被裁剪或缩放，导致多屏基本不可用。
        """
        screens = QGuiApplication.screens()
        names = [s.name() for s in screens]
        if self._overlays and self._overlay_screens == names:
            return self._overlays
        for ov in self._overlays:             # 屏幕组合变了：重建
            ov.deleteLater()
        self._overlays = []
        for scr in screens:
            ov = SnipperOverlay("region", screen=scr)
            ov.captured.connect(self._on_captured)
            ov.region_selected.connect(self._on_region_selected)
            ov.point_selected.connect(self._on_scroll_anchor)
            ov.color_picked.connect(self._on_color_picked)
            ov.cancelled.connect(self._on_snip_cancelled)
            self._overlays.append(ov)
        self._overlay_screens = names
        self._overlay = self._overlays[0] if self._overlays else None
        return self._overlays

    def _warmup(self):
        """启动后预热：抓屏路径 + 每块屏的覆盖层窗口，让第一次截图也能秒开遮罩。"""
        if self.snipper is not None:        # 正在截图中，别去动覆盖层
            return
        try:
            grab_virtual_desktop()          # 预热抓屏（首次调用较慢）
            for ov in self._ensure_overlays():
                ov.warmup()                 # 预建置顶全屏窗口（Windows 首次极慢）
        except Exception:                    # noqa: BLE001
            pass                             # 预热失败不影响正常使用

    def _on_region_selected(self, region):
        mode = self._scroll_mode
        self._scroll_mode = None
        if not mode:
            return
        if mode == "drag":
            # 选区外遮罩、选区内可点击：让用户直接点到应用里的滚动条滑块
            self._on_snip_done()      # 先释放覆盖层引用，才能再用它做选点
            self._pending_scroll_region = QRect(region)
            self._start_snipper("point", point_region=QRect(region))
            return
        if mode == "manual":
            self._start_scrolling(region, manual=True)
        else:
            self._start_scrolling(region, mode=mode)

    # ---------- 截图会话：截图时最小化编辑器，结束后恢复 ----------
    def _prepare_capture(self):
        """开始截图前把编辑器最小化，免得自己被拍进图里。"""
        self._minimized_by_capture = [
            ed for ed in list(self.editors)
            if ed.isVisible() and not ed.isMinimized()
        ]
        for ed in self._minimized_by_capture:
            ed.showMinimized()

    def _finish_capture_session(self):
        """截图流程结束后把之前最小化的编辑器还原。"""
        for ed in getattr(self, "_minimized_by_capture", []):
            if ed in self.editors:
                ed.showNormal()
                ed.raise_()
                ed.activateWindow()
        self._minimized_by_capture = []

    def _on_snip_cancelled(self, *args):
        self._on_snip_done()
        self._pending_scroll_region = None   # 取消时清掉滚动截图的待选状态
        self._finish_capture_session()

    def _on_snip_done(self, *args):
        # 所有屏幕的覆盖层都要收起（多屏时可能有好几个）
        for ov in getattr(self, "_overlays", []):
            if ov.isVisible():
                ov.finish()
        self.snipper = None
        if not self.tray_available and not self.editors:
            self.app.quit()  # 无托盘且无窗口时退出，避免程序"隐身"残留

    def _on_captured(self, pixmap: QPixmap):
        self._on_snip_done()
        if self._scroll_mode:      # 滚动截图的选区，不是要编辑的截图
            self._scroll_mode = None
            return

        # 等覆盖层彻底关闭再开编辑器，否则置顶的覆盖层可能压在编辑器上面；
        # 并且把异常显式暴露出来，避免"截图后什么都没发生"这种静默失败。
        def _open():
            try:
                self.open_editor(pixmap)
            except Exception as ex:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self._notify("打开编辑器失败", f"{type(ex).__name__}: {ex}")
            finally:
                self._finish_capture_session()

        QTimer.singleShot(120, _open)

    def capture_fullscreen(self, screen=None):
        """全屏截图。

        screen 为 None 时截"鼠标所在的那块显示器"（多屏下最符合直觉）；
        也可以显式指定某块屏（托盘菜单"截取指定显示器"）。
        另外保留"所有显示器拼成一张"的旧行为，见 capture_all_screens。
        """
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos()) \
                or QGuiApplication.primaryScreen()
        self._prepare_capture()

        def _grab():
            try:
                pix = grab_screen(screen)
            except Exception as ex:  # noqa: BLE001
                self._notify("全屏截图失败", f"{type(ex).__name__}: {ex}")
                self._finish_capture_session()
                return
            label = f"{screen.name()} {pix.width()}×{pix.height()}"
            self.open_editor(pix)
            self._notify("全屏截图完成", label)
            self._finish_capture_session()

        # 等最小化动画结束再抓，否则窗口残影会进图
        QTimer.singleShot(280, _grab)

    def capture_all_screens(self):
        """把所有显示器拼成一张长图（旧的全屏行为）。"""
        self._prepare_capture()

        def _grab():
            pix, _ = grab_virtual_desktop()
            self.open_editor(pix)
            self._finish_capture_session()

        QTimer.singleShot(280, _grab)

    # ---------- 滚动长截图 ----------
    def capture_scrolling(self, manual: bool = False, mode: str = "wheel"):
        """mode: wheel 滚轮 | drag 拖拽滚动条 | key 按键；manual=True 为手动模式。"""
        if self.snipper is not None or self.scroller is not None:
            return
        # 用 "scroll" 模式：只取选区，不会触发普通截图流程（否则编辑器会被弹到前面挡住目标）
        self._start_snipper("scroll", scroll_mode="manual" if manual else mode)

    def _start_scrolling(self, region, manual: bool = False, mode: str = "wheel"):
        self._on_snip_done()   # 只清引用：滚动期间编辑器保持最小化，否则会被拍进画面
        if region.width() < 50 or region.height() < 120:
            self._notify("滚动截图", "区域太小，请框选更高的可滚动区域")
            self._finish_capture_session()
            return
        driver = None
        if not manual:
            driver = ScrollDriver(mode, region)
        self._launch_scroller(region, manual=manual, driver=driver)

    def _launch_scroller(self, region, manual=False, driver=None, title=None):
        self.scroller = ScrollCapture(region, manual=manual, driver=driver)
        if title:
            self.scroller.bar.set_title(title)
        self.scroller.finished_ok.connect(self._on_scroll_finished)
        self.scroller.failed.connect(self._on_scroll_failed)
        # 等覆盖层完全关闭再开始，否则会拍到残影
        QTimer.singleShot(500, self.scroller.start)

    def _on_scroll_anchor(self, point):
        """用户在滚动条滑块上点了一下：开始"拖拽滚动条"自动滚动。"""
        self._on_snip_done()
        region = self._pending_scroll_region
        self._pending_scroll_region = None
        if region is None:
            self._finish_capture_session()
            return
        driver = ScrollDriver("drag", region, anchor=point)
        self._launch_scroller(region, manual=False, driver=driver,
                              title="拖拽滚动条自动滚动")
        self._notify("已记录滚动条位置",
                     f"滑块锚点 ({point.x()}, {point.y()})，开始自动拖拽滚动。\n"
                     "滚到底会自动结束；想中途停止点控制条上的按钮。")

    def _on_scroll_finished(self, pixmap: QPixmap):
        self.scroller = None
        self._notify("滚动截图完成", f"已拼接 {pixmap.height()} px 长图")
        self.open_editor(pixmap)
        self._finish_capture_session()

    def _on_scroll_failed(self, msg: str):
        self.scroller = None
        self._notify("滚动截图失败", msg)
        self._finish_capture_session()

    # ---------- 屏幕取色 ----------
    def pick_color(self):
        self._start_snipper("color")

    def _on_color_picked(self, color):
        self._on_snip_done()
        text = color.name().upper()
        QApplication.clipboard().setText(text)
        self._notify("屏幕取色",
                     f"{text}  RGB({color.red()}, {color.green()}, {color.blue()}) 已复制")

    # ---------- 贴图钉板 ----------
    def pin_pixmap(self, pixmap: QPixmap, pos=None):
        pin = PinWindow(pixmap, pos)
        pin.closed.connect(
            lambda w: self.pins.remove(w) if w in self.pins else None)
        self.pins.append(pin)
        pin.show()
        return pin

    def pin_clipboard(self):
        pix = QApplication.clipboard().pixmap()
        if pix.isNull():
            self._notify("贴图", "剪贴板里没有图片")
            return
        self.pin_pixmap(pix, QCursor.pos())

    def _notify(self, title: str, msg: str):
        if self.tray_available:
            self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 4000)
        else:
            print(f"[{title}] {msg}")

    def notify_ready(self):
        """启动就绪提示（整个启动过程只弹这一条）。

        把热键、托盘用法、退出方式一次说清，避免"启动"和"就绪"两条气泡。
        """
        if not self._hotkey_ok:
            tried = "、".join(DEFAULT_HOTKEYS)
            self._notify(
                "PyShot 热键不可用",
                f"热键（{tried}）都被占用，请双击托盘图标截图。\n"
                "可用环境变量 PYSHOT_HOTKEY 指定其他组合，"
                "例如 PYSHOT_HOTKEY=ctrl+alt+j")
            return
        self._notify(
            "PyShot 已启动",
            f"按 {self.hotkey_text} 框选截图，或双击托盘图标。\n"
            "右键托盘图标：滚动长截图 / 屏幕取色 / 贴图 / 退出。\n"
            "找不到图标时点任务栏右侧的 ∧ 展开。")

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "打开图片", str(Path.home()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            return
        self.open_editor(pix)

    def show_editor(self):
        """把编辑器恢复到前台；没有就开图片选择对话框。"""
        if self.editors:
            ed = self.editors[-1]
            ed.show()
            ed.setWindowState(ed.windowState() & ~Qt.WindowMinimized)
            ed.raise_()
            ed.activateWindow()
        else:
            self.open_image()

    def open_editor(self, pixmap: QPixmap):
        """把截图送进编辑器：已有编辑器就新增标签页，否则新建窗口。"""
        editor = self.editors[-1] if self.editors else None
        if editor is None:
            editor = EditorWindow()
            editor.setWindowIcon(make_tray_icon())
            editor.setAttribute(Qt.WA_DeleteOnClose)
            editor.destroyed.connect(
                lambda: self.editors.remove(editor) if editor in self.editors else None)
            editor.pin_requested.connect(lambda pix: self.pin_pixmap(pix, QCursor.pos()))
            editor.capture_requested.connect(self.capture_region)
            self.editors.append(editor)
        editor.add_canvas(pixmap)
        editor.set_hotkey_hint(self.hotkey_text)
        editor.show()
        editor.setWindowState(editor.windowState() & ~Qt.WindowMinimized)
        editor.raise_()
        editor.activateWindow()


def main():
    # --check-deps：只检查依赖，不开界面
    if "--check-deps" in sys.argv:
        print(deps_report())
        return

    # Windows 任务栏图标分组
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pyshot.app")
    except Exception:
        pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 托盘常驻
    app.setApplicationName("PyShot")
    apply_theme(app)

    core = PyShotApp(app)
    app.aboutToQuit.connect(core.shutdown)

    # 命令行直接给图片路径则直接进入编辑
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        pix = QPixmap(sys.argv[1])
        if not pix.isNull():
            core.open_editor(pix)
        else:
            core.capture_region()
    elif not core.tray_available:
        # 没有系统托盘的环境（极少数）：直接进截图，否则用户看不到任何入口
        core.capture_region()
    else:
        # 正常启动：只驻留托盘，不自动开始截图（避免启动就被全屏覆盖层挡住而以为卡死）
        core.notify_ready()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
