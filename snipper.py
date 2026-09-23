# -*- coding: utf-8 -*-
"""全屏覆盖层：框选截图区域 / 屏幕取色，带放大镜、尺寸和色值提示。

模式
====
- region：拖拽框选，松开后同时发出 captured(pixmap) 和 region_selected(rect)
- color ：单击取色，发出 color_picked(QColor)

用法::

    snipper = SnipperOverlay()                # 或 SnipperOverlay("color")
    snipper.captured.connect(on_pixmap)
    snipper.cancelled.connect(on_cancel)
    snipper.start()
"""
import ctypes
import weakref

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QGuiApplication, QImage,
                           QPainter, QPainterPath, QPen, QPixmap, QRegion)
from PySide6.QtWidgets import QWidget
from i18n import tr
# 诊断日志：直接顶层导入（**不要**用 try/except 包着导入 —— 单文件合并时
# 本地导入行会被删掉，留下一个空的 try 块，直接语法错误）
from diag import log as _dlog, timed as _dtimed

# ---------------------------------------------------------------- 实例注册表
# 覆盖层是**无父窗口**的顶层窗口 —— findChildren() 找不到它们。
# 一旦列表被重建（屏幕组合变化）或某次流程中途异常，旧实例就可能没人管、
# 永远留在屏幕上挡住一切（用户表现："遮罩挡住了"）。
# 所以留一份全局弱引用表，收尾时一律收掉，不依赖任何列表。
_ALL_OVERLAYS = weakref.WeakSet()


def finish_all_overlays():
    """把所有还活着的覆盖层收起来（兜底）。返回处理了几个。"""
    n = 0
    for ov in list(_ALL_OVERLAYS):
        try:
            if ov.isVisible() or getattr(ov, "_active", False):
                ov.finish()
            ov.hide()
            n += 1
        except Exception:                          # noqa: BLE001
            continue
    return n


MASK_COLOR = QColor(6, 10, 18, 150)   # 遮罩：偏深的蓝黑，任何背景都能看出"已进入截图状态"
VK_LBUTTON = 0x01
user32 = ctypes.windll.user32

# 覆盖层窗口类型（测试可覆盖，用于对比不同标志对首屏速度的影响）
OVERLAY_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                 | Qt.Tool | Qt.BypassWindowManagerHint)

MAG_ZOOM = 9                      # 放大倍数（整数，保证像素格对齐）
MAG_CELL = 15                     # 放大镜覆盖的源像素数（奇数，有正中心像素）
MAG_SIZE = MAG_CELL * MAG_ZOOM    # 放大镜边长 135（屏幕像素）


def screens_and_geometry() -> tuple:
    """返回 (所有屏幕, 虚拟桌面逻辑矩形)。"""
    screens = QGuiApplication.screens()
    geo = QRect()
    for s in screens:
        geo = geo.united(s.geometry()) if not geo.isNull() else s.geometry()
    return screens, geo


def region_to_screen_pixels(region: QRect, screen_geo: QRect,
                            dpr: float) -> QRect:
    """把逻辑屏幕坐标的区域，换算成某块屏幕上抓屏图里的物理像素矩形。

    独立成纯函数便于测试（含负坐标的多屏布局、混合 DPI 都能算对）。
    """
    local = region.translated(-screen_geo.left(), -screen_geo.top())
    return QRect(int(round(local.x() * dpr)), int(round(local.y() * dpr)),
                 int(round(local.width() * dpr)),
                 int(round(local.height() * dpr)))


def grab_logical_region(region: QRect) -> QPixmap:
    """按逻辑屏幕坐标抓一块区域：自动选中那块屏幕，并按它的 dpr 精确裁剪。

    多屏 + 混合 DPI 下这是唯一正确的做法（不能用主屏 dpr 去处理所有屏）。
    """
    screen = QGuiApplication.screenAt(region.center())
    if screen is None:                      # 区域中心不在任何屏上，退到主屏
        screen = QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio() or 1.0)
    shot = screen.grabWindow(0)
    src = region_to_screen_pixels(region, screen.geometry(), dpr)
    out = shot.copy(src.intersected(shot.rect()))
    out.setDevicePixelRatio(dpr)
    return out


