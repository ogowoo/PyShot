# -*- coding: utf-8 -*-
"""编辑器窗口：左侧工具栏 + 顶部属性栏 + 可缩放画布。"""
import math

from PySide6.QtCore import (QPoint, QPointF, QRect, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QGuiApplication, QIcon, QKeySequence,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QTabBar,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget,
                               QButtonGroup)

from shapes import (ArrowShape, EllipseShape, HighlightShape, LineShape,
                    MosaicShape, PenShape, RectShape, Shape, StepShape,
                    TextShape, WatermarkShape, clone_shapes)
from style import ACCENT, SpinBox, make_icon, make_tool_icon
from watermark import WatermarkDialog, load_default, save_default

TOOLS = [
    ("select",    "选择",   "选择并移动已有标注（Delete 删除）"),
    ("rect",      "矩形",   "拖拽画矩形，Shift 画正方形"),
    ("ellipse",   "椭圆",   "拖拽画椭圆，Shift 画正圆"),
    ("line",      "直线",   "拖拽画直线，Shift 锁定水平/垂直/45°"),
    ("arrow",     "箭头",   "拖拽画箭头，指引方向"),
    ("pen",       "画笔",   "自由手绘"),
    ("step",      "序号",   "单击放置递增序号，做步骤指引"),
    ("text",      "文字",   "单击后输入文字，Enter 确认"),
    ("highlight", "高亮",   "拖拽涂抹半透明高亮"),
    ("mosaic",    "马赛克", "拖拽对区域打码"),
    ("pick",      "取色",   "单击吸取图上颜色作为当前标注颜色"),
    ("crop",      "裁剪",   "拖拽选择保留区域，Enter 应用"),
]

PALETTE = ["#e53935", "#fb8c00", "#fdd835", "#43a047",
           "#1e88e5", "#8e24aa", "#ffffff", "#000000"]

HANDLE_SIZE = 8      # 选中图形四角/四边句柄的显示大小（屏幕像素）
HANDLE_HIT = 11      # 句柄的点击容差


class FlowLayout(QLayout):
    """可换行的水平布局：空间不够时自动把控件换到下一行。

    用来替代 QToolBar 做顶栏 —— QToolBar 在窗口变窄时会把放不下的控件
    吞进溢出"»"菜单，用户就找不到了；流式布局会直接换行，始终可见。
    """

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        """逐行排布：同一行内**垂直居中**（不同高度的控件才能对齐），
        放不下就换行。"""
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        right = eff.right() + 1
        x, y = eff.x(), eff.y()
        line_height = 0
        line = []                      # [(item, sizeHint, x)]

        def place_line():
            nonlocal y, line_height
            for it, hint, ix in line:
                if not test_only:
                    iy = y + (line_height - hint.height()) // 2   # 垂直居中
                    it.setGeometry(QRect(QPoint(ix, iy), hint))
            y += line_height + self._spacing
            line.clear()
            line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            if line and x + hint.width() > right:
                place_line()
                x = eff.x()
            line.append((item, hint, x))
            line_height = max(line_height, hint.height())
            x += hint.width() + self._spacing
        if line:
            for it, hint, ix in line:
                if not test_only:
                    iy = y + (line_height - hint.height()) // 2
                    it.setGeometry(QRect(QPoint(ix, iy), hint))
            y += line_height
        return max(self._spacing, y - rect.y() + m.bottom())


