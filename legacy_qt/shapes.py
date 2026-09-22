# -*- coding: utf-8 -*-
"""标注图形对象：矩形 / 椭圆 / 直线 / 箭头 / 画笔 / 文字 / 序号 / 高亮 / 马赛克。

所有图形使用图像像素坐标（与底图一致），由画布负责缩放。
"""
import copy
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap


class Shape:
    """所有标注图形的基类。"""

    def __init__(self, color: QColor, width: int):
        self.color = QColor(color)
        self.width = max(1, int(width))

    # --- 子类需实现 ---
    def draw(self, painter: QPainter, canvas):
        raise NotImplementedError

    def bounding_rect(self) -> QRectF:
        raise NotImplementedError

    def move_by(self, dx: float, dy: float):
        raise NotImplementedError

    def contains(self, pos: QPointF, tol: float = 6.0) -> bool:
        return self.bounding_rect().adjusted(-tol, -tol, tol, tol).contains(pos)

    # --- 通用 ---
    def pen(self) -> QPen:
        pen = QPen(self.color, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        pen.setCosmetic(False)
        return pen

    def clone(self):
        return copy.deepcopy(self)

    def translate(self, dx: float, dy: float):
        """整体平移（裁剪时使用）。默认按 move_by 处理。"""
        self.move_by(dx, dy)

    # ---------- 缩放手柄 ----------
    # 顺序：0左上 1上中 2右上 3右中 4右下 5下中 6左下 7左中
    def handles(self) -> list:
        """可拖拽的缩放句柄（默认按外接矩形给 8 个；返回空列表表示不可缩放）。"""
        r = self.bounding_rect()
        if r.isNull() or r.width() < 1 or r.height() < 1:
            return []
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        return [QPointF(x0, y0), QPointF(cx, y0), QPointF(x1, y0),
                QPointF(x1, cy), QPointF(x1, y1), QPointF(cx, y1),
                QPointF(x0, y1), QPointF(x0, cy)]

    def resize_by_handle(self, index: int, pos: QPointF):
        """把第 index 个句柄拖到 pos。"""
        r = self.bounding_rect()
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        if index in (0, 1, 2):
            y0 = pos.y()
        elif index in (4, 5, 6):
            y1 = pos.y()
        if index in (0, 6, 7):
            x0 = pos.x()
        elif index in (2, 3, 4):
            x1 = pos.x()
        new = QRectF(QPointF(min(x0, x1), min(y0, y1)),
                     QPointF(max(x0, x1), max(y0, y1)))
        self.apply_rect(new)

    def apply_rect(self, rect: QRectF):
        """把图形拉伸到新的外接矩形（子类按自身语义实现）。"""
        self.move_by(rect.topLeft().x() - self.bounding_rect().left(),
                     rect.topLeft().y() - self.bounding_rect().top())


class RectShape(Shape):
    def __init__(self, color, width, rect: QRectF, fill=False):
        super().__init__(color, width)
        self.rect = QRectF(rect).normalized()
        self.fill = fill

    def apply_rect(self, rect: QRectF):
        self.rect = QRectF(rect).normalized()

    def draw(self, painter, canvas):
        painter.setPen(self.pen())
        if self.fill:
            c = QColor(self.color)
            c.setAlpha(60)
            painter.setBrush(c)
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect)

    def bounding_rect(self):
        return self.rect

    def move_by(self, dx, dy):
        self.rect.translate(dx, dy)


class EllipseShape(RectShape):
    def draw(self, painter, canvas):
        painter.setPen(self.pen())
        if self.fill:
            c = QColor(self.color)
            c.setAlpha(60)
            painter.setBrush(c)
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.rect)


class LineShape(Shape):
    def __init__(self, color, width, p1: QPointF, p2: QPointF):
        super().__init__(color, width)
        self.p1 = QPointF(p1)
        self.p2 = QPointF(p2)

    def handles(self):
        return [QPointF(self.p1), QPointF(self.p2)]

    def resize_by_handle(self, index: int, pos: QPointF):
        if index == 0:
            self.p1 = QPointF(pos)
        else:
            self.p2 = QPointF(pos)

    def apply_rect(self, rect: QRectF):
        # 直线按外接矩形拉伸两个端点（保持方向）
        old = self.bounding_rect()
        if old.width() < 0.5 and old.height() < 0.5:
            return
        sx = rect.width() / old.width() if old.width() > 0.5 else 1.0
        sy = rect.height() / old.height() if old.height() > 0.5 else 1.0
        self.p1 = QPointF(rect.left() + (self.p1.x() - old.left()) * sx,
                          rect.top() + (self.p1.y() - old.top()) * sy)
        self.p2 = QPointF(rect.left() + (self.p2.x() - old.left()) * sx,
                          rect.top() + (self.p2.y() - old.top()) * sy)

    def draw(self, painter, canvas):
        painter.setPen(self.pen())
        painter.drawLine(self.p1, self.p2)

    def bounding_rect(self):
        return QRectF(self.p1, self.p2).normalized()

    def move_by(self, dx, dy):
        self.p1 += QPointF(dx, dy)
        self.p2 += QPointF(dx, dy)