def grab_screen(screen) -> QPixmap:
    """抓取一整块显示器；常规抓屏是空白/纯色时回退 PrintWindow。

    用于「全屏截图」与托盘里的「截取指定显示器」。
    """
    geo = screen.geometry()
    pix = grab_logical_region(geo)
    from capture_utils import grab_region_printwindow, pixmap_is_blank
    if not pixmap_is_blank(pix):
        return pix
    # 硬件加速 / 内容保护窗口（Citrix、远程桌面常见）：退到 PrintWindow。
    # 需要"桌面物理像素"坐标，所以要按该屏 dpr 换算。
    dpr = float(screen.devicePixelRatio() or 1.0)
    physical = QRect(int(round(geo.x() * dpr)), int(round(geo.y() * dpr)),
                     int(round(geo.width() * dpr)),
                     int(round(geo.height() * dpr)))
    alt = grab_region_printwindow(physical, dpr)
    if alt is not None and not pixmap_is_blank(alt):
        return alt
    return pix


def grab_virtual_desktop() -> tuple[QPixmap, QRect]:
    """抓取所有屏幕拼成一张图，返回 (pixmap, 虚拟桌面逻辑矩形)。

    以参考 dpr（主屏）合成，每块屏按自己的 dpr 独立抓取后按逻辑位置摆放：
    单 DPI 环境下是像素精确的；混合 DPI 下次屏内容会按参考比例重采样
    （区域截图不受影响 —— 那条路径走 grab_logical_region，按屏精确裁剪）。
    """
    screens, geo = screens_and_geometry()
    if not screens:
        return QPixmap(), QRect()
    ref = float(QGuiApplication.primaryScreen().devicePixelRatio() or 1.0)
    big = QPixmap(int(geo.width() * ref), int(geo.height() * ref))
    big.setDevicePixelRatio(ref)
    big.fill(Qt.black)
    p = QPainter(big)
    for s in screens:
        shot = s.grabWindow(0)
        if shot.isNull():
            continue
        local = s.geometry().translated(-geo.left(), -geo.top())
        target = QRectF(local.x() * ref, local.y() * ref,
                        local.width() * ref, local.height() * ref)
        p.drawPixmap(target, shot, QRectF(shot.rect()))
    p.end()
    return big, geo