class Canvas(QWidget):
    """底图 + 标注列表的绘制与交互。坐标均为图像像素坐标。"""

    shapes_changed = Signal()
    color_picked = Signal(QColor)
    zoom_changed = Signal(float)
    escape_idle = Signal()   # Esc 按下且画布无任何待取消状态
    selection_changed = Signal(object)   # 当前选中的图形（或 None）

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.base_pixmap = QPixmap(pixmap)
        # 保留截图自带的 devicePixelRatio：图形坐标统一用"图像物理像素"，
        # 画布控件尺寸用"逻辑像素"（物理 / dpr），这样 100% 缩放时
        # 1 个图像像素恰好落在 1 个屏幕物理像素上，不会被系统放大而发虚。
        self.dpr = float(self.base_pixmap.devicePixelRatio() or 1.0)
        self.shapes: list = []
        self.tool = "select"
        self.color = QColor(PALETTE[0])
        self.pen_width = 3
        self.font_size = 20
        self.step_diameter = 36        # 序号圆直径，独立于字号
        self.step_counter = 1

        self.zoom = 1.0
        self._current: Shape | None = None   # 正在拖拽中的图形
        self._drag_start = QPointF()
        self._dragging = False
        self._moving: Shape | None = None    # 选择模式下拖动的图形
        self._move_last = QPointF()
        self._move_snapshot = False
        self._selected: Shape | None = None
        self._resizing: tuple | None = None   # (shape, handle_index)
        self._crop_rect: QRectF | None = None
        self._hover_pos = None   # 取色放大镜用的光标位置（窗口坐标）

        self._undo_stack: list = []
        self._redo_stack: list = []

        self._text_edit: QLineEdit | None = None
        self._text_pos = QPointF()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._apply_size()

    # ---------- 基础 ----------
    def _apply_size(self):
        """画布逻辑尺寸 = 图像物理像素 / dpr × 缩放。"""
        self.setFixedSize(max(1, round(self.base_pixmap.width() / self.dpr * self.zoom)),
                          max(1, round(self.base_pixmap.height() / self.dpr * self.zoom)))

    def to_image(self, widget_pos) -> QPointF:
        """控件坐标 → 图像物理像素坐标。"""
        return QPointF(widget_pos.x() * self.dpr / self.zoom,
                       widget_pos.y() * self.dpr / self.zoom)

    def clamp(self, p: QPointF) -> QPointF:
        r = QRectF(self.base_pixmap.rect())
        return QPointF(min(max(p.x(), r.left()), r.right()),
                       min(max(p.y(), r.top()), r.bottom()))

    # ---------- 撤销 / 重做 ----------
    def _snapshot(self):
        return (QPixmap(self.base_pixmap), clone_shapes(self.shapes),
                self.step_counter)

    def push_undo(self):
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > 60:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())

    def redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())

    def _restore(self, snap):
        self.base_pixmap, self.shapes, self.step_counter = snap
        self.base_pixmap = QPixmap(self.base_pixmap)
        self.shapes = clone_shapes(self.shapes)
        self._selected = None
        self._crop_rect = None
        self._apply_size()
        self.update()
        self.shapes_changed.emit()

    # ---------- 鼠标交互 ----------
    def mousePressEvent(self, e):
        self._commit_text()
        if e.button() != Qt.LeftButton:
            return
        pos = self.clamp(self.to_image(e.position()))
        self._drag_start = pos
        self._dragging = True

        if self.tool == "select":
            self._resizing = None
            # 先看是否点在缩放句柄上（优先于选中/移动）
            if self._selected is not None:
                hit = int(HANDLE_HIT / self.zoom) + 2
                for i, hp in enumerate(self._selected.handles()):
                    if (abs(hp.x() - pos.x()) <= hit and abs(hp.y() - pos.y()) <= hit):
                        self.push_undo()
                        self._resizing = (self._selected, i)
                        self._dragging = False
                        self.update()
                        return
            self._moving = None
            self._selected = None
            self._move_snapshot = False
            for shape in reversed(self.shapes):  # 最上层优先
                if shape.contains(pos, 6 / self.zoom):
                    self._selected = shape
                    self._moving = shape
                    self._move_last = pos
                    break
            self.selection_changed.emit(self._selected)
            self.update()
            return

        if self.tool == "crop":
            self._crop_rect = QRectF(pos, pos)
            self.update()
            return

        if self.tool == "pick":
            img = self.base_pixmap.toImage()
            c = img.pixelColor(int(pos.x()), int(pos.y()))
            self.color = c
            self.color_picked.emit(c)
            self._dragging = False
            return

        if self.tool == "text":
            self._open_text_editor(pos)
            self._dragging = False
            return

        if self.tool == "step":
            self.push_undo()
            self.shapes.append(StepShape(self.color, self.pen_width, pos,
                                         self.step_counter, self.font_size,
                                         self.step_diameter))
            self.step_counter += 1
            self._dragging = False
            self.update()
            self.shapes_changed.emit()
            return

        if self.tool == "pen":
            self._current = PenShape(self.color, self.pen_width, [pos])
        elif self.tool == "rect":
            self._current = RectShape(self.color, self.pen_width, QRectF(pos, pos))
        elif self.tool == "ellipse":
            self._current = EllipseShape(self.color, self.pen_width, QRectF(pos, pos))
        elif self.tool == "line":
            self._current = LineShape(self.color, self.pen_width, pos, pos)
        elif self.tool == "arrow":
            self._current = ArrowShape(self.color, self.pen_width, pos, pos)
        elif self.tool == "highlight":
            self._current = HighlightShape(self.color, self.pen_width, QRectF(pos, pos))
        elif self.tool == "mosaic":
            self._current = MosaicShape(self.color, self.pen_width, QRectF(pos, pos))
        self.update()

    def mouseMoveEvent(self, e):
        self._hover_pos = e.position()
        if self.tool == "pick":
            self.update()  # 刷新取色放大镜
        pos = self.clamp(self.to_image(e.position()))
        if self.tool == "select" and self._resizing is not None:
            shape, index = self._resizing
            shape.resize_by_handle(index, pos)
            self.update()
            return
        if self.tool == "select" and self._moving is not None:
            if not self._move_snapshot:
                self.push_undo()  # 移动开始前记录一次快照
                self._move_snapshot = True
            d = pos - self._move_last
            self._moving.move_by(d.x(), d.y())
            self._move_last = pos
            self.update()
            return
        if self.tool == "crop" and self._dragging and self._crop_rect is not None:
            self._crop_rect = QRectF(self._drag_start, pos)
            self.update()
            return
        if not self._dragging or self._current is None:
            return
        cur = self._current
        if isinstance(cur, PenShape):
            cur.add_point(pos)
        elif isinstance(cur, LineShape):
            p2 = pos
            if e.modifiers() & Qt.ShiftModifier:  # 锁定 45° 方向
                d = p2 - self._drag_start
                ang = round(math.atan2(d.y(), d.x()) / (math.pi / 4))
                length = math.hypot(d.x(), d.y())
                p2 = self._drag_start + QPointF(
                    length * math.cos(ang * math.pi / 4),
                    length * math.sin(ang * math.pi / 4))
            cur.p2 = p2
        else:  # 矩形类
            rect = QRectF(self._drag_start, pos)
            if e.modifiers() & Qt.ShiftModifier:  # 正方形
                side = max(abs(rect.width()), abs(rect.height()))
                sx = side if pos.x() >= self._drag_start.x() else -side
                sy = side if pos.y() >= self._drag_start.y() else -side
                rect = QRectF(self._drag_start,
                              self._drag_start + QPointF(sx, sy))
            cur.rect = rect.normalized()
        self.update()

    def leaveEvent(self, e):
        if self._hover_pos is not None:
            self._hover_pos = None
            if self.tool == "pick":
                self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.tool == "select":
            self._moving = None
            self._move_snapshot = False
            self._resizing = None
            self.shapes_changed.emit()
            return
        if self.tool == "crop":
            self._dragging = False
            return
        if self._current is not None:
            # 过滤掉过小的误触
            br = self._current.bounding_rect()
            too_small = (not isinstance(self._current, PenShape)
                         and br.width() < 3 and br.height() < 3)
            if isinstance(self._current, PenShape) and len(self._current.points) < 2:
                too_small = True
            if not too_small:
                self.push_undo()
                self.shapes.append(self._current)
                self.shapes_changed.emit()
            self._current = None
        self._dragging = False
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self.tool == "crop":
            self.apply_crop()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self._selected is not None and self._selected in self.shapes:
                self.push_undo()
                self.shapes.remove(self._selected)
                self._selected = None
                self.selection_changed.emit(None)
                self.update()
                self.shapes_changed.emit()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.tool == "crop":
                self.apply_crop()
            return
        if e.key() == Qt.Key_Escape:
            # 分层取消：文字输入 → 裁剪框 → 选中图形 → 绘制中 → 都空闲则请求关闭窗口
            if self._text_edit is not None:
                self._cancel_text()
            elif self._crop_rect is not None:
                self._crop_rect = None
                self.update()
            elif self._selected is not None:
                self._selected = None
                self.selection_changed.emit(None)
                self.update()
            elif self._current is not None:
                self._current = None
                self._dragging = False
                self.update()
            else:
                self.escape_idle.emit()
            return
        super().keyPressEvent(e)

    # ---------- 文字输入 ----------
    def _open_text_editor(self, pos: QPointF):
        self._text_pos = pos
        edit = QLineEdit(self)
        edit.setPlaceholderText("输入文字，Enter 确认 / Esc 取消")
        font = edit.font()
        font.setPixelSize(max(12, int(self.font_size * self.zoom)))
        edit.setFont(font)
        edit.setStyleSheet(f"color: {self.color.name()}; background: rgba(255,255,255,220);"
                           "border: 1px dashed #888;")
        edit.move(int(pos.x() * self.zoom), int(pos.y() * self.zoom))
        edit.resize(max(240, int(self.font_size * self.zoom * 12)), edit.sizeHint().height() + 6)
        edit.returnPressed.connect(self._commit_text)
        edit.editingFinished.connect(self._commit_text)
        edit.show()
        edit.setFocus()
        self._text_edit = edit

    def _cancel_text(self):
        """丢弃正在输入的文字。"""
        if self._text_edit is None:
            return
        edit = self._text_edit
        self._text_edit = None
        edit.blockSignals(True)   # 防止 editingFinished 触发提交
        edit.deleteLater()

    def _commit_text(self):
        if self._text_edit is None:
            return
        edit = self._text_edit
        self._text_edit = None
        text = edit.text().strip()
        edit.deleteLater()
        if text:
            self.push_undo()
            self.shapes.append(TextShape(self.color, self.pen_width, self._text_pos,
                                         text, self.font_size))
            self.update()
            self.shapes_changed.emit()

    # ---------- 裁剪 ----------
    def apply_crop(self):
        if self._crop_rect is None:
            return
        r = self._crop_rect.normalized().toAlignedRect().intersected(
            self.base_pixmap.rect())
        if r.width() < 10 or r.height() < 10:
            self._crop_rect = None
            self.update()
            return
        self.push_undo()
        cropped = self.base_pixmap.copy(r)
        cropped.setDevicePixelRatio(self.dpr)
        self.base_pixmap = cropped
        kept = []
        for shape in self.shapes:
            shape.translate(-r.x(), -r.y())
            if shape.bounding_rect().intersects(QRectF(self.base_pixmap.rect())):
                kept.append(shape)
        self.shapes = kept
        self._crop_rect = None
        self._selected = None
        self._apply_size()
        self.update()
        self.shapes_changed.emit()

    def cancel_crop(self):
        self._crop_rect = None
        self.update()

    # ---------- 序号大小 ----------
    def selected_step(self):
        """当前选中的序号图形（没有则返回 None）。"""
        return self._selected if isinstance(self._selected, StepShape) else None

    def resize_selected_step(self, diameter: float, push_undo: bool = True):
        step = self.selected_step()
        if step is None:
            return False
        if abs(step.diameter - diameter) < 0.5:
            return False
        if push_undo:
            self.push_undo()
        step.set_diameter(diameter)
        self.update()
        self.shapes_changed.emit()
        return True

    # ---------- 缩放 ----------
    def set_zoom(self, zoom: float):
        self.zoom = min(4.0, max(0.1, zoom))
        self._apply_size()
        self.update()
        self.zoom_changed.emit(self.zoom)

    # ---------- 导出 ----------
    def render_result(self) -> QPixmap:
        """导出为图像物理像素的完整结果（无损，不做任何缩放）。"""
        w, h = self.base_pixmap.width(), self.base_pixmap.height()
        out = QPixmap(w, h)          # 先在 dpr=1 的工作画布上按物理像素绘制
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        # 用显式源/目标矩形绘制，避免源 pixmap 的 dpr 影响落点尺寸
        p.drawPixmap(QRect(0, 0, w, h), self.base_pixmap,
                     QRect(0, 0, w, h))
        for shape in self.shapes:
            shape.draw(p, self)
        p.end()
        out.setDevicePixelRatio(self.dpr)   # 带上 dpr，显示按逻辑尺寸、像素不丢
        return out

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.save()
        painter.scale(self.zoom, self.zoom)
        # 缩小时用平滑滤波（不然文字发虚/锯齿）；放大时保持像素锐利；
        # 只对底图启用，马赛克等图形的像素化效果不受影响。
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 1.0)
        painter.drawPixmap(0, 0, self.base_pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        for shape in self.shapes:
            shape.draw(painter, self)
        if self._current is not None:
            self._current.draw(painter, self)
        # 选中框 + 缩放句柄（细实线 + 白色句柄，现代编辑器风格）
        if self._selected is not None and self.tool == "select":
            rect = self._selected.bounding_rect().adjusted(-2, -2, 2, 2)
            painter.setPen(QPen(QColor(ACCENT), 1.4 / self.zoom))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            hs = HANDLE_SIZE / self.zoom
            painter.setPen(QPen(QColor(ACCENT), 1.2 / self.zoom))
            painter.setBrush(QColor("#ffffff"))
            for hp in self._selected.handles():
                painter.drawRect(QRectF(hp.x() - hs / 2, hp.y() - hs / 2, hs, hs))
        # 裁剪遮罩
        if self.tool == "crop" and self._crop_rect is not None:
            rect = self._crop_rect.normalized()
            full = QRectF(self.base_pixmap.rect())
            path = QPainterPath()
            path.addRect(full)
            path.addRect(rect)
            painter.fillPath(path, QColor(0, 0, 0, 130))
            painter.setPen(QPen(QColor(255, 255, 255), 1.5 / self.zoom, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            # 尺寸提示
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(rect.bottomRight() + QPointF(-70, -6),
                             f"{int(rect.width())} × {int(rect.height())}")
        painter.restore()
        # 取色工具的像素放大镜（窗口坐标，不随画布缩放）
        if self.tool == "pick" and self._hover_pos is not None:
            self._draw_pick_magnifier(painter)
        painter.end()

    # ---------- 取色放大镜 ----------
    PICK_CELL_N = 9     # 奇数格，正中心即取样像素
    PICK_CELL_PX = 22   # 每格屏幕像素

    def _draw_pick_magnifier(self, p: QPainter):
        n, cpx = self.PICK_CELL_N, self.PICK_CELL_PX
        size = n * cpx
        half = n // 2
        img = self.base_pixmap.toImage()
        src = self.to_image(self._hover_pos)
        cx, cy = int(src.x()), int(src.y())

        # 位置：光标右下，越界翻转，最后整体夹回画布内
        wx, wy = self._hover_pos.x() + 20, self._hover_pos.y() + 20
        if wx + size > self.width() - 4:
            wx = self._hover_pos.x() - size - 20
        if wy + size + 34 > self.height() - 4:
            wy = self._hover_pos.y() - size - 54
        wx = min(max(4.0, wx), max(4.0, self.width() - size - 4))
        wy = min(max(4.0, wy), max(4.0, self.height() - size - 34 - 4))
        wx, wy = int(wx), int(wy)

        # 逐像素填格（真实源像素，未经缩放混合）
        for j in range(n):
            for i in range(n):
                px, py = cx + i - half, cy + j - half
                if 0 <= px < img.width() and 0 <= py < img.height():
                    p.fillRect(wx + i * cpx, wy + j * cpx, cpx, cpx,
                               img.pixelColor(px, py))
                else:
                    p.fillRect(wx + i * cpx, wy + j * cpx, cpx, cpx,
                               QColor(40, 40, 40))
        # 网格 + 外框
        p.setPen(QPen(QColor(255, 255, 255, 36), 1))
        p.setBrush(Qt.NoBrush)
        for i in range(1, n):
            p.drawLine(wx + i * cpx, wy, wx + i * cpx, wy + size)
            p.drawLine(wx, wy + i * cpx, wx + size, wy + i * cpx)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.drawRect(wx, wy, size, size)
        # 红框标出实际取样的像素
        if 0 <= cx < img.width() and 0 <= cy < img.height():
            p.setPen(QPen(QColor(229, 57, 53), 2))
            p.drawRect(wx + half * cpx, wy + half * cpx, cpx, cpx)
            # 色值标签
            color = img.pixelColor(cx, cy)
            text = color.name().upper()
            metrics = p.fontMetrics()
            lw = metrics.horizontalAdvance(text) + 30
            lh = metrics.height() + 10
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 200))
            p.drawRoundedRect(wx, wy + size + 6, lw, lh, 4, 4)
            p.setBrush(color)
            p.drawRect(wx + 6, wy + size + 11, lh - 12, lh - 12)
            p.setPen(QColor(255, 255, 255))
            p.drawText(wx + lh, wy + size + 6 + metrics.ascent() + 5, text)


class EditorWindow(QMainWindow):
    """FSCapture 风格编辑器主窗口。"""

    pin_requested = Signal(QPixmap)
    capture_requested = Signal()   # 点顶栏"截图"按钮：去截下一张（会自动最小化编辑器）

    def __init__(self, pixmap: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PyShot 编辑器")
        self._prev_tool = "select"
        # 跨标签共享的绘制属性（切标签/新截图沿用当前工具与样式）
        self._shared = {"tool": "select", "color": QColor(PALETTE[0]),
                        "pen_width": 3, "font_size": 20, "step_diameter": 36}

        # 标签页：一次会话里的多张截图
        self.tabs = QTabWidget()
        self.tabs.setObjectName("canvasTabs")
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())       # 可换行的顶栏
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_toolbar())
        row.addWidget(self.tabs, 1)
        root.addLayout(row, 1)
        self.setCentralWidget(central)

        self._build_shortcuts()

        if pixmap is not None:
            self.add_canvas(pixmap)
            w = min(int(pixmap.width() * self.canvas.zoom) + 190,
                    int(QGuiApplication.primaryScreen().availableGeometry().width() * 0.92))
            h = min(int(pixmap.height() * self.canvas.zoom) + 120,
                    int(QGuiApplication.primaryScreen().availableGeometry().height() * 0.92))
            self.resize(max(w, 760), max(h, 500))
        self._refresh_actions()

    # ---------- 标签页 ----------
    @property
    def canvas(self) -> "Canvas | None":
        """当前标签的画布。"""
        page = self.tabs.currentWidget()
        return page.widget() if isinstance(page, QScrollArea) else None

    @property
    def scroll(self) -> "QScrollArea | None":
        page = self.tabs.currentWidget()
        return page if isinstance(page, QScrollArea) else None

    def add_canvas(self, pixmap: QPixmap, title: str | None = None) -> Canvas:
        """新增一个截图标签页并切换过去。"""
        canvas = Canvas(pixmap)
        canvas.tool = self._shared["tool"]
        canvas.color = QColor(self._shared["color"])
        canvas.pen_width = self._shared["pen_width"]
        canvas.font_size = self._shared["font_size"]
        canvas.step_diameter = self._shared["step_diameter"]
        canvas.setCursor(Qt.CrossCursor if canvas.tool != "select" else Qt.ArrowCursor)
        canvas.shapes_changed.connect(self._refresh_actions)
        canvas.color_picked.connect(self._on_color_picked)
        canvas.selection_changed.connect(self._on_selection_changed)
        canvas.escape_idle.connect(self.close)  # 空闲时 Esc 关闭编辑器
        canvas.zoom_changed.connect(lambda z, c=canvas: self._on_canvas_zoom(c, z))

        scroll = QScrollArea()
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignCenter)

        idx = self.tabs.addTab(scroll, title or f"截图 {self.tabs.count() + 1}")
        self.tabs.setTabToolTip(
            idx, f"{pixmap.width()} × {pixmap.height()} px\n"
                 "滚轮/Ctrl+滚轮 缩放 · 中键拖动滚动")
        # 自定义关闭按钮（自带图标在深色主题下几乎看不见）
        close_btn = QToolButton()
        close_btn.setObjectName("tabclose")
        close_btn.setText("✕")
        close_btn.setToolTip("关闭此标签 (Ctrl+W)")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(lambda _=False, page=scroll: self._close_page(page))
        self.tabs.tabBar().setTabButton(idx, QTabBar.RightSide, close_btn)

        self.tabs.setCurrentIndex(idx)
        self._fit_canvas(canvas, scroll)
        # 设为默认的水印：新截图自动加上（可 Ctrl+Z 撤销）
        defaults = load_default()
        if defaults.get("auto"):
            canvas.push_undo()
            canvas.shapes.append(WatermarkShape(defaults,
                                                canvas.base_pixmap.size()))
        return canvas

    def close_tab(self, idx: int):
        page = self.tabs.widget(idx)
        if page is not None:
            self._close_page(page)

    def _close_page(self, page):
        idx = self.tabs.indexOf(page)
        if idx < 0:
            return
        self.tabs.removeTab(idx)
        page.setParent(None)
        page.deleteLater()
        if self.tabs.count() == 0:
            self.close()          # 关掉最后一个标签 → 关闭编辑器
        else:
            self._on_tab_changed(self.tabs.currentIndex())

    def _on_tab_changed(self, idx: int):
        canvas = self.canvas
        if canvas is None:
            return
        # 新标签沿用当前工具/颜色/线宽/字号
        canvas.tool = self._shared["tool"]
        canvas.color = QColor(self._shared["color"])
        canvas.pen_width = self._shared["pen_width"]
        canvas.font_size = self._shared["font_size"]
        canvas.step_diameter = self._shared["step_diameter"]
        canvas.setCursor(Qt.CrossCursor if canvas.tool != "select" else Qt.ArrowCursor)
        self.zoom_label.setText(f"{round(canvas.zoom * 100)}%")
        self._refresh_swatch_state()
        self._refresh_actions()
        self._refresh_size_label()
        self._on_selection_changed(canvas._selected)

    def _on_canvas_zoom(self, canvas: Canvas, zoom: float):
        if canvas is self.canvas:
            self.zoom_label.setText(f"{round(zoom * 100)}%")
            self._refresh_size_label()

    def _refresh_size_label(self):
        canvas = self.canvas
        if canvas is None:
            return
        self.size_label.setText(
            f"{canvas.base_pixmap.width()} × {canvas.base_pixmap.height()} px")

    # ---------- 工具栏 ----------
    # 工具分组（用细线分隔），让工具轨道有清晰的层级
    _TOOL_GROUPS = [
        ["select"],
        ["rect", "ellipse", "line", "arrow", "pen"],
        ["step", "text", "highlight", "mosaic"],
        ["pick", "crop"],
    ]

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFrameShape(QFrame.NoFrame)      # 去掉默认立体边框
        v = QVBoxLayout(bar)
        v.setContentsMargins(6, 10, 6, 8)
        v.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        tips = {tid: (name, tip) for tid, name, tip in TOOLS}
        first_group = True
        for group in self._TOOL_GROUPS:
            if not first_group:
                sep = QFrame()
                sep.setObjectName("railsep")
                sep.setFrameShape(QFrame.HLine)
                v.addWidget(sep)
            first_group = False
            for tid in group:
                name, tip = tips[tid]
                btn = QToolButton()
                btn.setObjectName("toolbtn")
                btn.setIcon(make_tool_icon(tid))
                btn.setIconSize(QSize(24, 24))
                btn.setFixedSize(44, 42)
                btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
                btn.setToolTip(f"{name} — {tip}")
                btn.setCheckable(True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda checked, t=tid: self.set_tool(t))
                self.tool_group.addButton(btn)
                self.tool_buttons[tid] = btn
                v.addWidget(btn, 0, Qt.AlignHCenter)
        self.tool_buttons["select"].setChecked(True)
        v.addStretch(1)
        return bar

    def _action_button(self, action: QAction) -> QToolButton:
        """把一个 QAction 包成普通按钮（用于流式顶栏）。"""
        btn = QToolButton()
        btn.setObjectName("topbtn")
        btn.setDefaultAction(action)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    _CTRL_H = 30          # 顶栏控件统一高度（对齐的关键）

    def _group(self, *widgets) -> QWidget:
        """把若干控件打包成"原子组"：换行时整组一起走，不会被拆散。"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        for w in widgets:
            h.addWidget(w)
        return box

    def _labeled(self, text: str, widget: QWidget) -> QWidget:
        """标签 + 控件的原子组（垂直居中，换行时不会分开）。"""
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        return self._group(lab, widget)

    def _top_sep(self) -> QFrame:
        """顶栏分组之间的细竖分隔线（与控件等高居中）。"""
        sep = QFrame()
        sep.setObjectName("topsep")
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedSize(1, 20)
        return sep

    def _build_topbar(self):
        """顶栏：**两行有设计的分组**（不是随机换行）。

        第 1 行 = 截图 + 颜色 + 尺寸参数；第 2 行 = 编辑操作 + 输出操作。
        每行内部用流式布局，窗口过窄时该行内部才会继续折行；
        所有控件统一高度并垂直居中，保证水平基线对齐。
        """
        bar = QWidget()
        bar.setObjectName("topbar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)

        def row() -> FlowLayout:
            host = QWidget()
            fl = FlowLayout(host, margin=0, spacing=10)
            outer.addWidget(host)
            return fl

        # ---------- 第 1 行：截图 / 颜色 / 尺寸 ----------
        r1 = row()
        btn_shot = QPushButton("截图")
        btn_shot.setObjectName("primarybtn")
        btn_shot.setIcon(make_icon("camera"))
        btn_shot.setIconSize(QSize(17, 17))
        btn_shot.setFixedHeight(self._CTRL_H)
        btn_shot.setToolTip("截取新区域\n会自动最小化编辑器，截完回到这里新增标签")
        btn_shot.setCursor(Qt.PointingHandCursor)
        btn_shot.clicked.connect(self.capture_requested)
        self.btn_shot = btn_shot
        r1.addWidget(btn_shot)
        r1.addWidget(self._top_sep())

        color_label = QLabel("颜色")
        color_label.setAlignment(Qt.AlignVCenter)
        swatches = []
        self.color_buttons = []
        for hexs in PALETTE:
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"background:{hexs};")
            b.clicked.connect(lambda checked, c=hexs: self.set_color(QColor(c)))
            swatches.append(b)
            self.color_buttons.append(b)
        more = QPushButton("…")
        more.setObjectName("swatchMore")
        more.setFixedSize(20, 20)
        more.setToolTip("自定义颜色")
        more.clicked.connect(self._pick_color)
        r1.addWidget(self._group(color_label, *swatches, more))
        self._refresh_swatch_state()
        r1.addWidget(self._top_sep())

        self.width_spin = SpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(self._shared["pen_width"])
        self.width_spin.setFixedHeight(self._CTRL_H)
        self.width_spin.setFixedWidth(62)
        self.width_spin.valueChanged.connect(self._on_width_changed)
        r1.addWidget(self._labeled("线宽", self.width_spin))

        self.font_spin = SpinBox()
        self.font_spin.setRange(10, 96)
        self.font_spin.setValue(self._shared["font_size"])
        self.font_spin.setFixedHeight(self._CTRL_H)
        self.font_spin.setFixedWidth(62)
        self.font_spin.valueChanged.connect(self._on_font_changed)
        r1.addWidget(self._labeled("字号", self.font_spin))

        self.step_spin = SpinBox()
        self.step_spin.setRange(16, 240)
        self.step_spin.setSingleStep(2)
        self.step_spin.setSuffix(" px")
        self.step_spin.setValue(int(self._shared["step_diameter"]))
        self.step_spin.setFixedHeight(self._CTRL_H)
        self.step_spin.setFixedWidth(80)
        self.step_spin.setToolTip("序号圆的大小\n选中已有序号时可直接调整它的大小")
        self.step_spin.valueChanged.connect(self._on_step_size_changed)
        r1.addWidget(self._labeled("序号", self.step_spin))

        # ---------- 第 2 行：编辑 / 输出 ----------
        r2 = row()
        self.act_undo = QAction("撤销", self)
        self.act_undo.setToolTip("撤销 (Ctrl+Z)")
        self.act_undo.triggered.connect(lambda: self.canvas and self.canvas.undo())
        self.act_redo = QAction("重做", self)
        self.act_redo.setToolTip("重做 (Ctrl+Y)")
        self.act_redo.triggered.connect(lambda: self.canvas and self.canvas.redo())
        self.act_crop_ok = QAction("应用裁剪", self)
        self.act_crop_ok.setToolTip("应用裁剪框 (Enter)")
        self.act_crop_ok.triggered.connect(
            lambda: self.canvas and self.canvas.apply_crop())
        act_copy = QAction("复制", self)
        act_copy.setToolTip("复制到剪贴板 (Ctrl+C)")
        act_copy.triggered.connect(self.copy_to_clipboard)
        act_pin = QAction("贴图", self)
        act_pin.setToolTip("把当前结果钉在屏幕最上层（Snipaste 风格）")
        act_pin.triggered.connect(self.pin_to_screen)
        act_wm = QAction("水印", self)
        act_wm.setToolTip("给当前图片加水印（文字/图片、九宫格或平铺、可设为默认）")
        act_wm.triggered.connect(self.add_watermark)
        act_save = QAction("保存", self)
        act_save.setToolTip("保存为文件 (Ctrl+S)")
        act_save.triggered.connect(self.save_as)
        act_close = QAction("关闭", self)
        act_close.setToolTip("关闭编辑器 (Esc)")
        act_close.triggered.connect(self.close)

        undo_btn = self._icon_button("undo", "撤销 (Ctrl+Z)",
                                     lambda: self.canvas and self.canvas.undo())
        redo_btn = self._icon_button("redo", "重做 (Ctrl+Y)",
                                     lambda: self.canvas and self.canvas.redo())
        self.btn_undo, self.btn_redo = undo_btn, redo_btn
        r2.addWidget(self._group(undo_btn, redo_btn))
        r2.addWidget(self._action_button(self.act_crop_ok))
        r2.addWidget(self._top_sep())
        for act in (act_copy, act_pin, act_wm, act_save, act_close):
            r2.addWidget(self._action_button(act))

        self._build_statusbar_zoom()
        return bar

    def _icon_button(self, icon_name: str, tip: str, fn) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("topbtn")
        btn.setIcon(make_icon(icon_name))
        btn.setIconSize(QSize(18, 18))
        btn.setFixedSize(self._CTRL_H + 4, self._CTRL_H)
        btn.setToolTip(tip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(fn)
        return btn
        for act in (self.act_undo, self.act_redo, self.act_crop_ok,
                    act_copy, act_pin, act_wm, act_save, act_close):
            lay.addWidget(self._action_button(act))

        self._build_statusbar_zoom()
        return bar

    def _build_statusbar_zoom(self):
        """状态栏：左侧当前工具，右侧缩放胶囊。"""
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)      # 去掉右下角的多余手柄
        self.tool_name_label = QLabel()
        self.tool_name_label.setObjectName("toolname")
        self.tool_name_label.setText("工具：选择")
        sb.addWidget(self.tool_name_label)
        self.size_label = QLabel("")
        self.size_label.setObjectName("sizelabel")
        sb.addPermanentWidget(self.size_label)
        zoom_group = QWidget()
        zoom_group.setObjectName("zoomgroup")
        zoom_group.setAttribute(Qt.WA_StyledBackground, True)
        zlay = QHBoxLayout(zoom_group)
        zlay.setContentsMargins(6, 2, 6, 2)
        zlay.setSpacing(2)

        def _zbtn(text, tip, fn, width=28):
            b = QPushButton(text)
            b.setObjectName("zoombtn")
            b.setFixedSize(width, 24)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            return b

        zoom_out = _zbtn("−", "缩小 (Ctrl+滚轮)",
                         lambda: self.canvas and self.canvas.set_zoom(self.canvas.zoom / 1.2))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomlabel")
        self.zoom_label.setMinimumWidth(46)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        zoom_in = _zbtn("＋", "放大 (Ctrl+滚轮)",
                        lambda: self.canvas and self.canvas.set_zoom(self.canvas.zoom * 1.2))
        zlay.addWidget(zoom_out)
        zlay.addWidget(self.zoom_label)
        zlay.addWidget(zoom_in)
        sep = QFrame()
        sep.setObjectName("zoomsep")
        sep.setFrameShape(QFrame.VLine)
        zlay.addWidget(sep)
        zlay.addWidget(_zbtn("100%", "实际像素 (1:1)",
                             lambda: self.canvas and self.canvas.set_zoom(1.0), width=44))
        zlay.addWidget(_zbtn("适应", "缩放以适应窗口",
                             self._zoom_fit, width=44))
        sb.addPermanentWidget(zoom_group)

    def _build_shortcuts(self):
        for seq, fn in [
            ("Ctrl+Z", lambda: self.canvas and self.canvas.undo()),
            ("Ctrl+Y", lambda: self.canvas and self.canvas.redo()),
            ("Ctrl+Shift+Z", lambda: self.canvas and self.canvas.redo()),
            ("Ctrl+S", self.save_as),
            ("Ctrl+C", self.copy_to_clipboard),
            ("Ctrl+W", lambda: self.close_tab(self.tabs.currentIndex())),
            ("Ctrl+Tab", lambda: self.tabs.setCurrentIndex(
                (self.tabs.currentIndex() + 1) % max(1, self.tabs.count()))),
        ]:
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(fn)
            self.addAction(a)
        # 工具快捷键
        for key, tid in zip("VRELAPSTHMIC", [t[0] for t in TOOLS]):
            a = QAction(self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda checked, t=tid: self.set_tool(t))
            self.addAction(a)

    def set_hotkey_hint(self, hotkey: str):
        """把当前生效的全局热键告知编辑器（显示在截图按钮提示里）。"""
        if not hasattr(self, "btn_shot"):
            return
        suffix = f"（{hotkey}）" if hotkey else ""
        self.btn_shot.setToolTip(
            f"截取新区域{suffix}\n会自动最小化编辑器，截完回到这里新增标签")

    # ---------- 行为 ----------
    def set_tool(self, tid: str):
        canvas = self.canvas
        if canvas is not None:
            canvas._commit_text()
        if tid != "pick":
            self._prev_tool = tid
        self._shared["tool"] = tid
        # 应用到所有标签，切换标签时保持一致
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.tool = tid
                c.cancel_crop() if tid != "crop" else None
                c._selected = None
                c._hover_pos = None
                c.setCursor(Qt.CrossCursor if tid != "select" else Qt.ArrowCursor)
                c.update()
        self.tool_buttons[tid].setChecked(True)
        self._refresh_actions()
        name = dict((t, n) for t, n, _ in TOOLS).get(tid, tid)
        self.tool_name_label.setText(f"工具：{name}")

    def _on_color_picked(self, color: QColor):
        self._refresh_swatch_state()
        self.statusBar().showMessage(
            f"已取色 {color.name().upper()}，切回 {dict((t, n) for t, n, _ in TOOLS)[self._prev_tool]} 工具",
            3000)
        self.set_tool(self._prev_tool)  # 取色后自动切回之前的工具

    def set_color(self, color: QColor):
        self._shared["color"] = QColor(color)
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.color = QColor(color)
        self._refresh_swatch_state()

    def _on_width_changed(self, v: int):
        self._shared["pen_width"] = v
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.pen_width = v

    def _on_font_changed(self, v: int):
        self._shared["font_size"] = v
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.font_size = v

    def _on_step_size_changed(self, v: int):
        """序号大小：作用于新序号，同时也实时调整选中的序号。"""
        self._shared["step_diameter"] = v
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.step_diameter = v
        canvas = self.canvas
        if canvas is not None:
            canvas.resize_selected_step(v)

    def _on_selection_changed(self, shape):
        """选中序号时把它的实际大小同步到控件上（控件即所见：新序号也用这个值）。"""
        if not hasattr(self, "step_spin"):
            return
        if isinstance(shape, StepShape):
            d = int(round(shape.diameter))
            self.step_spin.blockSignals(True)
            self.step_spin.setValue(d)
            self.step_spin.blockSignals(False)
            self._shared["step_diameter"] = d
            for i in range(self.tabs.count()):
                c = self.tabs.widget(i).widget()
                if isinstance(c, Canvas):
                    c.step_diameter = d

    def _refresh_swatch_state(self):
        canvas = self.canvas
        cur = canvas.color.name() if canvas is not None else self._shared["color"].name()
        for b, hexs in zip(self.color_buttons, PALETTE):
            b.setProperty("selected", QColor(hexs).name() == cur)
            b.style().unpolish(b)
            b.style().polish(b)

    def _pick_color(self):
        current = self.canvas.color if self.canvas is not None else self._shared["color"]
        c = QColorDialog.getColor(current, self, "选择颜色")
        if c.isValid():
            self.set_color(c)

    def _fit_canvas(self, canvas: Canvas, scroll: QScrollArea):
        """让新标签的图片适配可视区（小图不放大超过 100%）。"""
        iw = max(1, canvas.base_pixmap.width() / canvas.dpr)
        ih = max(1, canvas.base_pixmap.height() / canvas.dpr)
        vw = scroll.viewport().width()
        vh = scroll.viewport().height()
        if vw > 80 and vh > 80:
            zx = (vw - 24) / iw
            zy = (vh - 24) / ih
        else:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            zx = (screen.width() * 0.85 - 190) / iw
            zy = (screen.height() * 0.85 - 120) / ih
        canvas.set_zoom(min(1.0, max(0.1, min(zx, zy))))

    def _zoom_fit(self):
        """缩放画布以适应当前窗口可视区。"""
        canvas, scroll = self.canvas, self.scroll
        if canvas is None or scroll is None:
            return
        iw = max(1, canvas.base_pixmap.width() / canvas.dpr)
        ih = max(1, canvas.base_pixmap.height() / canvas.dpr)
        zx = (scroll.viewport().width() - 24) / iw
        zy = (scroll.viewport().height() - 24) / ih
        canvas.set_zoom(min(4.0, max(0.1, min(zx, zy))))

    def _refresh_actions(self):
        canvas = self.canvas
        self.act_undo.setEnabled(bool(canvas and canvas._undo_stack))
        self.act_redo.setEnabled(bool(canvas and canvas._redo_stack))
        self.act_crop_ok.setEnabled(bool(canvas and canvas.tool == "crop"))

    def copy_to_clipboard(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas._commit_text()
        QApplication.clipboard().setPixmap(canvas.render_result())
        self.statusBar().showMessage("已复制到剪贴板", 2000)

    def pin_to_screen(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas._commit_text()
        self.pin_requested.emit(canvas.render_result())

    # ---------- 水印 ----------
    def add_watermark(self):
        """打开水印设置对话框，把水印加到当前标签（可撤销、可拖动）。"""
        canvas = self.canvas
        if canvas is None:
            return
        dlg = WatermarkDialog(self, load_default(), canvas.base_pixmap.size())
        if dlg.exec() != QDialog.Accepted:
            return
        settings = dlg.settings()
        if settings.get("auto"):
            saved = save_default(settings)
            msg = ("已设为默认水印，之后每次新截图会自动添加"
                   if saved else "已设为默认水印（本次运行有效，配置写入失败）")
            self.statusBar().showMessage(msg, 4000)
        self.apply_watermark(canvas, settings)

    def apply_watermark(self, canvas: Canvas, settings: dict):
        canvas.push_undo()
        canvas.shapes.append(WatermarkShape(settings, canvas.base_pixmap.size()))
        canvas.update()
        canvas.shapes_changed.emit()

    def save_as(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas._commit_text()
        idx = self.tabs.currentIndex() + 1
        default = f"screenshot-{idx}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存截图", default,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;BMP 图片 (*.bmp)")
        if not path:
            return
        img = canvas.render_result().toImage()
        if path.lower().endswith((".jpg", ".jpeg")):
            # JPEG 无透明通道，补白底；先归一化 dpr 以免按逻辑尺寸缩小
            img.setDevicePixelRatio(1.0)
            bg = QPixmap(img.size())
            bg.fill(QColor("white"))
            p = QPainter(bg)
            p.drawPixmap(0, 0, QPixmap.fromImage(img))
            p.end()
            bg.save(path, "JPG", 92)
        else:
            img.setDevicePixelRatio(1.0)   # PNG 存原始像素，不带 dpr 元数据
            img.save(path)
        self.statusBar().showMessage(f"已保存：{path}", 4000)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier and self.canvas is not None:
            delta = e.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.canvas.set_zoom(self.canvas.zoom * factor)
            e.accept()
            return
        super().wheelEvent(e)
