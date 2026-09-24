# -*- coding: utf-8 -*-
"""编辑器窗口：左侧工具栏 + 顶部属性栏 + 可缩放画布。"""
import math
from pathlib import Path

from PySide6.QtCore import (QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QGuiApplication, QIcon, QKeySequence,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QTransform)
from PySide6.QtWidgets import (QDialogButtonBox, QFontDialog, QGridLayout, QMenu, QStackedWidget, QApplication, QColorDialog, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QTabBar,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget,
                               QButtonGroup)

from shapes import (ArrowShape, EllipseShape, HighlightShape, LineShape,
                    MosaicShape, PenShape, RectShape, Shape, StepShape,
                    TextShape, WatermarkShape, clone_shapes)
from style import ACCENT, SpinBox, make_icon, make_tool_icon
from watermark import WatermarkDialog, load_default, save_default
from i18n import tr

# 「截图时不最小化编辑器」的设置键（主程序截图时读同一个键）
KEEP_EDITOR_SETTING = "capture_keep_editor"


def keep_editor_on_capture() -> bool:
    """当前是否要求"截图时不要最小化编辑器"（默认 False = 自动让位）。"""
    try:
        from i18n import get_setting
        return bool(get_setting(KEEP_EDITOR_SETTING, False))
    except Exception:                              # noqa: BLE001
        return False

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
    ("pan",       "抓手",   "拖拽移动画面（图放大后看不同位置）；任何工具下按住中键或空格也能拖"),
]

def basic_colors() -> list:
    """Windows 拾色器风格的「基本颜色」48 色（8 列 × 6 行）。

    前两行是经典 16 色，后面四行是它们的浅色/深色变体 —— 和系统对话框观感一致。
    """
    classic = ["#000000", "#800000", "#008000", "#808000",
               "#000080", "#800080", "#008080", "#c0c0c0",
               "#808080", "#ff0000", "#00ff00", "#ffff00",
               "#0000ff", "#ff00ff", "#00ffff", "#ffffff"]
    out = list(classic)
    for factor, lighter in ((160, True), (130, True), (180, False), (140, False)):
        for c in classic:
            col = QColor(c)
            out.append(col.lighter(factor).name() if lighter
                       else col.darker(factor).name())
    return out[:48]


CUSTOM_SLOTS = 16


def _custom_colors() -> list:
    """读「自定义颜色」格子（最多 16 个，空的用 None 占位）。"""
    try:
        from i18n import get_setting
        saved = get_setting("custom_colors", []) or []
    except Exception:                              # noqa: BLE001
        saved = []
    out = [c for c in saved if isinstance(c, str) and QColor(c).isValid()]
    return (out + [None] * CUSTOM_SLOTS)[:CUSTOM_SLOTS]


def _remember_custom(color: QColor):
    """把颜色记进「自定义颜色」格子（去重、最新的排前面）并持久化。"""
    name = QColor(color).name()
    items = [c for c in _custom_colors() if c]
    if name in items:
        items.remove(name)
    items.insert(0, name)
    try:
        from i18n import set_setting
        set_setting("custom_colors", items[:CUSTOM_SLOTS])
    except Exception:                              # noqa: BLE001
        pass