class SnipperOverlay(QWidget):
    captured = Signal(QPixmap)
    region_selected = Signal(QRect)   # 逻辑屏幕坐标，滚动截图用
    point_selected = Signal(QPoint)   # 单击选一个点（如滚动条滑块）
    color_picked = Signal(QColor)
    cancelled = Signal()

    def __init__(self, mode: str = "region", screen=None):
        """mode: "region" 框选截图 | "color" 屏幕取色 | "scroll" 只选区 | "point" 选点

        screen: 该覆盖层负责的显示器。**每个显示器一个覆盖层实例** ——
        单个窗口横跨多显示器在 Windows 每显示器 DPI 下会被裁剪/缩放，直接不可用。
        """
        super().__init__(None, OVERLAY_FLAGS)
        self.mode = mode
        self.screen = screen or QGuiApplication.primaryScreen()
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._bg: QPixmap | None = None
        self._img: QImage | None = None   # 取色用的缓存
        self._geo = QRect()
        self._origin = QPoint()
        self._current = QPoint()
        self._selecting = False
        self._active = False              # 是否处于截图会话中
        self._warmed = False
        # “选滚动条”模式：选区外遮罩、选区内鼠标穿透（能真的点到应用里的滚动条）
        self._point_local = QRect()
        self._point_pressed = False
        self._point_timer = QTimer(self)
        self._point_timer.setInterval(25)
        _ALL_OVERLAYS.add(self)   # 见文件头的注册表说明
        self._point_timer.timeout.connect(self._poll_point_click)

    def screen_geometry(self) -> QRect:
        """本覆盖层覆盖的显示器逻辑矩形。"""
        return self.screen.geometry()

    # ---------- 预热 ----------
    def warmup(self, hold_ms: int = 3000):
        """启动时预热窗口，消除"首次截图遮罩迟迟不出现"。

        实测（Windows）：进程内第一个置顶全屏窗口虽然很早 paintEvent 就画完了，
        但系统要好几秒才真正把它合成上屏（4~5 秒）；而一旦上屏过，之后每次
        show() 只要 ~0.3 秒。所以这里在启动时以**完全透明 + 鼠标穿透**的方式
        先上屏一次，代价在启动阶段付掉，用户第一次截图就是快的。

        透明（opacity=0）不会被合成进屏幕画面，因此也不会污染截图。
        """
        if self._warmed:
            return
        self._warmed = True
        self.setGeometry(self.screen.geometry())
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        QTimer.singleShot(hold_ms, self._end_warmup)

    def _end_warmup(self):
        if self._active:          # 用户已经自己开始截图了，别去隐藏
            return
        self.hide()
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._can_exclude = False      # 能否把自己排除在抓屏之外

    # ---------- 生命周期 ----------
    def start(self, mode: str | None = None):
        if mode:
            self.mode = mode
        # 万一在预热期间就开始截图：恢复正常不透明度并接收鼠标事件
        self.setWindowOpacity(1.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._active = True
        self._selecting = False
        self._origin = QPoint(-1, -1)
        self._current = QPoint(-1, -1)
        self._geo = self.screen.geometry()
        # **必须"先抓屏、后显示"**。
        # 曾经为了降低首屏延迟改成"先显示遮罩、再抓屏"，靠
        # SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) 把遮罩排除在抓屏之外；
        # 但实测该排除在真实环境不可靠（Qt 的窗口带分层样式时会被忽略），
        # 结果抓到的整张图就是**我们自己的遮罩**（纯深色 + 蓝色选框边）——
        # 用户截出来的图全是废的。所以回到物理上不可能拍到自己的顺序：
        # 先抓本屏底图（多屏/混合 DPI 下按各自 dpr 裁剪才准确），再显示遮罩。
        with _dtimed("遮罩·抓底图", f"屏={self.screen.name()} "
                                    f"dpr={self.screen.devicePixelRatio()}"):
            self._bg = self.screen.grabWindow(0)
            self._img = self._bg.toImage() if not self._bg.isNull() else None
        _dlog("遮罩·抓底图结果", self.bg_report())
        if self._bg.isNull():
            self._ensure_bg()                      # 抓失败：兜底一张，别让流程断
        # 用显式几何 + show()，比 showFullScreen() 在多屏/首次显示时更可靠地铺满整屏
        with _dtimed("遮罩·显示窗口", f"geo={self._geo.width()}x"
                                     f"{self._geo.height()}"):
            self.setGeometry(self._geo)
            self.show()
            if self.geometry() != self._geo:
                self.setGeometry(self._geo)   # 首次上屏尺寸不对时才再钉一次
            self.raise_()
            self.activateWindow()
            # 只有"本进程当前没有前台窗口"时才走原生抢前台 ——
            # 正常情况下这一步是白花钱（实测 SetWindowPos+SetForegroundWindow
            # +SetActiveWindow 三连是显示阶段的大头）。
            try:
                from PySide6.QtWidgets import QApplication
                need_force = QApplication.activeWindow() is None
            except Exception:                      # noqa: BLE001
                need_force = True
            if need_force:
                try:
                    from capture_utils import force_foreground
                    _dlog("遮罩·抢前台", "无前台窗口，启用原生抢前台")
                    force_foreground(int(self.winId()))
                except Exception:                  # noqa: BLE001
                    pass
        # 注意：这里不能用 repaint() —— 对尚未映射完成的窗口强制同步绘制后，
        # Qt 不会再补一次绘制，窗口就会"在但没画出来"（动一下鼠标才出现）。
        self.update()
        for delay in (0, 120):           # 兜底两次即可（原来三次，纯属多花时间）
            QTimer.singleShot(delay, self._ensure_cover)

    def bg_report(self) -> str:
        """底图自检信息（写进诊断日志，方便确认有没有拍到自己/抓成空白）。"""
        try:
            if self._bg is None or self._bg.isNull():
                return "底图=空"
            img = self._bg.toImage()
            w, h = img.width(), img.height()
            colors = set()
            total = n = 0
            for y in range(0, h, max(1, h // 12)):
                for x in range(0, w, max(1, w // 12)):
                    c = img.pixelColor(x, y)
                    colors.add(c.name())
                    total += c.red() + c.green() + c.blue()
                    n += 1
            avg = int(total / (n * 3)) if n else -1
            return (f"底图={w}x{h} 平均亮度={avg} 采样色数={len(colors)}"
                    + ("（疑似纯色/拍到自己！）" if len(colors) <= 2 else ""))
        except Exception:                          # noqa: BLE001
            return "底图=自检失败"

    def _ensure_bg(self):
        """确保底图已经就绪；没有就地抓一次，实在抓不到也要给一张兜底的。

        交互（框选/取色）需要底图；"先显示遮罩、后抓屏"期间底图是空的，
        这里保证不会因为底图没到就把用户的操作全部忽略（那会表现成遮罩没反应）。
        """
        if self._bg is not None and not self._bg.isNull():
            return self._bg
        try:
            self._bg = self.screen.grabWindow(0)
        except Exception:                          # noqa: BLE001
            self._bg = None
        if self._bg is None or self._bg.isNull():
            # 兜底：纯色图，保证后续交互不会因为 None 崩掉/被忽略
            pm = QPixmap(self._geo.size() if self._geo.isValid()
                         else self.size())
            pm.fill(QColor(24, 26, 32))
            pm.setDevicePixelRatio(self.devicePixelRatioF() or 1.0)
            self._bg = pm
        self._img = self._bg.toImage()
        self.update()
        return self._bg


    def finish(self):
        """结束本次截图会话：隐藏窗口但保留原生窗口，下次截图更快。"""
        _dlog("遮罩·收起", f"屏={self.screen.name()} active={self._active} "
                          f"visible={self.isVisible()}")
        self._point_timer.stop()
        self._clear_mask()
        self._point_local = QRect()
        self._active = False
        self._selecting = False
        self._bg = None
        self._img = None
        self.hide()

    # ---------- 选滚动条：选区外遮罩 + 选区内可点击 ----------
    def set_point_hole(self, region_global: QRect):
        """把选区"挖空"：外面继续遮罩，里面鼠标穿透 —— 用户能真的点到滚动条。

        用窗口 mask 实现：窗口在 mask 之外的区域既不绘制也不接收鼠标，
        事件自然落到下面的应用上。
        """
        local = region_global.translated(-self._geo.left(),
                                         -self._geo.top()).intersected(self.rect())
        self._point_local = local
        if local.width() > 2 and local.height() > 2:
            self.setMask(QRegion(self.rect()).subtracted(QRegion(local)))
        else:
            self._clear_mask()            # 与这块屏没有交集：整屏遮罩
        self._point_pressed = False
        self._active = True
        self._point_timer.start()
        self.update()

    def _clear_mask(self):
        if not self.mask().isEmpty():
            self.setMask(QRegion())

    def _poll_point_click(self):
        """在选区内轮询真实左键按下（因为选区内事件被穿透给了应用）。"""
        if not self._active or self.mode != "point":
            self._point_timer.stop()
            return
        try:
            pressed = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        except Exception:                     # noqa: BLE001
            pressed = False
        if pressed and not self._point_pressed:
            self._point_pressed = True
            pos = QCursor.pos()
            if self._point_local.contains(pos - self._geo.topLeft()):
                self._point_timer.stop()
                self._clear_mask()
                self.finish()
                self.point_selected.emit(pos)
        elif not pressed:
            self._point_pressed = False

    def _ensure_cover(self):
        _dlog("遮罩·铺满兜底", f"active={self._active} "
                              f"visible={self.isVisible()} "
                              f"bg={'有' if self._bg is not None else '无'}")
        """兜底：确保覆盖层真的铺满并且是画出来的。

        注意：**不能**因为 _bg 还没抓回来就跳过 —— 抓屏是延后做的（先显示遮罩、
        后抓底图），这里要是等 _bg，头几帧的兜底就全空转了，多屏/缩放下遮罩
        可能压根没铺好（曾因此表现成"遮罩卡住不动"）。
        """
        if not self._active or not self.isVisible():
            return
        if self.geometry() != self._geo:
            self.setGeometry(self._geo)
        self.raise_()
        self.update()

    def closeEvent(self, e):
        self._point_timer.stop()
        self._clear_mask()
        self._active = False
        self._bg = None
        self._img = None
        super().closeEvent(e)

    def color_at(self, logical_pos: QPoint) -> QColor:
        """读取覆盖层逻辑坐标处的颜色。"""
        if self._img is None:
            return QColor()
        dpr = self._bg.devicePixelRatio()
        x = int(logical_pos.x() * dpr)
        y = int(logical_pos.y() * dpr)
        if 0 <= x < self._img.width() and 0 <= y < self._img.height():
            return self._img.pixelColor(x, y)
        return QColor()

    # ---------- 交互 ----------
    def mousePressEvent(self, e):
        if not self._active:                       # 已结束：忽略残留事件
            return
        # 右键/取消必须**永远**能用，不能因为底图还没抓回来就失灵
        if e.button() == Qt.RightButton:
            self._cancel()
            return
        if e.button() != Qt.LeftButton:
            return
        self._ensure_bg()                          # 底图没到就补上，别忽略操作
        if self.mode == "color":
            color = self.color_at(e.position().toPoint())
            if color.isValid():
                self.color_picked.emit(color)
            self.finish()
            return
        if self.mode == "point":
            # 选区内的点击会被穿透给应用（由 _poll_point_click 轮询捕获），
            # 落在遮罩区的左键一律忽略，避免误当成滑块位置。
            return
        self._origin = e.position().toPoint()
        self._current = self._origin
        self._selecting = True
        self.update()

    def mouseMoveEvent(self, e):
        if not self._active:
            return
        if self._bg is None:
            return                                 # 还没按下去，等底图即可
        self._current = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e):
        if (not self._active or e.button() != Qt.LeftButton
                or not self._selecting):
            return
        self._ensure_bg()                          # 保证有底图可裁
        self._selecting = False
        rect = QRect(self._origin, self._current).normalized().intersected(self.rect())
        if rect.width() < 6 or rect.height() < 6:
            self.update()
            return
        dpr = self._bg.devicePixelRatio()
        img_rect = QRect(int(rect.x() * dpr), int(rect.y() * dpr),
                         int(rect.width() * dpr), int(rect.height() * dpr))
        # 滚动截图只需要选区坐标：绝不能同时发 captured，
        # 否则宿主会当成普通截图去打开/前置编辑器，正好盖住要滚动的区域。
        if self.mode == "scroll":
            self.finish()
            self.region_selected.emit(rect.translated(self._geo.topLeft()))
            return

        result = self._bg.copy(img_rect)
        result.setDevicePixelRatio(dpr)
        # 常规抓屏拿不到内容时（远程桌面/虚拟化应用的硬件加速或内容保护），
        # 用 PrintWindow 让目标窗口自己渲染一遍再试一次
        try:
            from capture_utils import (grab_region_printwindow,
                                       looks_like_missing_content)
            if looks_like_missing_content(result):
                phys = QRect(int((rect.x() + self._geo.x()) * dpr),
                             int((rect.y() + self._geo.y()) * dpr),
                             img_rect.width(), img_rect.height())
                alt = grab_region_printwindow(phys, dpr)
                if alt is not None and not looks_like_missing_content(alt):
                    result = alt
        except Exception:                     # noqa: BLE001
            pass                              # 回退失败就用原图
        self.finish()              # 先隐藏再来发信号，避免处理期间残留事件重入
        # 逻辑屏幕坐标（供滚动截图等需要屏幕位置的调用方）
        self.region_selected.emit(rect.translated(self._geo.topLeft()))
        self.captured.emit(result)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._cancel()

    def _cancel(self):
        if not self._active:
            return
        self.finish()
        self.cancelled.emit()

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        has_bg = self._bg is not None and not self._bg.isNull()
        if has_bg:
            p.drawPixmap(0, 0, self._bg)
        else:
            p.fillRect(self.rect(), QColor(24, 26, 32))   # 抓图失败也要有遮罩

        if self.mode == "point":
            # 选滚动条：窗口 mask 已经"挖空"了选区，绘制只会落在遮罩区
            p.fillRect(self.rect(), MASK_COLOR)
            rect = self._point_local
            if rect.width() > 2 and rect.height() > 2:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(61, 139, 253), 3))
                p.drawRect(rect.adjusted(-3, -3, 2, 2))
                p.setPen(QPen(QColor(61, 139, 253, 90), 1, Qt.DashLine))
                p.drawLine(0, rect.center().y(), max(0, rect.left()),
                           rect.center().y())
                p.drawLine(rect.right(), rect.center().y(), self.width(),
                           rect.center().y())
            self._draw_hint(p, self._hint_anchor(rect))
            return

        # 取色模式不压暗（保证看到的颜色真实），其余模式整体压暗
        if self.mode != "color":
            p.fillRect(self.rect(), MASK_COLOR)

        rect = QRect(self._origin, self._current).normalized().intersected(self.rect())
        selecting = (self.mode in ("region", "scroll") and self._selecting
                     and rect.width() >= 2 and rect.height() >= 2)
        if selecting:
            # 选区内恢复原图亮度（源矩形必须夹在图像范围内，否则 drawPixmap 抛异常）
            if has_bg:
                dpr = self._bg.devicePixelRatio()
                src = QRect(int(rect.x() * dpr), int(rect.y() * dpr),
                            int(rect.width() * dpr), int(rect.height() * dpr))
                src = src.intersected(self._bg.rect())
                if not src.isEmpty():
                    p.drawPixmap(QRectF(rect), self._bg, QRectF(src))
            self._draw_guides(p, rect)
            self._draw_selection_border(p, rect)
            self._draw_size_label(p, rect)
        else:
            # 未开始拖拽：用全屏十字准线告诉用户当前落点
            self._draw_crosshair(p, self._current)

        if has_bg:                       # 预热显示等场景下 _bg 可能为空
            self._draw_magnifier(p, self._current)
        self._draw_hint(p)

    # ---------- 选区视觉强化 ----------
    def _draw_guides(self, p: QPainter, rect: QRect):
        """把选区四条边延伸到全屏，方便看清边界对齐到了哪里。"""
        pen = QPen(QColor(61, 139, 253, 170), 1, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(0, rect.top(), self.width(), rect.top())
        p.drawLine(0, rect.bottom(), self.width(), rect.bottom())
        p.drawLine(rect.left(), 0, rect.left(), self.height())
        p.drawLine(rect.right(), 0, rect.right(), self.height())

    def _draw_crosshair(self, p: QPainter, pos: QPoint):
        if pos.x() < 0 or pos.y() < 0:
            return
        p.setPen(QPen(QColor(61, 139, 253, 150), 1))
        p.drawLine(0, pos.y(), self.width(), pos.y())
        p.drawLine(pos.x(), 0, pos.x(), self.height())

    def _draw_selection_border(self, p: QPainter, rect: QRect):
        """外白内蓝双描边 + 四角把手：任何背景色下都清晰可见。"""
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 220), 1))
        p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.setPen(QPen(QColor(61, 139, 253), 2))
        p.drawRect(rect.adjusted(1, 1, -2, -2))
        # 四角把手
        hs = 5
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.setBrush(QColor(61, 139, 253))
        for cx, cy in [(rect.left(), rect.top()), (rect.right(), rect.top()),
                       (rect.left(), rect.bottom()), (rect.right(), rect.bottom())]:
            p.drawRect(QRect(cx - hs // 2, cy - hs // 2, hs, hs))

    def _draw_size_label(self, p: QPainter, rect: QRect):
        text = f"{rect.width()} × {rect.height()}"
        font = p.font()
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 18
        h = metrics.height() + 10
        below = rect.top() - h - 6 <= 0
        x = rect.left()
        y = rect.bottom() + 6 if below else rect.top() - h - 6
        x = min(max(0, x), self.width() - w)
        y = min(max(0, y), self.height() - h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(15, 17, 22, 225))
        p.drawRoundedRect(x, y, w, h, 5, 5)
        p.setPen(QPen(QColor(61, 139, 253), 1))
        p.drawRoundedRect(x, y, w, h, 5, 5)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)
        p.setFont(QFont())

    def _draw_magnifier(self, p: QPainter, pos: QPoint):
        dpr = self._bg.devicePixelRatio()
        half = MAG_CELL // 2
        src = QRect(int((pos.x() - half) * dpr), int((pos.y() - half) * dpr),
                    int(MAG_CELL * dpr), int(MAG_CELL * dpr))
        # 放大镜位置：光标右下，越界则翻转到左上
        mx = pos.x() + 18
        my = pos.y() + 18
        if mx + MAG_SIZE > self.width() - 4:
            mx = pos.x() - MAG_SIZE - 18
        if my + MAG_SIZE > self.height() - 4:
            my = pos.y() - MAG_SIZE - 18
        target = QRect(mx, my, MAG_SIZE, MAG_SIZE)
        p.save()
        p.setClipRect(target)
        p.fillRect(target, QColor(40, 40, 40))
        # 源区域夹取到图像内，并同步修正目标子矩形（靠近屏幕边缘时）
        clamped = src.intersected(self._bg.rect())
        if not clamped.isEmpty():
            scale = MAG_SIZE / src.width()
            sub = QRectF(mx + (clamped.x() - src.x()) * scale,
                         my + (clamped.y() - src.y()) * scale,
                         clamped.width() * scale, clamped.height() * scale)
            p.drawPixmap(sub, self._bg, QRectF(clamped))
        # 网格线（整数格宽，逐像素对齐）
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        for i in range(1, MAG_CELL):
            p.drawLine(mx + i * MAG_ZOOM, my, mx + i * MAG_ZOOM, my + MAG_SIZE)
            p.drawLine(mx, my + i * MAG_ZOOM, mx + MAG_SIZE, my + i * MAG_ZOOM)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(target)
        # 红框标出真正取样的中心像素（与 color_at 取样点一致）
        half = MAG_CELL // 2
        p.setPen(QPen(QColor(229, 57, 53), 2))
        p.drawRect(mx + half * MAG_ZOOM, my + half * MAG_ZOOM,
                   MAG_ZOOM, MAG_ZOOM)
        self._draw_color_label(p, pos, mx, my)

    def _hint_anchor(self, rect: QRect) -> QPoint:
        """给提示条挑一个落在遮罩区的位置（选区内部是穿透的，画在那看不见）。"""
        w = self.width()
        if rect.top() > 60:                     # 选区上方有空间
            return QPoint((w - 420) // 2, max(8, rect.top() - 56))
        if rect.bottom() < self.height() - 70:  # 选区下方有空间
            return QPoint((w - 420) // 2, rect.bottom() + 12)
        return QPoint((w - 420) // 2, 24)

    def _draw_hint(self, p: QPainter, anchor: QPoint | None = None):
        """提示条：明确告知当前模式和退出方式，避免看起来像卡死。"""
        if self.mode == "color":
            text = tr("屏幕取色：单击复制色值    ·    Esc / 右键 取消")
        elif self.mode == "scroll":
            text = tr("拖拽选择要滚动截图的区域    ·    Esc / 右键 取消")
        elif self.mode == "point":
            text = tr("蓝框内可直接点击滚动条【滑块】→ 自动开始滚动    ·    Esc 取消")
        else:
            text = tr("拖拽选择截图区域    ·    Esc / 右键 取消")
        metrics = p.fontMetrics()
        w = metrics.horizontalAdvance(text) + 36
        h = metrics.height() + 16
        x = (self.width() - w) // 2
        y = 24
        if anchor is not None:
            x = min(max(4, anchor.x()), max(4, self.width() - w - 4))
            y = anchor.y()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(x, y, w, h, 8, 8)
        p.setPen(QColor(235, 238, 242))
        p.drawText(QRect(x, y, w, h), Qt.AlignCenter, text)

    def _draw_color_label(self, p: QPainter, pos: QPoint, mx: int, my: int):
        """在放大镜下方显示光标处的色值。"""
        color = self.color_at(pos)
        if not color.isValid():
            return
        text = color.name().upper()
        rgb = f"{color.red()},{color.green()},{color.blue()}"
        metrics = p.fontMetrics()
        w = max(metrics.horizontalAdvance(text), metrics.horizontalAdvance(rgb)) + 14
        h = metrics.height() * 2 + 10
        x = mx
        y = my + MAG_SIZE + 6
        if y + h > self.height() - 4:
            y = my - h - 6
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(x, y, w, h, 4, 4)
        # 色块
        p.setBrush(color)
        p.drawRect(x + 4, y + 5, metrics.height() - 2, metrics.height() - 2)
        p.setPen(QColor(255, 255, 255))
        p.drawText(x + 8 + metrics.height(), y + 5 + metrics.ascent(), text)
        p.drawText(QRect(x, y + metrics.height() + 5, w, metrics.height() + 5),
                   Qt.AlignCenter, rgb)