class ArrowShape(LineShape):
    """带箭头头部的直线。"""

    def draw(self, painter, canvas):
        painter.setPen(self.pen())
        painter.drawLine(self.p1, self.p2)
        angle = math.atan2(self.p2.y() - self.p1.y(), self.p2.x() - self.p1.x())
        head = 8 + self.width * 3.0
        spread = math.radians(25)
        for sign in (1, -1):
            a = angle + math.pi + sign * spread
            tip = QPointF(self.p2.x() + head * math.cos(a),
                          self.p2.y() + head * math.sin(a))
            painter.drawLine(self.p2, tip)


class PenShape(Shape):
    """自由画笔轨迹。"""

    def __init__(self, color, width, points=None):
        super().__init__(color, width)
        self.points = [QPointF(p) for p in (points or [])]

    def add_point(self, p: QPointF):
        self.points.append(QPointF(p))

    def draw(self, painter, canvas):
        if len(self.points) < 2:
            if self.points:
                painter.setPen(self.pen())
                painter.drawPoint(self.points[0])
            return
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        painter.setPen(self.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def bounding_rect(self):
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

    def apply_rect(self, rect: QRectF):
        old = self.bounding_rect()
        if old.width() < 1 or old.height() < 1 or not self.points:
            return
        sx = rect.width() / old.width()
        sy = rect.height() / old.height()
        self.points = [QPointF(rect.left() + (p.x() - old.left()) * sx,
                               rect.top() + (p.y() - old.top()) * sy)
                       for p in self.points]

    def move_by(self, dx, dy):
        d = QPointF(dx, dy)
        self.points = [p + d for p in self.points]


class TextShape(Shape):
    def __init__(self, color, width, pos: QPointF, text: str, font_size: int):
        super().__init__(color, width)
        self.pos = QPointF(pos)
        self.text = text
        self.font_size = max(8, int(font_size))

    def font(self) -> QFont:
        f = QFont("Microsoft YaHei")
        f.setPixelSize(self.font_size)
        f.setBold(True)
        return f

    def draw(self, painter, canvas):
        painter.setFont(self.font())
        painter.setPen(QPen(self.color))
        # 白色描边提升可读性
        metrics = painter.fontMetrics()
        for i, line in enumerate(self.text.split("\n")):
            y = self.pos.y() + i * metrics.lineSpacing()
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.setPen(QPen(QColor(255, 255, 255, 200)))
                painter.drawText(QPointF(self.pos.x() + ox, y + oy), line)
            painter.setPen(QPen(self.color))
            painter.drawText(QPointF(self.pos.x(), y), line)

    def bounding_rect(self):
        metrics = _metrics(self.font())
        lines = self.text.split("\n")
        w = max((metrics.horizontalAdvance(s) for s in lines), default=0)
        h = metrics.lineSpacing() * len(lines)
        return QRectF(self.pos.x() - 2, self.pos.y() - metrics.ascent() - 2,
                      w + 6, h + 6)

    def apply_rect(self, rect: QRectF):
        """缩放文字：按高度比例改字号（8~400），并把左上角搬到新位置。"""
        old = self.bounding_rect()
        if old.height() < 2:
            return
        ratio = rect.height() / old.height()
        self.font_size = int(min(400, max(8, round(self.font_size * ratio))))
        metrics = _metrics(self.font())
        self.pos = QPointF(rect.left() + 2,
                           rect.top() + 2 + metrics.ascent())

    def move_by(self, dx, dy):
        self.pos += QPointF(dx, dy)


def _metrics(font: QFont):
    from PySide6.QtGui import QFontMetrics
    return QFontMetrics(font)


class StepShape(Shape):
    """序号步骤：圆形底 + 数字，做操作指引的核心工具。

    直径（diameter）独立可调，数字大小自动跟随直径，保证任何尺寸下都居中好看。
    """

    def __init__(self, color, width, center: QPointF, number: int,
                 font_size: int = 20, diameter: float | None = None):
        super().__init__(color, width)
        self.center = QPointF(center)
        self.number = int(number)
        self.font_size = max(8, int(font_size))
        # 未指定直径时按字号推算（兼容旧调用）
        self.diameter = float(diameter) if diameter else max(24.0, self.font_size * 1.8)

    @property
    def radius(self):
        return self.diameter / 2.0

    def digit_pixel_size(self) -> int:
        """数字字号：跟随直径，但不超过设定的字号上限。"""
        return max(8, int(min(self.diameter * 0.62, self.font_size * 1.8)))

    def set_diameter(self, diameter: float):
        self.diameter = max(16.0, float(diameter))

    def draw(self, painter, canvas):
        r = self.radius
        rect = QRectF(self.center.x() - r, self.center.y() - r, r * 2, r * 2)
        painter.setPen(QPen(QColor(255, 255, 255), max(2, self.width)))
        painter.setBrush(self.color)
        painter.drawEllipse(rect)
        font = QFont("Microsoft YaHei")
        font.setPixelSize(self.digit_pixel_size())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(rect, Qt.AlignCenter, str(self.number))

    def bounding_rect(self):
        r = self.radius
        return QRectF(self.center.x() - r, self.center.y() - r, r * 2, r * 2)

    def apply_rect(self, rect: QRectF):
        """缩放序号：改直径，圆心跟随。"""
        self.center = rect.center()
        self.set_diameter(max(rect.width(), rect.height()))

    def contains(self, pos, tol=6.0):
        return (math.hypot(pos.x() - self.center.x(),
                           pos.y() - self.center.y()) <= self.radius + tol)

    def move_by(self, dx, dy):
        self.center += QPointF(dx, dy)


class HighlightShape(Shape):
    """荧光笔高亮：半透明色块。"""

    def __init__(self, color, width, rect: QRectF):
        super().__init__(color, width)
        self.rect = QRectF(rect).normalized()

    def draw(self, painter, canvas):
        c = QColor(self.color)
        c.setAlpha(110)
        painter.setPen(Qt.NoPen)
        painter.setBrush(c)
        painter.drawRect(self.rect)

    def bounding_rect(self):
        return self.rect

    def move_by(self, dx, dy):
        self.rect.translate(dx, dy)


class MosaicShape(Shape):
    """马赛克：绘制时将底图对应区域像素化。"""

    PIXEL = 12

    def __init__(self, color, width, rect: QRectF):
        super().__init__(color, width)
        self.rect = QRectF(rect).normalized()

    def draw(self, painter, canvas):
        src = canvas.base_pixmap
        r = self.rect.toAlignedRect().intersected(src.rect())
        if r.isEmpty():
            return
        region = src.copy(r)
        region.setDevicePixelRatio(1.0)     # 避免源 dpr 影响贴图尺寸
        w = max(1, r.width() // self.PIXEL)
        h = max(1, r.height() // self.PIXEL)
        small = region.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        blocky = small.scaled(r.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
        blocky.setDevicePixelRatio(1.0)
        # 用显式目标/源矩形，坐标系与图形一致（图像物理像素）
        painter.drawPixmap(QRectF(r), blocky, QRectF(blocky.rect()))

    def bounding_rect(self):
        return self.rect

    def move_by(self, dx, dy):
        self.rect.translate(dx, dy)


class WatermarkShape(Shape):
    """水印（文字/图片、九宫格或平铺、旋转、透明度）。

    非破坏性：和水印相关的参数都在这里，可以随时删除/撤销，不影响底图。
    """

    def __init__(self, settings: dict, image_size, offset=None):
        super().__init__(QColor(settings.get("color", "#ffffff")),
                         int(settings.get("font_size", 28)))
        self.settings = dict(settings)
        self.image_size = QSize(int(image_size.width()),
                                int(image_size.height()))
        self.offset = QPointF(offset) if offset else QPointF(0, 0)
        self._bounds = None

    def _size(self):
        from watermark import watermark_size
        return watermark_size(self.settings, self.image_size)

    def draw(self, painter, canvas):
        from watermark import draw_watermark
        draw_watermark(painter, self.settings, self.image_size, self.offset)

    def bounding_rect(self):
        from watermark import placements
        size = self._size()
        pts = placements(self.settings, self.image_size, size)
        if not pts:
            return QRectF()
        if self.settings.get("position") == 9:      # 平铺：整幅都算
            return QRectF(0, 0, self.image_size.width(), self.image_size.height())
        pt = pts[0] + self.offset
        # 旋转后用一个足够大的外接矩形，保证点选/移动手感
        r = max(size.width(), size.height())
        return QRectF(pt.x(), pt.y(), size.width(), size.height()).adjusted(
            -(r - size.width()) / 2, -(r - size.height()) / 2,
            (r - size.width()) / 2, (r - size.height()) / 2)

    def move_by(self, dx, dy):
        self.offset += QPointF(dx, dy)
        self._bounds = None

    def apply_rect(self, rect: QRectF):
        """缩放水印：按高度比例调整字号或图片大小，并跟到新位置。"""
        old = self.bounding_rect()
        if old.height() < 2 or old.width() < 2:
            return
        ratio = max(0.1, min(8.0, rect.height() / old.height()))
        if self.settings.get("kind") == "image":
            self.settings["image_scale"] = max(
                0.02, min(1.0, float(self.settings.get("image_scale", 0.2)) * ratio))
        else:
            self.settings["font_size"] = int(min(
                400, max(8, round(int(self.settings.get("font_size", 28)) * ratio))))
        self._bounds = None
        new = self.bounding_rect()
        self.offset += QPointF(rect.left() - new.left(), rect.top() - new.top())


def clone_shapes(shapes):
    return copy.deepcopy(shapes)