class ColorPaletteDialog(QDialog):
    """颜色（仿 Windows 拾色器）：基本颜色 + 自定义颜色，两段式。

    - 基本颜色：48 色 8×6 网格，点一下即选中
    - 自定义颜色：16 个格子，记住用过的颜色（存 settings.json，重启还在）；
      点空白格会打开系统拾色器来定义
    """

    def __init__(self, parent=None, current=None):
        super().__init__(parent)
        self.setWindowTitle(tr("颜色"))
        self._color = QColor(current) if current is not None else QColor("#e53935")
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ---- 基本颜色 ----
        root.addWidget(QLabel(tr("基本颜色")))
        basic = QGridLayout()
        basic.setSpacing(2)
        self.buttons = []
        for i, hexs in enumerate(basic_colors()):
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(24, 24)
            b.setStyleSheet(f"background:{hexs};")
            b.setToolTip(hexs)
            b.clicked.connect(lambda checked, c=hexs: self._choose(QColor(c)))
            basic.addWidget(b, i // 8, i % 8)
            self.buttons.append(b)
        root.addLayout(basic)

        # ---- 自定义颜色 ----
        root.addWidget(QLabel(tr("自定义颜色")))
        custom = QGridLayout()
        custom.setSpacing(2)
        self.custom_buttons = []
        for i, hexs in enumerate(_custom_colors()):
            b = QPushButton()
            b.setObjectName("swatch" if hexs else "swatchEmpty")
            b.setFixedSize(24, 24)
            if hexs:
                b.setStyleSheet(f"background:{hexs};")
                b.setToolTip(hexs)
                b.clicked.connect(lambda checked, c=hexs: self._choose(QColor(c)))
            else:
                # 空白格：虚线框，点了去系统拾色器定义
                b.setStyleSheet("background:transparent;"
                                "border:1px dashed #5a6070;")
                b.setToolTip(tr("点这里定义一个自定义颜色…"))
                b.clicked.connect(self._define_custom)
            custom.addWidget(b, i // 8, i % 8)
            self.custom_buttons.append(b)
        root.addLayout(custom)

        box = QHBoxLayout()
        box.addStretch(1)
        self.btn_custom = QPushButton(tr("自定义…"))
        self.btn_custom.setToolTip(tr("打开系统拾色器"))
        self.btn_custom.clicked.connect(self._custom)
        box.addWidget(self.btn_custom)
        btns = QDialogButtonBox(self)
        btns.addButton(tr("取消"), QDialogButtonBox.RejectRole).clicked.connect(
            self.reject)
        box.addWidget(btns)
        root.addLayout(box)

    # ---------- 交互 ----------
    def _choose(self, color: QColor):
        self._color = QColor(color)
        _remember_custom(self._color)              # 选过的颜色进自定义格
        self.accept()

    def _define_custom(self, *args):
        self._custom()

    def _custom(self):
        c = QColorDialog.getColor(self._color, self, tr("自定义颜色"))
        if c.isValid():
            self._choose(c)

    def selected(self) -> QColor:
        return QColor(self._color)


from version import APP_VERSION, VERSION_TITLE

# 色板：两行 20 色（红橙黄绿青蓝紫 + 灰阶），常用色一眼可选
PALETTE = ["#e53935", "#fb8c00", "#fdd835", "#43a047", "#00acc1",
           "#1e88e5", "#5e35b1", "#8e24aa", "#d81b60", "#6d4c41",
           "#ffffff", "#f5f5f5", "#bdbdbd", "#757575", "#424242",
           "#212121", "#000000", "#00e676", "#ff1744", "#ffea00"]

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
    float_changed = Signal()   # 浮动粘贴的开始/固定/取消（宿主据此刷新菜单）
    context_action = Signal(str)   # 右键菜单请求：front/up/down/back/dup/rot15/rot0

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.base_pixmap = QPixmap(pixmap)
        # 保留截图自带的 devicePixelRatio：图形坐标统一用"图像物理像素"，
        # 画布控件尺寸用"逻辑像素"（物理 / dpr），这样 100% 缩放时
        # 1 个图像像素恰好落在 1 个屏幕物理像素上，不会被系统放大而发虚。
        self.dpr = float(self.base_pixmap.devicePixelRatio() or 1.0)
        self.shapes: list = []
        # 拖动查看（平移画面）的状态
        self._panning = False
        self._space_pan = False          # 按住空格临时抓手
        self._pan_from = QPointF()
        self._pan_scroll = (0, 0)
        self._scroll_area = None
        self.setFocusPolicy(Qt.StrongFocus)     # 为了接空格键
        self.tool = "select"
        # 适应模式：窗口大小变化时自动重算缩放。
        # 用户一旦手动缩放（滚轮/按钮）就退出，免得打断他看细节。
        self.fit_mode = True
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

        # 浮动粘贴：把新截图贴到当前图上，先摆位置再固定（Enter 固定 / Esc 取消）
        self._float_pix: QPixmap | None = None
        self._float_rect_obj = QRectF()       # 权威尺寸：图像物理像素下的矩形
        self._float_aspect = 1.0              # 原始宽高比（Shift 等比时用）
        self._float_angle = 0.0               # 浮层旋转角（度，顺时针）
        self._float_from: QPointF | None = None    # 拖动时的抓取偏移
        self._float_handle: int | None = None      # 正在拖的句柄索引（8 = 旋转）
        # 粘贴图的外观（阴影/描边/圆角）——做指引时让贴上去的图"浮起来"
        self.float_style = {"shadow": False, "stroke": False, "radius": 0,
                            "stroke_color": "#ffffff", "stroke_width": 3}

        self._text_edit: QLineEdit | None = None
        self._text_pos = QPointF()
        self._text_target = None      # 正在改的已有文字（None = 新建）
        self.font_family = ""         # 文字字体（空 = 默认微软雅黑）

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

    def to_widget(self, image_pos) -> QPointF:
        """图像物理像素坐标 → 控件坐标（paintEvent 里变换的逆）。

        这两个函数必须严格互逆 —— 否则鼠标位置和图形落点会错开，
        系统缩放不是 100% 时表现为"画图不跟手"。
        """
        return QPointF(image_pos.x() * self.zoom / self.dpr,
                       image_pos.y() * self.zoom / self.dpr)

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
    # ---------- 拖动查看（放大后平移画面）----------
    def scroll_area(self):
        """找到承载自己的 QScrollArea（add_canvas 里会存一份引用）。"""
        area = getattr(self, "_scroll_area", None)
        if area is not None:
            return area
        w = self.parent()
        while w is not None:
            if isinstance(w, QScrollArea):
                return w
            w = w.parent()
        return None

    def _pan_begin(self, e):
        """开始拖动：记下按下位置与当时的滚动量。"""
        area = self.scroll_area()
        if area is None:
            return False
        self._panning = True
        self._pan_from = e.position()
        self._pan_scroll = (area.horizontalScrollBar().value(),
                            area.verticalScrollBar().value())
        self._pan_moved = False
        self.setCursor(Qt.ClosedHandCursor)
        return True

    def _pan_update(self, e) -> bool:
        """拖动中：把鼠标位移反向加到滚动条上。"""
        if not self._panning:
            return False
        area = self.scroll_area()
        if area is None:
            return False
        d = e.position() - self._pan_from
        if abs(d.x()) > 1 or abs(d.y()) > 1:
            self._pan_moved = True
        area.horizontalScrollBar().setValue(int(self._pan_scroll[0] - d.x()))
        area.verticalScrollBar().setValue(int(self._pan_scroll[1] - d.y()))
        return True

    def _pan_end(self):
        was = self._panning
        self._panning = False
        self.set_tool_cursor()
        return was

    def can_pan(self) -> bool:
        """当前是否处于"拖动能平移"的状态（抓手工具 / 按住空格）。"""
        return self.tool == "pan" or self._space_pan

    def set_tool_cursor(self):
        """按当前工具设置鼠标形状。"""
        if self.tool == "pan" or self._space_pan:
            self.setCursor(Qt.ClosedHandCursor if self._panning
                           else Qt.OpenHandCursor)
        elif self.tool == "select":
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space_pan = False
            if not self._panning:
                self.set_tool_cursor()
            e.accept()
            return
        super().keyReleaseEvent(e)

    def mousePressEvent(self, e):
        self._commit_text()
        # 中键：任何工具下都能拖动画面（以前这里直接 return，中键其实没用）
        if e.button() == Qt.MiddleButton:
            self._pan_begin(e)
            e.accept()
            return
        if e.button() != Qt.LeftButton:
            return
        # 抓手工具 / 按住空格：左键拖动 = 平移画面
        if self.can_pan():
            self._pan_begin(e)
            e.accept()
            return
        pos = self.clamp(self.to_image(e.position()))
        self._drag_start = pos
        self._dragging = True

        # 浮动粘贴：任何工具下都能拖/缩/转它（临时摆放状态，优先于画笔工具）
        if self._float_pix is not None:
            hit = max(8.0, (HANDLE_HIT + 2) / max(0.2, self.zoom))
            for i, hp in enumerate(self.float_handles()):
                if (abs(hp.x() - pos.x()) <= hit and abs(hp.y() - pos.y()) <= hit):
                    self._float_handle = i        # 0~7 缩放，8 = 旋转
                    self._float_from = None
                    self._dragging = False
                    e.accept()
                    return
            if self.float_rect().contains(self.float_local(pos)):
                self._float_from = self.float_local(pos) - self._float_rect_obj.topLeft()
                self._dragging = False
                e.accept()
                return

        if self.tool == "select":
            self._resizing = None
            # 先看是否点在缩放/旋转句柄上（优先于选中/移动）
            if self._selected is not None:
                hit = int(HANDLE_HIT / self.zoom) + 2
                for i, hp in enumerate(self._selected.rotated_handles()):
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
                # 命中判定要在图形**自身坐标**里做（旋转过的图形点不准会很难选）
                if shape.contains(shape.world_to_local(pos), 6 / self.zoom):
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
        if self._pan_update(e):                 # 拖动查看优先
            return
        self._hover_pos = e.position()
        if self.tool == "pick":
            self.update()  # 刷新取色放大镜
        pos = self.clamp(self.to_image(e.position()))
        # 拖动/缩放/旋转中的浮动粘贴
        if self._float_pix is not None and self._float_handle is not None:
            if self._float_handle == 8:
                self.rotate_float_to(pos)
            elif self._float_angle:
                # 转过之后：角手柄绕中心等比缩放，边的靠自身坐标处理
                c = self._float_rect_obj.center()
                if self._float_handle in (0, 2, 4, 6):
                    d0 = math.hypot(self._float_rect_obj.width(),
                                    self._float_rect_obj.height()) / 2.0
                    d1 = math.hypot(pos.x() - c.x(), pos.y() - c.y())
                    if d0 > 0.5 and d1 > 0.5:
                        self.scale_float(d1 / d0)
                else:
                    self.resize_float_by_handle(self._float_handle,
                                                self.float_local(pos),
                                                bool(e.modifiers() & Qt.ShiftModifier))
            else:
                self.resize_float_by_handle(self._float_handle, pos,
                                            bool(e.modifiers() & Qt.ShiftModifier))
            self.update()
            return
        if self._float_pix is not None and self._float_from is not None:
            top_left = self.float_local(pos) - self._float_from
            self._float_rect_obj = QRectF(top_left, self._float_rect_obj.size())
            self.update()
            return
        # 悬停在浮动图上时给"可拖动"的光标
        if self._float_pix is not None:
            over = self.float_rect().contains(self.float_local(pos))
            self.setCursor(Qt.SizeAllCursor if over else Qt.ArrowCursor)
            if over:
                return
        if self.tool == "select" and self._resizing is not None:
            shape, index = self._resizing
            shape.apply_rotation_and_resize(
                index, pos, bool(e.modifiers() & Qt.ShiftModifier))
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
        if self._float_from is not None or self._float_handle is not None:
            self._float_from = None            # 松开：浮动图就停在当前位置/大小
            self._float_handle = None
            e.accept()
            return
        if self._panning and (e.button() in (Qt.MiddleButton, Qt.LeftButton)):
            self._pan_end()
            e.accept()
            return
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
        if self._float_pix is not None:        # 双击 = 固定（和 Enter 等价）
            self.commit_float()
            return
        if self.tool == "crop":
            self.apply_crop()
            return
        # 双击已有文字 = 改文字（以前只能删掉重写）
        pos = self.to_image(e.position())
        for shape in reversed(self.shapes):
            if isinstance(shape, TextShape) and shape.contains(
                    shape.world_to_local(pos), 6 / self.zoom):
                self._selected = shape
                self.selection_changed.emit(shape)
                self._open_text_editor(shape.pos, target=shape)
                self.update()
                return

    def contextMenuEvent(self, e):
        """右键菜单：图层顺序 / 再制 / 旋转 / 删除 / 粘贴相关。

        以前画布右键没反应，只能去编辑菜单里找；做指引时这些操作很常用。
        """
        menu = QMenu(self)
        has_sel = self._selected is not None and self._selected in self.shapes
        if self._float_pix is not None:
            menu.addAction(tr("固定粘贴的图"), self.commit_float)
            menu.addAction(tr("取消粘贴"), self.cancel_float)
            menu.addSeparator()
        if has_sel:
            menu.addAction(tr("置于顶层"),
                           lambda: self._emit_ctx("front"))
            menu.addAction(tr("上移一层"), lambda: self._emit_ctx("up"))
            menu.addAction(tr("下移一层"), lambda: self._emit_ctx("down"))
            menu.addAction(tr("置于底层"), lambda: self._emit_ctx("back"))
            menu.addSeparator()
            menu.addAction(tr("再制一个"), lambda: self._emit_ctx("dup"))
            if isinstance(self._selected, TextShape):
                menu.addAction(tr("修改文字…"),
                               lambda: self._emit_ctx("edit_text"))
            menu.addAction(tr("旋转 15°"), lambda: self._emit_ctx("rot15"))
            menu.addAction(tr("摆正（0°）"), lambda: self._emit_ctx("rot0"))
            menu.addSeparator()
            menu.addAction(tr("删除"), lambda: self._emit_ctx("del"))
        if menu.isEmpty():
            menu.addAction(tr("撤销"), self.undo)
            menu.addAction(tr("重做"), self.redo)
        menu.exec(e.globalPos())

    def _emit_ctx(self, what: str):
        """画布右键菜单 → 交给宿主执行（宿主管撤销栈与状态栏提示）。"""
        if what == "del" and self._selected is not None:
            self.push_undo()
            self.shapes.remove(self._selected)
            self._selected = None
            self.selection_changed.emit(None)
            self.update()
            self.shapes_changed.emit()
            return
        self.context_action.emit(what)

    def keyPressEvent(self, e):
        # 方向键微调：选中的图形 1px，按 Shift 10px（画指引时对齐很有用）
        step = 10.0 if (e.modifiers() & Qt.ShiftModifier) else 1.0
        deltas = {Qt.Key_Left: (-step, 0.0), Qt.Key_Right: (step, 0.0),
                  Qt.Key_Up: (0.0, -step), Qt.Key_Down: (0.0, step)}
        if e.key() in deltas:
            if self._float_pix is not None:
                dx, dy = deltas[e.key()]
                self._float_rect_obj.translate(dx, dy)
                self.update()
                e.accept()
                return
            if self._selected is not None and self._selected in self.shapes:
                dx, dy = deltas[e.key()]
                self.push_undo()               # 每次微调都能撤销
                self._selected.move_by(dx, dy)
                self.update()
                self.shapes_changed.emit()
                e.accept()
                return
        # 浮动粘贴：Enter 固定 / Esc 取消（要排在其它 Esc 处理之前，
        # 否则会直接把编辑器关掉）
        if self._float_pix is not None:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.commit_float()
                e.accept()
                return
            if e.key() == Qt.Key_Escape:
                self.cancel_float()
                e.accept()
                return
        # 按住空格 = 临时抓手（和 Photoshop 一致，松开恢复原工具）
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space_pan = True
            self.set_tool_cursor()
            e.accept()
            return
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
    def _open_text_editor(self, pos: QPointF, target=None):
        """打开行内文字输入。target 是已有的 TextShape 时表示**改文字**。"""
        self._text_pos = pos
        self._text_target = target
        edit = QLineEdit(self)
        edit.setPlaceholderText(tr("输入文字，Enter 确认 / Esc 取消"))
        font = edit.font()
        size = int(getattr(target, "font_size", self.font_size) or self.font_size)
        font.setPixelSize(max(12, int(size * self.zoom)))
        fam = getattr(target, "family", "") or getattr(self, "font_family", "")
        if fam:
            font.setFamily(fam)
        edit.setFont(font)
        edit.setStyleSheet(f"color: {self.color.name()}; background: rgba(255,255,255,220);"
                           "border: 1px dashed #888;")
        edit.move(int(pos.x() * self.zoom), int(pos.y() * self.zoom))
        edit.resize(max(240, int(size * self.zoom * 12)), edit.sizeHint().height() + 6)
        if target is not None:                 # 改已有的：填上原文并全选，直接就能改
            edit.setText(str(target.text))
            edit.selectAll()
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
        target = getattr(self, "_text_target", None)
        self._text_edit = None
        self._text_target = None
        text = edit.text().strip()
        edit.deleteLater()
        if target is not None:                 # 改已有文字
            if not text:
                self.push_undo()
                if target in self.shapes:
                    self.shapes.remove(target)
                    if self._selected is target:
                        self._selected = None
                        self.selection_changed.emit(None)
                self.update()
                self.shapes_changed.emit()
                return
            if text != target.text:
                self.push_undo()
                target.text = text
                self.update()
                self.shapes_changed.emit()
            return
        if text:
            self.push_undo()
            self.shapes.append(TextShape(self.color, self.pen_width, self._text_pos,
                                         text, self.font_size,
                                         getattr(self, "font_family", "")))
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

    # ---------- 加边框（FSCapture 的「特效 → 边缘」）----------
    def apply_border(self, settings: dict, push_undo: bool = True) -> bool:
        """在图片四周加边框：底图变大，已有标注整体平移。

        和水印不同，边框是在**图片外面**加一圈（输出图更大），所以改的是
        base_pixmap；走撤销栈，加错了 Ctrl+Z 就能回去。
        """
        from border import border_padding, render_border
        left, top, _right, _bottom = border_padding(settings)
        if left + top == 0:
            return False
        if push_undo:
            self.push_undo()
        self.base_pixmap = render_border(self.base_pixmap, settings)
        self.base_pixmap.setDevicePixelRatio(self.dpr)
        for shape in self.shapes:
            shape.translate(left, top)
        self._crop_rect = None
        self._selected = None
        self._apply_size()
        self.update()
        self.shapes_changed.emit()
        return True

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
        # 任何"显式指定缩放"都算脱离适应模式（适应操作自己会再置回 True）
        self.fit_mode = False
        self.zoom = min(4.0, max(0.1, zoom))
        self._apply_size()
        self.update()
        self.zoom_changed.emit(self.zoom)

    # ---------- 浮动粘贴（把新截图贴到当前图上编辑） ----------
    def has_float(self) -> bool:
        return self._float_pix is not None

    def float_rect(self) -> QRectF:
        """浮动图在"图像物理像素"坐标下的矩形。"""
        return QRectF(self._float_rect_obj)

    def float_scale(self) -> float:
        """当前缩放倍数（1.0 = 原始像素大小），按宽度算。"""
        if self._float_pix is None or self._float_pix.width() <= 0:
            return 1.0
        return self._float_rect_obj.width() / self._float_pix.width()

    def float_handles(self) -> list:
        """浮动图的 8 个缩放手柄 + 1 个旋转手柄（最后一个是旋转）。

        顺序与 Shape.handles() 一致：0左上 1上中 2右上 3右中 4右下 5下中
        6左下 7左中；第 8 个是顶边外侧的旋转手柄。**都跟着旋转角走**。
        """
        if self._float_pix is None:
            return []
        r = self._float_rect_obj
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        cx = (x0 + x1) / 2.0
        local = [QPointF(x0, y0), QPointF(cx, y0), QPointF(x1, y0),
                 QPointF(x1, (y0 + y1) / 2.0), QPointF(x1, y1),
                 QPointF(cx, y1), QPointF(x0, y1), QPointF(x0, (y0 + y1) / 2.0)]
        c = r.center()
        rad = math.radians(self._float_angle)
        pts = []
        for p in local:
            if not self._float_angle:
                pts.append(QPointF(p))
                continue
            dx, dy = p.x() - c.x(), p.y() - c.y()
            pts.append(QPointF(c.x() + dx * math.cos(rad) - dy * math.sin(rad),
                               c.y() + dx * math.sin(rad) + dy * math.cos(rad)))
        # 旋转手柄：从"旋转后的上边中点"再往外一点
        top_mid = QPointF((pts[0].x() + pts[2].x()) / 2.0,
                          (pts[0].y() + pts[2].y()) / 2.0)
        dist = max(18.0, r.height() * 0.12)
        pts.append(QPointF(top_mid.x() + math.sin(rad) * dist,
                           top_mid.y() - math.cos(rad) * dist))
        return pts

    def float_corners(self) -> list:
        """浮层旋转后的四角（左上、右上、右下、左下）——虚线框按它画。"""
        r = self._float_rect_obj
        pts = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
        if not self._float_angle:
            return [QPointF(p) for p in pts]
        c = r.center()
        rad = math.radians(self._float_angle)
        out = []
        for p in pts:
            dx, dy = p.x() - c.x(), p.y() - c.y()
            out.append(QPointF(c.x() + dx * math.cos(rad) - dy * math.sin(rad),
                               c.y() + dx * math.sin(rad) + dy * math.cos(rad)))
        return out

    def float_local(self, pos: QPointF) -> QPointF:
        """世界坐标 → 浮层自身坐标（把点按旋转角反向转回来）。"""
        if not self._float_angle:
            return QPointF(pos)
        c = self._float_rect_obj.center()
        rad = math.radians(-self._float_angle)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        return QPointF(c.x() + dx * math.cos(rad) - dy * math.sin(rad),
                       c.y() + dx * math.sin(rad) + dy * math.cos(rad))

    def rotate_float_to(self, pos: QPointF) -> bool:
        """把旋转手柄拖到 pos：让浮层的"上边"朝向这个方向。"""
        if self._float_pix is None:
            return False
        c = self._float_rect_obj.center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return False
        self._float_angle = math.degrees(math.atan2(dx, -dy)) % 360.0
        self.update()
        return True

    def _float_anchor(self) -> QRectF:
        """浮动图的默认落点：**当前看得见**的那块区域的中心。

        不能直接用整图中心：滚动长截图动辄几千像素高，图心多半在屏幕外，
        贴上去等于看不见。滚动区拿不到（未嵌入时）就退回图心。
        """
        pix = self._float_pix
        w = float(pix.width())
        h = float(pix.height())
        # 比底图还大就先缩到能看全（否则一贴上去半个图在画布外，很难摆）
        bw, bh = self.base_pixmap.width(), self.base_pixmap.height()
        if w > bw * 0.9 or h > bh * 0.9:
            k = min(bw * 0.6 / max(1.0, w), bh * 0.6 / max(1.0, h))
            w, h = w * k, h * k
        cx = bw / 2.0
        cy = bh / 2.0
        area = self._scroll_area
        try:
            if area is not None:
                vp = area.viewport()
                center_in_canvas = self.mapFrom(vp, vp.rect().center())
                center_img = self.to_image(QPointF(center_in_canvas))
                cx, cy = center_img.x(), center_img.y()
        except Exception:                          # noqa: BLE001
            pass
        x = min(max(cx - w / 2.0, 0.0), max(0.0, bw - w))
        y = min(max(cy - h / 2.0, 0.0), max(0.0, bh - h))
        return QRectF(x, y, w, h)

    def start_float(self, pixmap: QPixmap) -> bool:
        """把一张图变成"可拖动的浮动层"，等用户摆好位置再固定。

        贴上去先不动底图（所以不占撤销栈），Enter/双击才合成进底图。
        """
        if pixmap is None or pixmap.isNull() or self.base_pixmap is None:
            return False
        pix = QPixmap(pixmap)
        pix.setDevicePixelRatio(1.0)      # 统一按图像物理像素处理
        self._float_pix = pix
        self._float_aspect = (pix.width() / pix.height()) if pix.height() else 1.0
        self._float_rect_obj = self._float_anchor()
        self._float_angle = 0.0
        self._float_from = None
        self._float_handle = None
        self.setFocus(Qt.OtherFocusReason)   # 让 Enter/Esc 能直接生效
        self.float_changed.emit()
        self.update()
        return True

    def commit_float(self) -> bool:
        """把浮动图合成到底图上（可撤销）。"""
        if self._float_pix is None:
            return False
        self.push_undo()                     # 底图要变了，先记一次
        p = QPainter(self.base_pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._draw_float(p)                  # 和预览用同一套画法，保证一致
        p.end()
        self._float_pix = None
        self._float_from = None
        self._float_handle = None
        self._apply_size()
        self.shapes_changed.emit()           # 宿主据此刷新按钮/会话缓存
        self.float_changed.emit()
        self.set_tool_cursor()
        self.update()
        return True

    # ---------- 画布变换：翻转 / 旋转 90° / 改尺寸 ----------
    # 标注图形跟着一起变换（不是"烧进图里"），所以变换完还能继续编辑。
    def _apply_canvas_transform(self, t: QTransform, new_size=None):
        """把仿射变换同时作用到底图和所有标注上。"""
        self.push_undo()
        old = self.base_pixmap
        if new_size is None:
            new_size = old.size()
        out = old.transformed(t, Qt.SmoothTransformation)
        if out.size() != new_size:                 # 兜底：尺寸必须和目标一致
            out = out.scaled(new_size, Qt.IgnoreAspectRatio,
                             Qt.SmoothTransformation)
        out.setDevicePixelRatio(self.dpr)
        self.base_pixmap = out
        for shape in self.shapes:
            try:
                shape.transform(t)
            except Exception:                      # noqa: BLE001
                pass
        self._apply_size()
        self._selected = None
        self._crop_rect = None
        self.shapes_changed.emit()
        self.update()

    def flip_horizontal(self):
        """水平翻转（左右镜像），标注跟着翻。"""
        t = QTransform().translate(self.base_pixmap.width(), 0).scale(-1, 1)
        self._apply_canvas_transform(t)

    def flip_vertical(self):
        """垂直翻转（上下镜像），标注跟着翻。"""
        t = QTransform().translate(0, self.base_pixmap.height()).scale(1, -1)
        self._apply_canvas_transform(t)

    def rotate90(self, clockwise: bool = True):
        """顺时针/逆时针转 90°（宽高对调），标注跟着转。"""
        w, h = self.base_pixmap.width(), self.base_pixmap.height()
        if clockwise:
            t = QTransform().translate(h, 0).rotate(90)
            size = QSize(h, w)
        else:
            t = QTransform().translate(0, w).rotate(-90)
            size = QSize(h, w)
        self._apply_canvas_transform(t, new_size=size)

    def scale_canvas(self, width: int, height: int):
        """把整张图（含标注）缩放到指定像素尺寸。"""
        w, h = self.base_pixmap.width(), self.base_pixmap.height()
        if width < 8 or height < 8 or w < 1 or h < 1:
            return
        t = QTransform().scale(width / float(w), height / float(h))
        self._apply_canvas_transform(t, new_size=QSize(int(width), int(height)))

    def set_float_style(self, **kw) -> None:
        """调粘贴图外观（shadow / stroke / radius / stroke_color）。"""
        self.float_style.update({k: v for k, v in kw.items()
                                 if k in self.float_style})
        self.update()

    def _float_path(self) -> QPainterPath:
        """粘贴图的轮廓（圆角矩形或直角矩形）：阴影/裁剪/描边都用它。"""
        path = QPainterPath()
        r = float(self.float_style.get("radius") or 0)
        rect = self.float_rect()
        if r > 0:
            r = min(r, rect.width() / 2.0, rect.height() / 2.0)
            path.addRoundedRect(rect, r, r)
        else:
            path.addRect(rect)
        return path

    def _draw_float(self, painter: QPainter) -> None:
        """把浮动图画到给定 painter（预览与合成共用，避免两处画法不一致）。"""
        if self._float_pix is None:
            return
        rect = self.float_rect()
        style = self.float_style
        painter.save()
        if self._float_angle:                  # 绕中心旋转后再画
            c = rect.center()
            painter.translate(c)
            painter.rotate(self._float_angle)
            painter.translate(-c)
        path = self._float_path()
        if style.get("shadow"):
            # 便宜的"软阴影"：几层逐渐变淡的偏移轮廓（做指引够用，不引入模糊库）
            for off, alpha in ((7, 46), (5, 62), (3, 86)):
                painter.save()
                painter.translate(off, off)
                painter.fillPath(path, QColor(0, 0, 0, alpha))
                painter.restore()
        painter.save()
        painter.setClipPath(path)
        painter.drawPixmap(rect, self._float_pix, QRectF(self._float_pix.rect()))
        painter.restore()
        if style.get("stroke"):
            painter.setPen(QPen(QColor(style.get("stroke_color", "#ffffff")),
                                max(1, int(style.get("stroke_width", 3)))))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        painter.restore()

    def cancel_float(self) -> bool:
        """丢掉浮动图，底图不动。"""
        if self._float_pix is None:
            return False
        self._float_pix = None
        self._float_from = None
        self._float_handle = None
        self.float_changed.emit()
        self.set_tool_cursor()
        self.update()
        return True

    def scale_float(self, factor: float) -> bool:
        """以中心为锚点等比缩放浮动图（0.05×~12×）。"""
        if self._float_pix is None:
            return False
        r = self._float_rect_obj
        new_w = r.width() * factor
        max_w = self._float_pix.width() * 12.0
        min_w = max(8.0, self._float_pix.width() * 0.05)
        new_w = min(max_w, max(min_w, new_w))
        k = new_w / max(1.0, r.width())
        if abs(k - 1.0) < 1e-6:
            return False
        c = r.center()
        self._float_rect_obj = QRectF(c.x() - r.width() * k / 2.0,
                                      c.y() - r.height() * k / 2.0,
                                      r.width() * k, r.height() * k)
        self.update()
        return True

    def resize_float_by_handle(self, index: int, pos: QPointF,
                               keep_aspect: bool = False) -> bool:
        """拖动某个手柄改浮动图大小（0~7 为边角，Shift 保持宽高比）。"""
        if self._float_pix is None or not 0 <= index <= 7:
            return False
        r = QRectF(self._float_rect_obj)
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        if index in (0, 1, 2):
            y0 = pos.y()
        elif index in (4, 5, 6):
            y1 = pos.y()
        if index in (0, 6, 7):
            x0 = pos.x()
        elif index in (2, 3, 4):
            x1 = pos.x()
        # 角上的手柄按 Shift 保持原比例：以"被拖的角"为基准反推另一边
        if keep_aspect and index in (0, 2, 4, 6):
            w = abs(x1 - x0)
            h = abs(y1 - y0)
            if self._float_aspect > 0:
                if w / max(1e-6, h) > self._float_aspect:
                    h = w / self._float_aspect
                else:
                    w = h * self._float_aspect
            if index in (0, 6):
                x0 = x1 - w if index == 0 else x0
            if index in (0, 2):
                y0 = y1 - h if index == 0 else y0
            if index == 0:
                x0, y0 = x1 - w, y1 - h
            elif index == 2:
                x1, y0 = x0 + w, y1 - h
            elif index == 4:
                x1, y1 = x0 + w, y0 + h
            elif index == 6:
                x0, y1 = x1 - w, y0 + h
        new = QRectF(QPointF(min(x0, x1), min(y0, y1)),
                     QPointF(max(x0, x1), max(y0, y1))).normalized()
        # 太小就贴个下限，免得被拖成一条线再也抓不住
        if new.width() < 8 or new.height() < 8:
            return False
        self._float_rect_obj = new
        self.update()
        return True

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
            self._draw_shape(p, shape)
        # 还没固定的浮动粘贴也算进导出结果（"看到什么就存什么"）
        if self._float_pix is not None:
            p.setRenderHint(QPainter.SmoothPixmapTransform,
                            self.float_scale() < 1.0)
            self._draw_float(p)
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.end()
        out.setDevicePixelRatio(self.dpr)   # 带上 dpr，显示按逻辑尺寸、像素不丢
        return out

    # ---------- 绘制 ----------
    def _draw_shape(self, painter: QPainter, shape):
        """按图形自身的旋转角绘制（绕外接矩形中心转）。

        旋转放在这里统一处理，各个 Shape.draw() 就不用管旋转了 ——
        否则矩形/椭圆/箭头/画笔/文字每一种都要自己算一遍。
        """
        rot = float(getattr(shape, "rotation", 0.0) or 0.0)
        if not rot:
            shape.draw(painter, self)
            return
        c = shape.bounding_rect().center()
        painter.save()
        painter.translate(c)
        painter.rotate(rot)
        painter.translate(-c)
        shape.draw(painter, self)
        painter.restore()

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
        # ---- 图形用图像物理像素坐标，而底图是 dpr 感知绘制的
        #      （QPixmap 带 devicePixelRatio 时 Qt 按逻辑尺寸画，即 P/dpr）。
        #      所以图形这里要再缩 1/dpr 才能与底图对齐；否则 dpr≠1（系统缩放
        #      非 100%）时图形会偏 dpr 倍，表现为画图不跟手。
        #      画笔宽度写成 /zoom 表示屏幕像素，在这个坐标系里恰好等于
        #      设备像素，所以无需改动。
        painter.save()
        painter.scale(1.0 / self.dpr, 1.0 / self.dpr)
        for shape in self.shapes:
            self._draw_shape(painter, shape)
        if self._current is not None:
            self._draw_shape(painter, self._current)
        # 浮动粘贴：虚线框 + 8 个缩放手柄 + 1 个旋转手柄（表示"还能拖/缩/转"）
        if self._float_pix is not None:
            self._draw_float(painter)
            # 虚线框必须用**旋转后的四角**画，否则转过之后框还是正的（用户报过）
            pen = QPen(QColor(ACCENT), 1.6 / self.zoom)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(self.float_corners()))
            hs = HANDLE_SIZE / self.zoom
            handles = self.float_handles()
            painter.setPen(QPen(QColor(ACCENT), 1.2 / self.zoom))
            painter.setBrush(QColor("#ffffff"))
            for hp in handles[:8]:
                painter.drawRect(QRectF(hp.x() - hs / 2, hp.y() - hs / 2, hs, hs))
            if len(handles) > 8:               # 旋转手柄：画个圆点 + 连接线
                rp = handles[8]
                corners = self.float_corners()
                top_mid = QPointF((corners[0].x() + corners[1].x()) / 2.0,
                                  (corners[0].y() + corners[1].y()) / 2.0)
                painter.setPen(QPen(QColor(ACCENT), 1.2 / self.zoom))
                painter.drawLine(top_mid, rp)
                painter.setBrush(QColor(ACCENT))
                painter.drawEllipse(rp, hs * 0.6, hs * 0.6)
        # 选中框 + 缩放句柄（细实线 + 白色句柄，现代编辑器风格）
        if self._selected is not None and self.tool == "select":
            hs = HANDLE_SIZE / self.zoom
            corners = self._selected.rotated_corners()
            painter.setPen(QPen(QColor(ACCENT), 1.4 / self.zoom))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(QPolygonF(corners))      # 跟着旋转的选中框
            handles = self._selected.rotated_handles()
            painter.setPen(QPen(QColor(ACCENT), 1.2 / self.zoom))
            painter.setBrush(QColor("#ffffff"))
            for hp in handles[:8]:
                painter.drawRect(QRectF(hp.x() - hs / 2, hp.y() - hs / 2, hs, hs))
            if len(handles) > 8:                         # 旋转手柄
                top_mid = QPointF((corners[0].x() + corners[1].x()) / 2.0,
                                  (corners[0].y() + corners[1].y()) / 2.0)
                painter.setPen(QPen(QColor(ACCENT), 1.2 / self.zoom))
                painter.drawLine(top_mid, handles[8])
                painter.setBrush(QColor(ACCENT))
                painter.drawEllipse(handles[8], hs * 0.6, hs * 0.6)
        painter.restore()
        # 裁剪遮罩
        if self.tool == "crop" and self._crop_rect is not None:
            painter.save()
            painter.scale(1.0 / self.dpr, 1.0 / self.dpr)
            rect = self._crop_rect.normalized()
            full = QRectF(self.base_pixmap.rect())
            path = QPainterPath()
            path.addRect(full)
            path.addRect(rect)
            painter.fillPath(path, QColor(0, 0, 0, 130))
            painter.setPen(QPen(QColor(255, 255, 255), 1.5 / self.zoom, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            painter.restore()
            # 尺寸提示：画在屏幕坐标里，字号不随缩放变形
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(
                self.to_widget(rect.bottomRight()) + QPointF(-70, -6),
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
    session_dirty = Signal()      # 内容变了，提示主程序缓存会话
    closing = Signal()            # 窗口要关了：趁标签还在赶紧存一次
    tabs_closed = Signal()        # 用户主动关掉了标签（缓存可以相应减少）
    capture_requested = Signal()   # 点顶栏"截图"按钮：去截下一张（会自动最小化编辑器）

    def __init__(self, pixmap: QPixmap | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("PyShot 编辑器"))
        self._prev_tool = "select"
        # 跨标签共享的绘制属性（切标签/新截图沿用当前工具与样式）
        self._shared = {"tool": "select", "color": QColor(PALETTE[0]),
                        "pen_width": 3, "font_size": 20, "step_diameter": 36,
                        "float_style": {"shadow": False, "stroke": False,
                                        "radius": 0, "stroke_color": "#ffffff",
                                        "stroke_width": 3}}

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
        # 空状态：没有标签页时显示提示页，而不是一片空白
        self.empty_page = self._build_empty_page()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.tabs)
        row.addWidget(self.stack, 1)
        root.addLayout(row, 1)
        self.setCentralWidget(central)

        self._build_menubar()
        self._build_shortcuts()
        self._update_empty_state()

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

    # ---------- 空状态 ----------
    def _build_empty_page(self) -> QWidget:
        """没有图片时的提示页（编辑器可以直接打开，不必先选文件）。"""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        title = QLabel(tr("还没有图片"))
        title.setObjectName("emptytitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel(tr("从「文件」菜单打开图片，或直接截图 / 从剪贴板粘贴"))
        hint.setObjectName("emptyhint")
        hint.setAlignment(Qt.AlignCenter)
        self.empty_hint = hint
        lay.addWidget(title)
        lay.addWidget(hint)
        return page

    def _update_empty_state(self):
        """按有没有标签页切换空状态；并把依赖图片的菜单项置灰。"""
        has = self.tabs.count() > 0
        try:
            self.stack.setCurrentWidget(self.tabs if has else self.empty_page)
        except Exception:                          # noqa: BLE001
            pass
        for act in getattr(self, "_needs_canvas", []):
            act.setEnabled(has)

    def _build_menubar(self):
        """菜单栏：文件 / 编辑 / 视图 / 特效 / 选项 / 帮助。"""
        bar = self.menuBar()
        bar.setObjectName("editorMenuBar")

        # ---------- 文件 ----------
        m_file = bar.addMenu(tr("文件"))
        self.menus = {"file": m_file}
        self.act_open_img = QAction(tr("打开图片…"), self)
        self.act_open_img.setShortcut("Ctrl+O")
        self.act_open_img.triggered.connect(self.open_image)
        m_file.addAction(self.act_open_img)
        act_clip = QAction(tr("打开剪贴板图片"), self)
        act_clip.setShortcut("Ctrl+Shift+V")
        act_clip.setToolTip(tr("把剪贴板里的图片作为**新标签**打开"))
        act_clip.triggered.connect(self.open_from_clipboard)
        m_file.addAction(act_clip)
        m_file.addSeparator()
        self.act_save = QAction(tr("保存"), self)
        self.act_save.setShortcut("Ctrl+S")
        self.act_save.triggered.connect(self.save_as)
        m_file.addAction(self.act_save)
        m_file.addSeparator()
        self.act_close_tab = QAction(tr("关闭当前标签"), self)
        self.act_close_tab.setShortcut("Ctrl+W")
        self.act_close_tab.triggered.connect(
            lambda: self.close_tab(self.tabs.currentIndex()))
        m_file.addAction(self.act_close_tab)
        act_quit = QAction(tr("退出"), self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        # ---------- 编辑 ----------
        m_edit = bar.addMenu(tr("编辑"))
        self.menus["edit"] = m_edit
        self.act_m_undo = QAction(tr("撤销"), self)
        self.act_m_undo.setShortcut("Ctrl+Z")
        self.act_m_undo.triggered.connect(lambda: self.canvas and self.canvas.undo())
        m_edit.addAction(self.act_m_undo)
        self.act_m_redo = QAction(tr("重做"), self)
        self.act_m_redo.setShortcut("Ctrl+Y")
        self.act_m_redo.triggered.connect(lambda: self.canvas and self.canvas.redo())
        m_edit.addAction(self.act_m_redo)
        m_edit.addSeparator()
        # 粘贴到当前图上（浮层：可拖动/缩放后再固定）——做指引时把两张截图拼一张
        self.act_paste = QAction(tr("粘贴到当前图（浮动）"), self)
        self.act_paste.setShortcut("Ctrl+V")
        self.act_paste.setToolTip(
            tr("把剪贴板里的截图贴到当前图上：拖动摆位置、Ctrl+滚轮缩放，"
               "Enter 固定、Esc 取消"))
        self.act_paste.triggered.connect(self.paste_onto_current)
        m_edit.addAction(self.act_paste)
        self.act_paste_ok = QAction(tr("固定粘贴的图"), self)
        self.act_paste_ok.setToolTip(tr("把正在摆放的粘贴图合成进当前图（Enter）"))
        self.act_paste_ok.triggered.connect(self.commit_pasted)
        m_edit.addAction(self.act_paste_ok)
        self.act_paste_cancel = QAction(tr("取消粘贴"), self)
        self.act_paste_cancel.setToolTip(tr("丢掉正在摆放的粘贴图（Esc）"))
        self.act_paste_cancel.triggered.connect(self.discard_pasted)
        m_edit.addAction(self.act_paste_cancel)
        # 粘贴图外观：阴影/描边/圆角（做指引时让贴上去的图"浮起来"）
        menu_paste_style = QMenu(tr("粘贴图外观"), m_edit)
        self.act_ps_shadow = QAction(tr("加阴影"), self)
        self.act_ps_shadow.setCheckable(True)
        self.act_ps_shadow.toggled.connect(
            lambda on: self._float_style(shadow=on))
        menu_paste_style.addAction(self.act_ps_shadow)
        self.act_ps_stroke = QAction(tr("加白色描边"), self)
        self.act_ps_stroke.setCheckable(True)
        self.act_ps_stroke.toggled.connect(
            lambda on: self._float_style(stroke=on))
        menu_paste_style.addAction(self.act_ps_stroke)
        menu_paste_style.addSeparator()
        for label, radius in ((tr("直角"), 0), (tr("小圆角"), 10),
                              (tr("大圆角"), 24)):
            act = QAction(label, self)
            act.triggered.connect(
                lambda checked=False, r=radius: self._float_style(radius=r))
            menu_paste_style.addAction(act)
        m_edit.addMenu(menu_paste_style)
        m_edit.addSeparator()
        # 选中图形的层级 / 微调 / 再制（做指引时会叠好几层，顺序很要紧）
        self.act_front = QAction(tr("置于顶层"), self)
        self.act_front.triggered.connect(lambda: self._layer("front"))
        m_edit.addAction(self.act_front)
        self.act_back = QAction(tr("置于底层"), self)
        self.act_back.triggered.connect(lambda: self._layer("back"))
        m_edit.addAction(self.act_back)
        self.act_up = QAction(tr("上移一层"), self)
        self.act_up.triggered.connect(lambda: self._layer("up"))
        m_edit.addAction(self.act_up)
        self.act_down = QAction(tr("下移一层"), self)
        self.act_down.triggered.connect(lambda: self._layer("down"))
        m_edit.addAction(self.act_down)
        self.act_dup = QAction(tr("再制一个"), self)
        self.act_dup.setShortcut("Ctrl+D")
        self.act_dup.setToolTip(tr("复制选中的图形/文字，向右下错开一点"))
        self.act_dup.triggered.connect(self.duplicate_selected)
        m_edit.addAction(self.act_dup)
        self.act_rotate = QAction(tr("旋转 15°"), self)
        self.act_rotate.setToolTip(
            tr("把选中图形转 15°（拖它上面的圆形手柄可以任意角度）"))
        self.act_rotate.triggered.connect(lambda: self.rotate_selected(15))
        m_edit.addAction(self.act_rotate)
        self.act_rotate0 = QAction(tr("摆正（0°）"), self)
        self.act_rotate0.triggered.connect(lambda: self.rotate_selected(None))
        m_edit.addAction(self.act_rotate0)
        m_edit.addSeparator()
        self.act_edit_text = QAction(tr("修改文字…"), self)
        self.act_edit_text.setShortcut("F2")
        self.act_edit_text.setToolTip(tr("改选中文字的内容（也可以直接双击文字）"))
        self.act_edit_text.triggered.connect(self.edit_selected_text)
        m_edit.addAction(self.act_edit_text)
        self.act_font = QAction(tr("字体…"), self)
        self.act_font.setToolTip(
            tr("选字体/字号/粗体：选中文字就改它，否则改之后新写的文字"))
        self.act_font.triggered.connect(self.choose_font)
        m_edit.addAction(self.act_font)
        m_edit.addSeparator()
        self.act_m_copy = QAction(tr("复制到剪贴板"), self)
        self.act_m_copy.setShortcut("Ctrl+C")
        self.act_m_copy.triggered.connect(self.copy_to_clipboard)
        m_edit.addAction(self.act_m_copy)
        self.act_m_pin = QAction(tr("贴图到屏幕"), self)
        self.act_m_pin.triggered.connect(self.pin_to_screen)
        m_edit.addAction(self.act_m_pin)

        # ---------- 视图 ----------
        m_view = bar.addMenu(tr("视图"))
        self.menus["view"] = m_view
        self.act_zoom_in = QAction(tr("放大"), self)
        self.act_zoom_in.setShortcut("Ctrl+=")
        self.act_zoom_in.triggered.connect(lambda: self._zoom_step(1.25))
        m_view.addAction(self.act_zoom_in)
        self.act_zoom_out = QAction(tr("缩小"), self)
        self.act_zoom_out.setShortcut("Ctrl+-")
        self.act_zoom_out.triggered.connect(lambda: self._zoom_step(1 / 1.25))
        m_view.addAction(self.act_zoom_out)
        self.act_zoom_100 = QAction(tr("实际像素 (1:1)"), self)
        self.act_zoom_100.setShortcut("Ctrl+0")
        self.act_zoom_100.triggered.connect(lambda: self._set_zoom(1.0))
        m_view.addAction(self.act_zoom_100)
        self.act_zoom_fit = QAction(tr("适应窗口"), self)
        self.act_zoom_fit.triggered.connect(self.fit_to_window)
        m_view.addAction(self.act_zoom_fit)

        # ---------- 特效 ----------
        # （画布翻转/旋转 90°/改尺寸 放在这里：都属于"整张图的变换"）
        m_fx = bar.addMenu(tr("特效"))
        self.menus["fx"] = m_fx
        self.act_m_wm = QAction(tr("水印…"), self)
        self.act_m_wm.triggered.connect(self.add_watermark)
        m_fx.addAction(self.act_m_wm)
        self.act_m_border = QAction(tr("边框…"), self)
        self.act_m_border.triggered.connect(self.add_border)
        m_fx.addAction(self.act_m_border)
        m_fx.addSeparator()
        self.act_flip_h = QAction(tr("水平翻转"), self)
        self.act_flip_h.setToolTip(tr("左右镜像（标注也跟着翻，可 Ctrl+Z 撤销）"))
        self.act_flip_h.triggered.connect(self.flip_h)
        m_fx.addAction(self.act_flip_h)
        self.act_flip_v = QAction(tr("垂直翻转"), self)
        self.act_flip_v.setToolTip(tr("上下镜像（标注也跟着翻，可 Ctrl+Z 撤销）"))
        self.act_flip_v.triggered.connect(self.flip_v)
        m_fx.addAction(self.act_flip_v)
        self.act_rot90 = QAction(tr("顺时针 90°"), self)
        self.act_rot90.triggered.connect(lambda: self.rot90(True))
        m_fx.addAction(self.act_rot90)
        self.act_rot270 = QAction(tr("逆时针 90°"), self)
        self.act_rot270.triggered.connect(lambda: self.rot90(False))
        m_fx.addAction(self.act_rot270)
        self.act_resize_img = QAction(tr("调整尺寸…"), self)
        self.act_resize_img.setToolTip(tr("按像素重设整张图（含标注），可 Ctrl+Z 撤销"))
        self.act_resize_img.triggered.connect(self.resize_image)
        m_fx.addAction(self.act_resize_img)

        # ---------- 选项 ----------
        m_opt = bar.addMenu(tr("选项"))
        self.menus["options"] = m_opt
        self.menu_lang = QMenu(tr("语言"), m_opt)
        self.menu_lang.aboutToShow.connect(self._rebuild_language_menu)
        m_opt.addMenu(self.menu_lang)
        m_opt.addSeparator()
        self.act_restore = QAction(tr("启动时恢复上次的截图"), self)
        self.act_restore.setCheckable(True)
        try:
            from session import session_enabled
            self.act_restore.setChecked(session_enabled())
        except Exception:                          # noqa: BLE001
            self.act_restore.setChecked(True)
        self.act_restore.setToolTip(
            tr("重启后自动把上次编辑的截图放回来（存在缓存里，不需要你保存）"))
        self.act_restore.toggled.connect(self._toggle_restore_session)
        m_opt.addAction(self.act_restore)
        m_opt.addSeparator()
        # 想截编辑器本身（写文档/做教程）时必须打开这条：否则一按截图，
        # 编辑器自己就最小化让位了，截不到它。
        self.act_keep_editor = QAction(tr("截图时不最小化编辑器"), self)
        self.act_keep_editor.setCheckable(True)
        self.act_keep_editor.setChecked(keep_editor_on_capture())
        self.act_keep_editor.setToolTip(
            tr("打开后截图时编辑器留在原地，方便截编辑器自己；"
               "平时关着（截图时自动让位，免得被拍进图里）"))
        self.act_keep_editor.toggled.connect(self._toggle_keep_editor)
        m_opt.addAction(self.act_keep_editor)
        m_opt.addSeparator()
        self.act_clear_session = QAction(tr("清除上次的截图缓存"), self)
        self.act_clear_session.triggered.connect(self._clear_session_cache)
        m_opt.addAction(self.act_clear_session)
        m_opt.addSeparator()
        self.act_default_wm = QAction(tr("编辑默认水印…"), self)
        self.act_default_wm.triggered.connect(self.edit_default_watermark)
        m_opt.addAction(self.act_default_wm)
        self.act_default_border = QAction(tr("编辑默认边框…"), self)
        self.act_default_border.triggered.connect(self.edit_default_border)
        m_opt.addAction(self.act_default_border)

        # ---------- 帮助 ----------
        m_help = bar.addMenu(tr("帮助"))
        self.menus["help"] = m_help
        act_about = QAction(tr("关于 PyShot"), self)
        act_about.triggered.connect(self.show_about)
        m_help.addAction(act_about)

        # 依赖图片的菜单项：空状态时置灰
        self._needs_canvas = [self.act_save, self.act_close_tab, self.act_m_undo,
                              self.act_m_redo, self.act_m_copy, self.act_m_pin,
                              self.act_zoom_in, self.act_zoom_out,
                              self.act_zoom_100, self.act_zoom_fit,
                              self.act_m_wm, self.act_m_border]
        return bar

    def _rebuild_language_menu(self):
        """选项 → 语言（三种语言 + 跟随系统）。"""
        from i18n import (AUTO, LANGUAGES, language_name, saved_language,
                          set_language, system_language)
        self.menu_lang.clear()
        cur = saved_language()
        for code, name in LANGUAGES:
            act = QAction(name, self.menu_lang)
            act.setCheckable(True)
            act.setChecked(cur == code)
            act.triggered.connect(
                lambda checked=False, c=code: self._switch_language(c))
            self.menu_lang.addAction(act)
        self.menu_lang.addSeparator()
        act_auto = QAction(
            tr("跟随系统") + f"（{language_name(system_language())}）",
            self.menu_lang)
        act_auto.setCheckable(True)
        act_auto.setChecked(cur == AUTO)
        act_auto.triggered.connect(lambda: self._switch_language(AUTO))
        self.menu_lang.addAction(act_auto)

    def _switch_language(self, code: str):
        from i18n import language_name, set_language
        lang = set_language(code)
        self.retranslate()
        self.statusBar().showMessage(
            tr("界面语言已切换") + f"：{language_name(lang)}", 4000)

    # ---------- 文件 ----------
    def open_image(self):
        """从「文件 → 打开图片」载入图片（在编辑器内直接开）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("打开图片"), str(Path.home()),
            tr("图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"))
        if not path:
            return
        pix = QPixmap(path)
        if not pix.isNull():
            self.add_canvas(pix)

    def open_from_clipboard(self):
        """把剪贴板里的图片作为新标签打开。"""
        img = QApplication.clipboard().image()
        if img is None or img.isNull():
            self.statusBar().showMessage(tr("剪贴板里没有图片"), 3000)
            return
        self.add_canvas(QPixmap.fromImage(img))

    def paste_onto_current(self):
        """把剪贴板里的截图**贴到当前这张图上**（浮层，摆好位置再固定）。

        和「打开剪贴板图片」（新标签）的区别：这条是"在现有图上继续拼"——
        贴上去是一个虚线框的浮动层，可以拖着摆位置、Ctrl+滚轮缩放，
        Enter（或双击）固定进图、Esc 丢弃；固定后 Ctrl+Z 可撤销。
        没有打开的图时退回"新标签"，不然用户按 Ctrl+V 会以为没反应。
        """
        canvas = self.canvas
        # 正在画布上输入文字时，Ctrl+V 应该粘贴**文字**，不能贴图
        edit = getattr(canvas, "_text_edit", None) if canvas is not None else None
        if edit is not None:
            edit.paste()
            return
        img = QApplication.clipboard().image()
        if img is None or img.isNull():
            self.statusBar().showMessage(tr("剪贴板里没有图片"), 3000)
            return
        pix = QPixmap.fromImage(img)
        if canvas is None:
            self.add_canvas(pix)
            return
        # 手上还有一个没固定的：先固定它，再贴新的 —— 否则会被直接覆盖丢掉
        if canvas.has_float():
            canvas.commit_float()
        canvas.start_float(pix)
        self.statusBar().showMessage(
            tr("已粘贴到当前图：拖动摆位置 · 拖手柄缩放、拖上方圆点旋转 · "
               "Enter 固定 · Esc 取消"),
            6000)
        self._refresh_actions()

    def commit_pasted(self):
        """把正在摆放的浮动粘贴固定进图（菜单项用）。"""
        canvas = self.canvas
        if canvas is not None and canvas.has_float():
            canvas.commit_float()
            self.statusBar().showMessage(tr("已固定粘贴的图（Ctrl+Z 可撤销）"), 4000)

    # ---------- 选中图形的层级 / 再制 / 旋转 ----------
    def _layer(self, how: str):
        """调整选中图形的叠放顺序：front/back/up/down。"""
        canvas = self.canvas
        shape = canvas._selected if canvas is not None else None
        if shape is None or shape not in canvas.shapes:
            self.statusBar().showMessage(tr("先选一个图形（用「选择」工具点一下）"), 3000)
            return
        canvas.push_undo()
        i = canvas.shapes.index(shape)
        canvas.shapes.pop(i)
        if how == "front":
            canvas.shapes.append(shape)
        elif how == "back":
            canvas.shapes.insert(0, shape)
        elif how == "up":
            canvas.shapes.insert(min(len(canvas.shapes), i + 1), shape)
        else:
            canvas.shapes.insert(max(0, i - 1), shape)
        canvas.update()
        canvas.shapes_changed.emit()

    def duplicate_selected(self):
        """再制选中图形（错开 12px），新图形成为当前选中。"""
        canvas = self.canvas
        shape = canvas._selected if canvas is not None else None
        if shape is None or shape not in canvas.shapes:
            self.statusBar().showMessage(tr("先选一个图形（用「选择」工具点一下）"), 3000)
            return
        canvas.push_undo()
        dup = shape.clone()
        dup.move_by(12, 12)
        canvas.shapes.append(dup)
        canvas._selected = dup
        canvas.selection_changed.emit(dup)
        canvas.update()
        canvas.shapes_changed.emit()
        self.statusBar().showMessage(tr("已再制一个（Ctrl+Z 可撤销）"), 3000)

    def _on_canvas_context(self, what: str):
        """画布右键菜单的动作分发。"""
        if what in ("front", "up", "down", "back"):
            self._layer(what)
        elif what == "dup":
            self.duplicate_selected()
        elif what == "rot15":
            self.rotate_selected(15)
        elif what == "rot0":
            self.rotate_selected(None)
        elif what == "edit_text":
            self.edit_selected_text()

    def _selected_text(self):
        """当前选中的文字图形（没选中文字就返回 None）。"""
        canvas = self.canvas
        shape = canvas._selected if canvas is not None else None
        if isinstance(shape, TextShape) and shape in canvas.shapes:
            return shape, canvas
        return None, canvas

    def edit_selected_text(self):
        """改选中文字的内容（等效于双击它）。"""
        shape, canvas = self._selected_text()
        if shape is None:
            self.statusBar().showMessage(
                tr("先选一段文字（用「选择」工具点一下，或直接双击文字）"), 3000)
            return
        canvas._open_text_editor(shape.pos, target=shape)

    def choose_font(self):
        """选字体/字号/粗体：选中文字就改它，否则作为新文字的默认。"""
        shape, canvas = self._selected_text()
        cur = QFont(shape.font()) if shape is not None else QFont(
            getattr(canvas, "font_family", "") or "Microsoft YaHei")
        if shape is None and canvas is not None:
            cur.setPixelSize(int(canvas.font_size))
        ok, font = QFontDialog.getFont(cur, self, tr("选择字体"))
        if not ok:
            return
        family = font.family()
        size = int(font.pixelSize()) if font.pixelSize() > 0 else int(
            font.pointSizeF() * 1.33) or 20
        bold = font.bold()
        if shape is not None:
            canvas.push_undo()
            shape.family = family
            shape.font_size = max(8, size)
            shape.bold = bold
            self.font_spin.setValue(shape.font_size)   # 让工具栏跟着变
            canvas.update()
            canvas.shapes_changed.emit()
            self.statusBar().showMessage(tr("已改字体（Ctrl+Z 可撤销）"), 3000)
            return
        if canvas is not None:
            canvas.font_family = family
            canvas.font_size = max(8, size)
        self.font_spin.setValue(max(10, min(96, size)))
        self.statusBar().showMessage(tr("之后的文字用这个字体"), 3000)

    def rotate_selected(self, degrees: float | None):
        """旋转选中图形；degrees=None 表示摆正（回到 0°）。"""
        canvas = self.canvas
        shape = canvas._selected if canvas is not None else None
        if shape is None or shape not in canvas.shapes:
            self.statusBar().showMessage(tr("先选一个图形（用「选择」工具点一下）"), 3000)
            return
        canvas.push_undo()
        if degrees is None:
            shape.rotation = 0.0
        else:
            shape.rotate_by(degrees)
        canvas.update()
        canvas.shapes_changed.emit()
        self.statusBar().showMessage(
            tr("旋转 {:.0f}°（Ctrl+Z 可撤销）", float(getattr(shape, "rotation", 0))),
            3000)

    def discard_pasted(self):
        """丢弃正在摆放的浮动粘贴。"""
        canvas = self.canvas
        if canvas is not None and canvas.has_float():
            canvas.cancel_float()
            self.statusBar().showMessage(tr("已取消粘贴"), 3000)

    def _float_style(self, **kw):
        """改粘贴图外观；这次没有浮层时也记住，下次粘贴就带上。"""
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.set_float_style(**kw)
        if self._shared is not None:
            self._shared.setdefault("float_style", {}).update(kw)

    # ---------- 画布变换（菜单入口）----------
    def flip_h(self):
        if self.canvas is not None:
            self.canvas.flip_horizontal()
            self.statusBar().showMessage(tr("已水平翻转（Ctrl+Z 可撤销）"), 3000)

    def flip_v(self):
        if self.canvas is not None:
            self.canvas.flip_vertical()
            self.statusBar().showMessage(tr("已垂直翻转（Ctrl+Z 可撤销）"), 3000)

    def rot90(self, clockwise: bool = True):
        if self.canvas is not None:
            self.canvas.rotate90(clockwise)
            self.statusBar().showMessage(
                tr("已旋转 90°（Ctrl+Z 可撤销）") if clockwise
                else tr("已逆时针旋转 90°（Ctrl+Z 可撤销）"), 3000)

    def resize_image(self):
        """调整尺寸对话框：按像素重设整张图（含标注）。"""
        canvas = self.canvas
        if canvas is None:
            return
        w, h = canvas.base_pixmap.width(), canvas.base_pixmap.height()
        new_w, ok = QInputDialog.getInt(
            self, tr("调整尺寸"), tr("宽度（像素，当前 {}）", w), w, 8, 20000, 1)
        if not ok:
            return
        new_h, ok = QInputDialog.getInt(
            self, tr("调整尺寸"), tr("高度（像素，当前 {}）", h), h, 8, 20000, 1)
        if not ok:
            return
        canvas.scale_canvas(new_w, new_h)
        self.statusBar().showMessage(
            tr("已调整为 {} × {}（Ctrl+Z 可撤销）", new_w, new_h), 4000)

    def show_about(self):
        """关于：一句话 + 版本号 + 主要能力（三语齐全）。"""
        QMessageBox.about(
            self, tr("关于 PyShot"),
            tr("PyShot {} — {}\n"
               "仿 FastStone Capture 的截图与标注工具\n\n"
               "托盘右键：区域截图 / 全屏截图 / 滚动长截图 / 屏幕取色 / 贴图\n"
               "编辑器：多标签标注 · 粘贴拼图 · 水印 · 加边框（含手撕纸）· 三语界面",
               APP_VERSION, tr(VERSION_TITLE)))

    def _toggle_restore_session(self, on: bool):
        try:
            from session import clear_session, set_session_enabled
            set_session_enabled(bool(on))
            if not on:
                clear_session()
        except Exception:                          # noqa: BLE001
            pass

    def _toggle_keep_editor(self, on: bool):
        """「截图时不最小化编辑器」开关：存进设置，主程序截图时读它。"""
        try:
            from i18n import set_setting
            set_setting(KEEP_EDITOR_SETTING, bool(on))
        except Exception:                          # noqa: BLE001
            pass
        self.statusBar().showMessage(
            tr("已开启：截图时编辑器留在原地（方便截编辑器自己）") if on
            else tr("已关闭：截图时编辑器自动最小化让位"), 4000)

    def _clear_session_cache(self):
        """手动清掉上次的截图缓存（不影响当前打开的标签）。"""
        try:
            from session import clear_session
            clear_session()
            self.statusBar().showMessage(tr("已清除上次的截图缓存"), 3000)
        except Exception:                          # noqa: BLE001
            pass

    def edit_default_watermark(self):
        """编辑"新截图自动加的水印"（不作用于当前标签）。"""
        from watermark import WatermarkDialog, load_default
        from watermark import save_default as wm_save
        canvas = self.canvas
        size = canvas.base_pixmap.size() if canvas else QSize(640, 400)
        dlg = WatermarkDialog(self, load_default(), size)
        if dlg.exec() == QDialog.Accepted:
            settings = dlg.settings()
            settings["auto"] = True
            wm_save(settings)
            self.statusBar().showMessage(
                tr("已设为默认水印，之后每次新截图会自动添加"), 4000)

    def edit_default_border(self):
        """编辑"新截图自动加的边框"（不作用于当前标签）。"""
        from border import BorderDialog, load_border_default
        from border import save_border_default as bd_save
        canvas = self.canvas
        size = canvas.base_pixmap.size() if canvas else QSize(640, 400)
        dlg = BorderDialog(self, load_border_default(), size)
        if dlg.exec() == QDialog.Accepted:
            settings = dlg.settings()
            settings["auto"] = True
            bd_save(settings)
            self.statusBar().showMessage(
                tr("已设为默认边框，之后每次新截图会自动加"), 4000)

    def _zoom_step(self, factor: float):
        canvas = self.canvas
        if canvas is None:
            return
        canvas.fit_mode = False                    # 手动缩放 → 退出适应模式
        canvas.set_zoom(canvas.zoom * factor)

    def _set_zoom(self, zoom: float):
        canvas = self.canvas
        if canvas is not None:
            canvas.fit_mode = False                # 指定缩放 → 退出适应模式
            canvas.set_zoom(zoom)

    def fit_to_window(self):
        scroll = self.scroll
        canvas = self.canvas
        if canvas is not None and scroll is not None:
            self._fit_canvas(canvas, scroll)

    # ---------- 会话（记住上次的截图）----------
    def session_tabs(self) -> list:
        """导出本窗口所有标签（底图 + 标注 + 缩放 + 标题）。"""
        out = []
        for i in range(self.tabs.count()):
            scroll = self.tabs.widget(i)
            canvas = scroll.widget() if isinstance(scroll, QScrollArea) else None
            if not isinstance(canvas, Canvas):
                continue
            out.append({"title": self.tabs.tabText(i),
                        "zoom": float(canvas.zoom),
                        "pixmap": canvas.base_pixmap,
                        "shapes": list(canvas.shapes)})
        return out

    def restore_session(self, tabs: list):
        """把上次的标签放回来（含标注）。"""
        for tab in tabs:
            canvas = self.add_canvas(tab["pixmap"], tab.get("title"))
            for sh in tab.get("shapes", []):
                canvas.shapes.append(sh)
            try:
                canvas.set_zoom(float(tab.get("zoom", 1.0) or 1.0))
            except Exception:                      # noqa: BLE001
                pass
            canvas.update()
            canvas.shapes_changed.emit()

    def notify_session_saved(self):
        """让主程序知道"内容变了，该更新会话缓存了"。"""
        self.session_dirty.emit()

    def add_canvas(self, pixmap: QPixmap, title: str | None = None) -> Canvas:
        """新增一个截图标签页并切换过去。"""
        canvas = Canvas(pixmap)
        canvas.tool = self._shared["tool"]
        canvas.color = QColor(self._shared["color"])
        canvas.pen_width = self._shared["pen_width"]
        canvas.font_size = self._shared["font_size"]
        canvas.step_diameter = self._shared["step_diameter"]
        canvas.set_float_style(**self._shared.get("float_style", {}))
        canvas.setCursor(Qt.CrossCursor if canvas.tool != "select" else Qt.ArrowCursor)
        canvas.shapes_changed.connect(self._refresh_actions)
        canvas.float_changed.connect(self._refresh_actions)
        canvas.context_action.connect(self._on_canvas_context)
        canvas.color_picked.connect(self._on_color_picked)
        canvas.selection_changed.connect(self._on_selection_changed)
        canvas.escape_idle.connect(self.close)  # 空闲时 Esc 关闭编辑器
        canvas.zoom_changed.connect(lambda z, c=canvas: self._on_canvas_zoom(c, z))

        scroll = QScrollArea()
        canvas._scroll_area = scroll            # 拖动查看时要用它调滚动条
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignCenter)

        idx = self.tabs.addTab(scroll, title or tr("截图 {}").format(self.tabs.count() + 1))
        self.tabs.setTabToolTip(
            idx, f"{pixmap.width()} × {pixmap.height()} px\n"
                 + tr("滚轮/Ctrl+滚轮 缩放 · 中键或空格拖动查看"))
        # 自定义关闭按钮（自带图标在深色主题下几乎看不见）
        close_btn = QToolButton()
        close_btn.setObjectName("tabclose")
        close_btn.setText("✕")
        close_btn.setToolTip(tr("关闭此标签 (Ctrl+W)"))
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(lambda _=False, page=scroll: self._close_page(page))
        self.tabs.tabBar().setTabButton(idx, QTabBar.RightSide, close_btn)

        self.tabs.setCurrentIndex(idx)
        self._fit_canvas(canvas, scroll)
        # 设为默认的水印 / 边框：新截图自动加上（可 Ctrl+Z 撤销）
        defaults = load_default()
        if defaults.get("auto"):
            canvas.push_undo()
            canvas.shapes.append(WatermarkShape(defaults,
                                                canvas.base_pixmap.size()))
        try:
            from border import load_border_default
            bcfg = load_border_default()
            if bcfg.get("auto"):
                canvas.apply_border(bcfg)      # 内部会 push_undo，可撤销
        except Exception:                      # noqa: BLE001
            pass
        self._update_empty_state()             # 有标签了：收起空状态、放开菜单
        self.session_dirty.emit()
        return canvas

    def closeEvent(self, e):
        """关窗口前把会话存一次。

        不然窗口一关、标签就没了，之后点「显示编辑器」只能得到空白窗口 ——
        用户会觉得"历史不见了"（就是这么被反馈的）。
        """
        try:
            self.closing.emit()
        except Exception:                          # noqa: BLE001
            pass
        super().closeEvent(e)

    def retranslate(self):
        """语言切换后刷新界面文案（画布与标注不受影响）。

        做法是"把当前显示的文案再翻译一次"：i18n 内部有译文→原文的反查，
        所以英文/繁体文本也能翻译回目标语言，反复切换不会错乱。
        """
        from i18n import tr as _tr
        self.setWindowTitle(_tr("PyShot 编辑器"))
        # 通用扫描：按钮 / 标签 / 复选框 / 分组框的文本与提示
        for w in self.findChildren(object):
            try:
                if hasattr(w, "text") and callable(getattr(w, "setText", None)):
                    txt = w.text()
                    if txt:
                        w.setText(_tr(txt))
                if hasattr(w, "setToolTip"):
                    tip = w.toolTip()
                    if tip:
                        w.setToolTip(_tr(tip))
            except Exception:                      # noqa: BLE001
                continue
        # 工具轨道与状态栏
        try:
            for tid, name, tip in TOOLS:
                btn = self.tool_buttons.get(tid)
                if btn is not None:
                    btn.setToolTip(_tr("{} — {}", _tr(name), _tr(tip)))
            self.set_tool(self.tool)
        except Exception:                          # noqa: BLE001
            pass

    def close_tab(self, idx: int):
        page = self.tabs.widget(idx)
        if page is not None:
            self._close_page(page)

        self.tabs_closed.emit()
    def _close_page(self, page):
        idx = self.tabs.indexOf(page)
        if idx < 0:
            return
        self.tabs.removeTab(idx)
        self._update_empty_state()
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
        canvas.set_float_style(**self._shared.get("float_style", {}))
        canvas.setCursor(Qt.CrossCursor if canvas.tool != "select" else Qt.ArrowCursor)
        self.zoom_label.setText(f"{round(canvas.zoom * 100)}%")
        self._refresh_swatch_state()
        self._refresh_actions()
        self._refresh_size_label()
        self._on_selection_changed(canvas._selected)

        QTimer.singleShot(0, self._autofit_current)
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
        ["pan"],
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
                btn.setToolTip(tr("{} — {}", tr(name), tr(tip)))
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
        btn_shot = QPushButton(tr("截图"))
        btn_shot.setObjectName("primarybtn")
        btn_shot.setIcon(make_icon("camera"))
        btn_shot.setIconSize(QSize(17, 17))
        btn_shot.setFixedHeight(self._CTRL_H)
        btn_shot.setToolTip(tr("截取新区域\n会自动最小化编辑器，截完回到这里新增标签"))
        btn_shot.setCursor(Qt.PointingHandCursor)
        btn_shot.clicked.connect(self.capture_requested)
        self.btn_shot = btn_shot
        r1.addWidget(btn_shot)
        r1.addWidget(self._top_sep())

        color_label = QLabel(tr("颜色"))
        color_label.setAlignment(Qt.AlignVCenter)

        # 当前颜色：拾色器吸到的 / 点色板选的，都会实时反映在这里
        self.current_color_btn = QPushButton()
        self.current_color_btn.setObjectName("currentColor")
        self.current_color_btn.setFixedSize(28, 28)
        self.current_color_btn.setCursor(Qt.PointingHandCursor)
        self.current_color_btn.clicked.connect(self._pick_color)

        # 色板拼盘：两行网格（10 列），点一下即设为当前颜色
        palette_box = QWidget()
        grid = QGridLayout(palette_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(3)
        self.color_buttons = []
        for i, hexs in enumerate(PALETTE):
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(18, 18)
            b.setStyleSheet(f"background:{hexs};")
            b.setToolTip(hexs)
            b.clicked.connect(lambda checked, c=hexs: self.set_color(QColor(c)))
            grid.addWidget(b, i // 10, i % 10)
            self.color_buttons.append(b)
        more_palette = QPushButton("▾")
        more_palette.setObjectName("swatchMore")
        more_palette.setFixedSize(18, 18)
        more_palette.setToolTip(tr("更多颜色…（基本颜色 + 自定义颜色）"))
        more_palette.clicked.connect(self._pick_from_palette)
        grid.addWidget(more_palette, 0, 10)
        more = QPushButton("…")
        more.setObjectName("swatchMore")
        more.setFixedSize(18, 18)
        more.setToolTip(tr("自定义颜色"))
        more.clicked.connect(self._pick_color)
        grid.addWidget(more, 1, 10)
        grid.setColumnStretch(10, 1)
        r1.addWidget(self._group(color_label, self.current_color_btn,
                                 palette_box))
        self._refresh_swatch_state()
        r1.addWidget(self._top_sep())

        self.width_spin = SpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(self._shared["pen_width"])
        self.width_spin.setFixedHeight(self._CTRL_H)
        self.width_spin.setFixedWidth(62)
        self.width_spin.valueChanged.connect(self._on_width_changed)
        r1.addWidget(self._labeled(tr("线宽"), self.width_spin))

        self.font_spin = SpinBox()
        self.font_spin.setRange(10, 96)
        self.font_spin.setValue(self._shared["font_size"])
        self.font_spin.setFixedHeight(self._CTRL_H)
        self.font_spin.setFixedWidth(62)
        self.font_spin.valueChanged.connect(self._on_font_changed)
        r1.addWidget(self._labeled(tr("字号"), self.font_spin))

        self.step_spin = SpinBox()
        self.step_spin.setRange(16, 240)
        self.step_spin.setSingleStep(2)
        self.step_spin.setSuffix(" px")
        self.step_spin.setValue(int(self._shared["step_diameter"]))
        self.step_spin.setFixedHeight(self._CTRL_H)
        self.step_spin.setFixedWidth(80)
        self.step_spin.setToolTip(tr("序号圆的大小\n选中已有序号时可直接调整它的大小"))
        self.step_spin.valueChanged.connect(self._on_step_size_changed)
        r1.addWidget(self._labeled(tr("序号"), self.step_spin))

        # ---------- 第 2 行：编辑 / 输出 ----------
        r2 = row()
        self.act_undo = QAction(tr("撤销"), self)
        self.act_undo.setToolTip(tr("撤销 (Ctrl+Z)"))
        self.act_undo.triggered.connect(lambda: self.canvas and self.canvas.undo())
        self.act_redo = QAction(tr("重做"), self)
        self.act_redo.setToolTip(tr("重做 (Ctrl+Y)"))
        self.act_redo.triggered.connect(lambda: self.canvas and self.canvas.redo())
        self.act_crop_ok = QAction(tr("应用裁剪"), self)
        self.act_crop_ok.setToolTip(tr("应用裁剪框 (Enter)"))
        self.act_crop_ok.triggered.connect(
            lambda: self.canvas and self.canvas.apply_crop())
        act_copy = QAction(tr("复制"), self)
        act_copy.setToolTip(tr("复制到剪贴板 (Ctrl+C)"))
        act_copy.triggered.connect(self.copy_to_clipboard)
        act_pin = QAction(tr("贴图"), self)
        act_pin.setToolTip(tr("把当前结果钉在屏幕最上层（Snipaste 风格）"))
        act_pin.triggered.connect(self.pin_to_screen)
        act_wm = QAction(tr("水印"), self)
        act_wm.setToolTip(
            tr("水印：文字与图片可各自开关（也可同时用）\n"
            "九宫格位置或平铺、各自调不透明度、可旋转与设边距\n"
            "还能「应用并设为默认」，之后新截图自动加"))
        act_wm.triggered.connect(self.add_watermark)
        act_border = QAction(tr("边框"), self)
        act_border.setToolTip(
            tr("加边框（对应 FSCapture 的「特效 → 边缘」）\n"
            "单线/双线/虚线/圆角/投影阴影/立体浮雕/边缘渐隐/拍立得白边\n"
            "边框加在图片外面，图会变大；可 Ctrl+Z 撤销"))
        act_border.triggered.connect(self.add_border)
        act_save = QAction(tr("保存"), self)
        act_save.setToolTip(tr("保存为文件 (Ctrl+S)"))
        act_save.triggered.connect(self.save_as)
        act_close = QAction(tr("关闭"), self)
        act_close.setToolTip(tr("关闭编辑器 (Esc)"))
        act_close.triggered.connect(self.close)

        undo_btn = self._icon_button("undo", tr("撤销 (Ctrl+Z)"),
                                     lambda: self.canvas and self.canvas.undo())
        redo_btn = self._icon_button("redo", tr("重做 (Ctrl+Y)"),
                                     lambda: self.canvas and self.canvas.redo())
        self.btn_undo, self.btn_redo = undo_btn, redo_btn
        r2.addWidget(self._group(undo_btn, redo_btn))
        r2.addWidget(self._action_button(self.act_crop_ok))
        r2.addWidget(self._top_sep())
        for act in (act_copy, act_pin, act_wm, act_border, act_save,
                    act_close):
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
        self.tool_name_label.setText(tr("工具：选择"))
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

        zoom_out = _zbtn("−", tr("缩小 (Ctrl+滚轮)"),
                         lambda: self.canvas and self.canvas.set_zoom(self.canvas.zoom / 1.2))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomlabel")
        self.zoom_label.setMinimumWidth(46)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        zoom_in = _zbtn("＋", tr("放大 (Ctrl+滚轮)"),
                        lambda: self.canvas and self.canvas.set_zoom(self.canvas.zoom * 1.2))
        zlay.addWidget(zoom_out)
        zlay.addWidget(self.zoom_label)
        zlay.addWidget(zoom_in)
        sep = QFrame()
        sep.setObjectName("zoomsep")
        sep.setFrameShape(QFrame.VLine)
        zlay.addWidget(sep)
        zlay.addWidget(_zbtn("100%", tr("实际像素 (1:1)"),
                             lambda: self.canvas and self.canvas.set_zoom(1.0), width=44))
        zlay.addWidget(_zbtn(tr("适应"), tr("缩放以适应窗口"),
                             self._zoom_fit, width=44))
        sb.addPermanentWidget(zoom_group)

    def _build_shortcuts(self):
        # 注意：Ctrl+Z / Ctrl+Y / Ctrl+S / Ctrl+C / Ctrl+W / Ctrl+O 这些
        # **已经由菜单栏的 QAction 提供**，这里不能再注册一遍 ——
        # 同一个窗口里两个动作用同一个按键序列会被 Qt 判为"歧义"，
        # 结果是**两个都不触发**（Ctrl+Z 失效就是这么来的）。
        # 这里只放菜单里没有的：重做备选键、切标签、以及单字母工具键。
        for seq, fn in [
            ("Ctrl+Shift+Z", lambda: self.canvas and self.canvas.redo()),
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
            tr("截取新区域{}\n会自动最小化编辑器，截完回到这里新增标签", suffix))

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
                c.set_tool_cursor()            # 抓手工具显示手型
                c.update()
        self.tool_buttons[tid].setChecked(True)
        self._refresh_actions()
        name = dict((t, n) for t, n, _ in TOOLS).get(tid, tid)
        self.tool_name_label.setText(tr("工具：") + tr(name))

    def _on_color_picked(self, color: QColor):
        self._refresh_swatch_state()
        self.statusBar().showMessage(
            tr("已取色") + f" {color.name().upper()}" + tr("，切回")
            + tr(dict((t, n) for t, n, _ in TOOLS)[self._prev_tool]) + tr(" 工具"),
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
        """字号：作用于新文字，同时实时调整**选中的文字**（和序号大小一致的手感）。"""
        self._shared["font_size"] = v
        for i in range(self.tabs.count()):
            c = self.tabs.widget(i).widget()
            if isinstance(c, Canvas):
                c.font_size = v
        canvas = self.canvas
        shape = canvas._selected if canvas is not None else None
        if isinstance(shape, TextShape) and shape in canvas.shapes:
            if int(shape.font_size) != int(v):
                canvas.push_undo()
                shape.font_size = max(8, int(v))
                canvas.update()
                canvas.shapes_changed.emit()

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
        # 当前颜色按钮：背景就是当前色，提示里带上色值
        try:
            name = QColor(self._shared["color"]).name()
            self.current_color_btn.setStyleSheet(
                f"background:{name}; border:2px solid #ffffff;"
                "border-radius:6px;")
            self.current_color_btn.setToolTip(tr("当前颜色") + f"  {name}")
        except Exception:                          # noqa: BLE001
            pass

    def _pick_from_palette(self):
        """打开大调色板（系统拾色盘风格）。"""
        dlg = ColorPaletteDialog(self, self._shared["color"])
        if dlg.exec() == QDialog.Accepted:
            self.set_color(dlg.selected())

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
        target = min(1.0, max(0.1, min(zx, zy)))
        canvas.fit_mode = True                     # 这就是「适应窗口」
        # 滞回：适配本身会让画布尺寸变化 → 滚动条出现/消失 → 视口又变一点，
        # 阈值太小就会来回抖（实测差约 2.4%）。差异小于 3% 视为已经合身。
        if abs(canvas.zoom - target) < 0.03:
            return
        canvas.set_zoom(target)                    # 它会清掉 fit_mode
        canvas.fit_mode = True                     # 适应窗口：再置回

    def resizeEvent(self, e):
        """窗口尺寸变化时，处于"适应模式"的标签跟着重新适配。

        用防抖：拖动窗口会连续触发 resizeEvent，攒一下再算一次。
        """
        super().resizeEvent(e)
        if getattr(self, "_fitting", False):
            return
        if getattr(self, "_resize_timer", None) is None:
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._autofit_current)
        self._resize_timer.start(60)

    def _autofit_current(self):
        """把当前标签按窗口重新适配（仅当它处于适应模式）。"""
        if getattr(self, "_fitting", False):
            return
        canvas, scroll = self.canvas, self.scroll
        if canvas is None or scroll is None or not getattr(canvas, "fit_mode",
                                                           False):
            return
        self._fitting = True
        try:
            self._fit_canvas(canvas, scroll)
        finally:
            self._fitting = False

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
        # 浮动粘贴的两个动作只在真的有个浮动图时才可用
        floating = bool(canvas and canvas.has_float())
        self.act_paste_ok.setEnabled(floating)
        self.act_paste_cancel.setEnabled(floating)
        # 图层/再制/旋转要有选中的图形才有意义
        has_sel = bool(canvas and canvas._selected is not None
                       and canvas._selected in canvas.shapes)
        for act in (self.act_front, self.act_back, self.act_up, self.act_down,
                    self.act_dup, self.act_rotate, self.act_rotate0):
            act.setEnabled(has_sel)

    def copy_to_clipboard(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas._commit_text()
        QApplication.clipboard().setPixmap(canvas.render_result())
        self.statusBar().showMessage(tr("已复制到剪贴板"), 2000)

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

    # ---------- 边框（FSCapture 的「特效 → 边缘」）----------
    def add_border(self):
        """打开边框对话框，给当前标签加边框（图会变大，可撤销）。

        注意：这里导入的是**真实名字**，不要用 `as` 起别名 ——
        合并成单文件时本地 import 会被删掉，别名就悬空了（曾因此崩过）。
        """
        canvas = self.canvas
        if canvas is None:
            return
        from border import BorderDialog, load_border_default
        from border import save_border_default
        dlg = BorderDialog(self, load_border_default(),
                           canvas.base_pixmap.size())
        if dlg.exec() != QDialog.Accepted:
            return
        settings = dlg.settings()
        if dlg.save_as_default():
            settings["auto"] = True
            saved = save_border_default(settings)
            self.statusBar().showMessage(
                "已设为默认边框，之后每次新截图会自动加"
                if saved else "已设为默认边框（本次运行有效，配置写入失败）",
                4000)
        if not self.apply_border(canvas, settings):
            self.statusBar().showMessage(tr("边框宽度为 0，未做改动"), 3000)
        else:
            self._fit_canvas(canvas, self.tabs.currentWidget())

    def apply_border(self, canvas: Canvas, settings: dict) -> bool:
        ok = canvas.apply_border(settings)
        if ok:
            self.statusBar().showMessage(
                tr("已加边框：") + f"{canvas.base_pixmap.width()}×"
                f"{canvas.base_pixmap.height()} px", 4000)
        return ok

    def save_as(self):
        canvas = self.canvas
        if canvas is None:
            return
        canvas._commit_text()
        idx = self.tabs.currentIndex() + 1
        default = f"screenshot-{idx}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("保存截图"), default,
            tr("PNG 图片 (*.png);;JPEG 图片 (*.jpg);;BMP 图片 (*.bmp)"))
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
        self.statusBar().showMessage(tr("已保存：") + path, 4000)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        # 正在摆放浮动粘贴时，Ctrl+滚轮改缩放浮层（比画布缩放更常用；
        # 想缩放画布先 Enter/Esc 结束摆放）
        if (e.modifiers() & Qt.ControlModifier and self.canvas is not None
                and self.canvas.has_float()):
            factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
            self.canvas.scale_float(factor)
            e.accept()
            return
        if e.modifiers() & Qt.ControlModifier and self.canvas is not None:
            delta = e.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.canvas.fit_mode = False           # 手动缩放 → 退出适应模式
            self.canvas.set_zoom(self.canvas.zoom * factor)
            e.accept()
            return
        super().wheelEvent(e)
