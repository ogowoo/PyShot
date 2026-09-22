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
from snipper import SnipperOverlay, grab_virtual_desktop
from style import apply_theme

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
HOTKEY_ID_BASE = 0x5053          # "PS"

# 候选全局热键（按优先级尝试，选第一个没被占用的）。
# 刻意避开被系统或常用软件注册的组合：
#   PrintScreen / Win+Shift+S  → Windows 11 截图工具
#   Ctrl+Alt+A / Ctrl+Shift+A / Alt+A → QQ、微信的截图
DEFAULT_HOTKEYS = ["ctrl+alt+x", "ctrl+shift+x", "ctrl+alt+f9", "ctrl+shift+f9"]

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


def register_global_hotkeys(candidates) -> dict:
    """依次尝试注册，返回 {热键 id: 显示名}（只注册第一个成功的）。

    candidates 为空表示不注册。注册失败（被其他程序占用）会自动尝试下一个。
    """
    user32 = ctypes.windll.user32
    for i, spec in enumerate(candidates):
        parsed = parse_hotkey(spec)
        if parsed is None:
            continue
        mods, vk, name = parsed
        hid = HOTKEY_ID_BASE + i
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
    """监听已注册的全局热键（Windows WM_HOTKEY）。"""

    def __init__(self, ids, callback):
        super().__init__()
        self.ids = set(ids)
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam in self.ids:
                self.callback()
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
        """注册全局热键：按候选列表挑第一个没被占用的组合。"""
        env_spec = os.environ.get("PYSHOT_HOTKEY")
        candidates = [env_spec] if env_spec else DEFAULT_HOTKEYS
        self._hotkeys = register_global_hotkeys(candidates)
        self._hotkey_ok = bool(self._hotkeys)
        self.hotkey_text = next(iter(self._hotkeys.values()), "")
        if self._hotkey_ok:
            self._filter = HotkeyFilter(self._hotkeys.keys(), self._on_hotkey)
            self.app.installNativeEventFilter(self._filter)
            print(f"[PyShot] 全局热键已注册：{self.hotkey_text}")
        else:
            print("[PyShot] 热键注册失败，已尝试：" + "、".join(candidates))

    # ---------- 托盘 ----------
    def _init_tray(self):
        if not self.tray_available:
            # 无托盘环境：关掉最后一个窗口就退出，避免程序"隐身"
            self.app.setQuitOnLastWindowClosed(True)
            return
        self.tray = QSystemTrayIcon(make_tray_icon(), self.app)
        menu = QMenu()
        act_region = QAction("区域截图", self.app)
        act_region.triggered.connect(lambda: self._deferred(self.capture_region))
        menu.addAction(act_region)
        self.act_region = act_region
        act_scroll = QAction("滚动长截图（滚轮自动）", self.app)
        act_scroll.setToolTip("框选可滚动区域，程序自己发滚轮逐屏拼接")
        act_scroll.triggered.connect(lambda: self._deferred(self.capture_scrolling))
        menu.addAction(act_scroll)
        act_scroll_drag = QAction("滚动长截图（点滚动条自动滚动）", self.app)
        act_scroll_drag.setToolTip(
            "框选区域后点一下滚动条滑块，程序按住滑块匀速拖拽滚动。\n"
            "远程桌面 / Citrix 里最稳：步长会实测标定，重叠充足")
        act_scroll_drag.triggered.connect(
            lambda: self._deferred(lambda: self.capture_scrolling(mode="drag")))
        menu.addAction(act_scroll_drag)
        act_scroll_key = QAction("滚动长截图（PageDown 自动滚动）", self.app)
        act_scroll_key.setToolTip(
            "框选区域后程序发送 PageDown / 空格翻页。\n"
            "适合没有滚动条的应用")
        act_scroll_key.triggered.connect(
            lambda: self._deferred(lambda: self.capture_scrolling(mode="key")))
        menu.addAction(act_scroll_key)
        act_scroll_manual = QAction("滚动长截图（手动滚动）", self.app)
        act_scroll_manual.setToolTip(
            "自己用滚轮/Page Down 滚动，程序负责逐帧拼接。\n"
            "适用于 Citrix、远程桌面等无法注入滚轮的窗口")
        act_scroll_manual.triggered.connect(
            lambda: self._deferred(lambda: self.capture_scrolling(manual=True)))
        menu.addAction(act_scroll_manual)
        act_full = QAction("全屏截图", self.app)
        act_full.triggered.connect(lambda: self._deferred(self.capture_fullscreen))
        menu.addAction(act_full)
        menu.addSeparator()
        act_color = QAction("屏幕取色", self.app)
        act_color.setToolTip("单击屏幕任意位置，复制色值到剪贴板")
        act_color.triggered.connect(lambda: self._deferred(self.pick_color))
        menu.addAction(act_color)
        act_pin_clip = QAction("贴出剪贴板图片", self.app)
        act_pin_clip.triggered.connect(self.pin_clipboard)
        menu.addAction(act_pin_clip)
        act_open = QAction("打开图片编辑…", self.app)
        act_open.triggered.connect(self.open_image)
        menu.addAction(act_open)
        act_editor = QAction("打开编辑器", self.app)
        act_editor.setToolTip("把编辑器窗口恢复到前台（取消截图后找不到编辑器时点这里）")
        act_editor.triggered.connect(self.show_editor)
        menu.addAction(act_editor)
        menu.addSeparator()
        act_quit = QAction("退出 PyShot", self.app)
        act_quit.triggered.connect(self.app.quit)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        if self._hotkey_ok:
            act_region.setText(f"区域截图 ({self.hotkey_text})")
            self.tray.setToolTip(
                f"PyShot 截图工具\n{self.hotkey_text} 框选截图 · "
                "双击图标截图 · 右键退出")
        else:
            self.tray.setToolTip("PyShot 截图工具\n双击图标截图 · 右键退出")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        # 注意：启动提示不在这里弹 —— 由 notify_ready() 统一负责，
        # 否则构造托盘和 main() 会各弹一次，用户看到两个气泡。

    def _on_hotkey(self):
        # 来自原生消息回调（WM_HOTKEY），延后一拍再开覆盖层
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

    def capture_fullscreen(self):
        self._prepare_capture()
        # 等最小化动画结束再抓，否则窗口残影会进图
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
