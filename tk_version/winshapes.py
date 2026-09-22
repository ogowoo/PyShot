# -*- coding: utf-8 -*-
"""winshapes.py —— 标注图形对象（纯 Python 数据 + 双渲染）。

每个图形有三份职责：
- 数据（坐标、颜色、宽度等，均用**图像像素坐标**）
- `draw_gdi(r, img)`：导出时用 GDI 渲染到图像上
- `draw_tk(cv, ox, oy, zoom)`：交互时用 Tk 画布渲染（只读预览），返回 item id 列表
- `bounding()` / `contains(p)` / `move_by()` / `handles()` / `resize_by_handle()`
"""
import math


def _v(x):
    return int(round(x))


def to_tk_color(color) -> str:
    """颜色 → Tk 的 #RRGGBB（支持 (r,g,b) 元组或已是 hex 字符串）。"""
    if isinstance(color, str):
        return color
    r, g, b = color
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


class Shape:
    def draw_gdi(self, r, img):
        raise NotImplementedError

    def draw_tk(self, cv, ox, oy, zoom):
        raise NotImplementedError

    def bounding(self):
        raise NotImplementedError

    def contains(self, px, py, tol=6.0):
        x0, y0, x1, y1 = self.bounding()
        return x0 - tol <= px <= x1 + tol and y0 - tol <= py <= y1 + tol

    def move_by(self, dx, dy):
        raise NotImplementedError

    def handles(self):
        x0, y0, x1, y1 = self.bounding()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return [(x0, y0), (cx, y0), (x1, y0), (x1, cy),
                (x1, y1), (cx, y1), (x0, y1), (x0, cy)]

    def resize_by_handle(self, index, pos):
        raise NotImplementedError

    def _scale_rect(self, index, pos):
        x0, y0, x1, y1 = self.bounding()
        px, py = pos
        if index in (0, 1, 2):
            y0 = py
        elif index in (4, 5, 6):
            y1 = py
        if index in (0, 6, 7):
            x0 = px
        elif index in (2, 3, 4):
            x1 = px
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


class RectShape(Shape):
    def __init__(self, color, width, rect, fill=False):
        self.color = color
        self.width = max(1, int(width))
        self.rect = tuple(rect)          # (x, y, w, h)
        self.fill = fill

    def bounding(self):
        x, y, w, h = self.rect
        return x, y, x + w, y + h

    def move_by(self, dx, dy):
        x, y, w, h = self.rect
        self.rect = (x + dx, y + dy, w, h)

    def draw_gdi(self, r, img):
        x, y, w, h = self.rect
        r.rect(x, y, w, h, self.color, self.width, self.fill)

    def draw_tk(self, cv, ox, oy, zoom):
        x, y, w, h = self.rect
        x0, y0 = ox + x * zoom, oy + y * zoom
        x1, y1 = x0 + w * zoom, y0 + h * zoom
        if self.fill:
            return [cv.create_rectangle(x0, y0, x1, y1, fill=to_tk_color(self.color),
                                        outline="")]
        return [cv.create_rectangle(x0, y0, x1, y1, outline=to_tk_color(self.color),
                                    width=self.width)]

    def resize_by_handle(self, index, pos):
        self.rect = self._scale_rect(index, pos)


class EllipseShape(RectShape):
    def draw_gdi(self, r, img):
        x, y, w, h = self.rect
        r.ellipse(x, y, w, h, self.color, self.width, self.fill)

    def draw_tk(self, cv, ox, oy, zoom):
        x, y, w, h = self.rect
        x0, y0 = ox + x * zoom, oy + y * zoom
        x1, y1 = x0 + w * zoom, y0 + h * zoom
        if self.fill:
            return [cv.create_oval(x0, y0, x1, y1, fill=to_tk_color(self.color), outline="")]
        return [cv.create_oval(x0, y0, x1, y1, outline=to_tk_color(self.color),
                               width=self.width)]


class LineShape(Shape):
    def __init__(self, color, width, p1, p2):
        self.color = color
        self.width = max(1, int(width))
        self.p1 = tuple(p1)
        self.p2 = tuple(p2)

    def bounding(self):
        return (min(self.p1[0], self.p2[0]), min(self.p1[1], self.p2[1]),
                max(self.p1[0], self.p2[0]), max(self.p1[1], self.p2[1]))

    def move_by(self, dx, dy):
        self.p1 = (self.p1[0] + dx, self.p1[1] + dy)
        self.p2 = (self.p2[0] + dx, self.p2[1] + dy)

    def draw_gdi(self, r, img):
        r.line(self.p1[0], self.p1[1], self.p2[0], self.p2[1],
               self.color, self.width)

    def draw_tk(self, cv, ox, oy, zoom):
        return [cv.create_line(ox + self.p1[0] * zoom, oy + self.p1[1] * zoom,
                               ox + self.p2[0] * zoom, oy + self.p2[1] * zoom,
                               fill=to_tk_color(self.color), width=self.width)]

    def handles(self):
        return [tuple(self.p1), tuple(self.p2)]

    def resize_by_handle(self, index, pos):
        if index == 0:
            self.p1 = tuple(pos)
        else:
            self.p2 = tuple(pos)


class ArrowShape(LineShape):
    def draw_gdi(self, r, img):
        r.line(self.p1[0], self.p1[1], self.p2[0], self.p2[1],
               self.color, self.width)
        ang = math.atan2(self.p2[1] - self.p1[1], self.p2[0] - self.p1[0])
        head = 8 + self.width * 3.0
        spread = math.radians(25)
        for sign in (1, -1):
            a = ang + math.pi + sign * spread
            tip_x = self.p2[0] + head * math.cos(a)
            tip_y = self.p2[1] + head * math.sin(a)
            r.line(self.p2[0], self.p2[1], tip_x, tip_y, self.color, self.width)

    def draw_tk(self, cv, ox, oy, zoom):
        items = super().draw_tk(cv, ox, oy, zoom)
        ang = math.atan2(self.p2[1] - self.p1[1], self.p2[0] - self.p1[0])
        head = 8 + self.width * 3.0
        spread = math.radians(25)
        for sign in (1, -1):
            a = ang + math.pi + sign * spread
            tip_x = self.p2[0] + head * math.cos(a)
            tip_y = self.p2[1] + head * math.sin(a)
            items.append(cv.create_line(ox + self.p2[0] * zoom,
                                        oy + self.p2[1] * zoom,
                                        ox + tip_x * zoom, oy + tip_y * zoom,
                                        fill=to_tk_color(self.color), width=self.width))
        return items


class PenShape(Shape):
    def __init__(self, color, width, points=None):
        self.color = color
        self.width = max(1, int(width))
        self.points = [tuple(p) for p in (points or [])]

    def add_point(self, p):
        self.points.append(tuple(p))

    def bounding(self):
        if not self.points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def move_by(self, dx, dy):
        self.points = [(x + dx, y + dy) for x, y in self.points]

    def draw_gdi(self, r, img):
        for (x1, y1), (x2, y2) in zip(self.points, self.points[1:]):
            r.line(x1, y1, x2, y2, self.color, self.width)

    def draw_tk(self, cv, ox, oy, zoom):
        if len(self.points) < 2:
            return []
        flat = []
        for x, y in self.points:
            flat += [ox + x * zoom, oy + y * zoom]
        return [cv.create_line(*flat, fill=to_tk_color(self.color), width=self.width,
                               smooth=True)]

    def resize_by_handle(self, index, pos):
        # 画笔不支持单点缩放（整段平移即可）
        pass


class StepShape(Shape):
    def __init__(self, color, width, center, number, diameter, font_size):
        self.color = color
        self.width = max(1, int(width))
        self.center = tuple(center)
        self.number = int(number)
        self.diameter = float(diameter)
        self.font_size = int(font_size)

    @property
    def radius(self):
        return self.diameter / 2.0

    def bounding(self):
        cx, cy = self.center
        return cx - self.radius, cy - self.radius, \
            cx + self.radius, cy + self.radius

    def contains(self, px, py, tol=6.0):
        cx, cy = self.center
        return math.hypot(px - cx, py - cy) <= self.radius + tol

    def move_by(self, dx, dy):
        cx, cy = self.center
        self.center = (cx + dx, cy + dy)

    def digit_size(self):
        return max(8, int(min(self.diameter * 0.62, self.font_size * 1.8)))

    def draw_gdi(self, r, img):
        cx, cy = self.center
        rr = self.radius
        r.ellipse(cx - rr, cy - rr, rr * 2, rr * 2, self.color, self.width,
                  fill=True)
        r.text_center(cx - rr, cy - rr, rr * 2, rr * 2, str(self.number),
                      (255, 255, 255), size_px=self.digit_size(), bold=True)

    def draw_tk(self, cv, ox, oy, zoom):
        cx, cy = self.center
        rr = self.radius
        x0 = ox + (cx - rr) * zoom
        y0 = oy + (cy - rr) * zoom
        x1 = ox + (cx + rr) * zoom
        y1 = oy + (cy + rr) * zoom
        items = [cv.create_oval(x0, y0, x1, y1, fill=to_tk_color(self.color),
                                outline="#ffffff", width=1.5)]
        items.append(cv.create_text(ox + cx * zoom, oy + cy * zoom,
                                    text=str(self.number), fill="#ffffff",
                                    font=("Microsoft YaHei UI",
                                          int(self.digit_size() * zoom / 1.2),
                                          "bold")))
        return items

    def resize_by_handle(self, index, pos):
        x0, y0, x1, y1 = self._scale_rect(index, pos)
        self.center = ((x0 + x1) / 2, (y0 + y1) / 2)
        self.diameter = max(16.0, max(x1 - x0, y1 - y0))


class TextShape(Shape):
    def __init__(self, color, width, pos, text, font_size):
        self.color = color
        self.width = max(1, int(width))
        self.pos = tuple(pos)
        self.text = text
        self.font_size = max(8, int(font_size))

    def bounding(self):
        # 估算：多行文本的包围盒
        lines = self.text.split("\n") or [""]
        w = max((len(s) for s in lines), default=0) * self.font_size * 0.62
        h = len(lines) * self.font_size * 1.25
        return self.pos[0], self.pos[1], self.pos[0] + w, self.pos[1] + h

    def move_by(self, dx, dy):
        self.pos = (self.pos[0] + dx, self.pos[1] + dy)

    def draw_gdi(self, r, img):
        lines = self.text.split("\n")
        line_h = self.font_size * 1.25
        # 白色描边提高可读性
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            for i, s in enumerate(lines):
                r.text(self.pos[0] + dx, self.pos[1] + i * line_h + dy, s,
                       (255, 255, 255), size_px=self.font_size, bold=True)
        for i, s in enumerate(lines):
            r.text(self.pos[0], self.pos[1] + i * line_h, s, self.color,
                   size_px=self.font_size, bold=True)

    def draw_tk(self, cv, ox, oy, zoom):
        lines = self.text.split("\n")
        line_h = self.font_size * 1.25
        fs = int(self.font_size * zoom / 1.2)
        items = []
        for i, s in enumerate(lines):
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                items.append(cv.create_text(
                    ox + self.pos[0] * zoom + dx,
                    oy + (self.pos[1] + i * line_h) * zoom + dy,
                    text=s, fill="#ffffff", anchor="nw",
                    font=("Microsoft YaHei UI", fs, "bold")))
        for i, s in enumerate(lines):
            items.append(cv.create_text(
                ox + self.pos[0] * zoom,
                oy + (self.pos[1] + i * line_h) * zoom,
                text=s, fill=to_tk_color(self.color), anchor="nw",
                font=("Microsoft YaHei UI", fs, "bold")))
        return items

    def resize_by_handle(self, index, pos):
        x0, y0, x1, y1 = self._scale_rect(index, pos)
        ratio = (y1 - y0) / max(1.0, self.font_size * 1.25 *
                                len(self.text.split("\n")))
        self.font_size = int(min(400, max(8, round(self.font_size * max(
            0.1, ratio)))))
        self.pos = (x0, y0)


class HighlightShape(Shape):
    def __init__(self, color, width, rect):
        self.color = color
        self.width = max(1, int(width))
        self.rect = tuple(rect)

    def bounding(self):
        x, y, w, h = self.rect
        return x, y, x + w, y + h

    def move_by(self, dx, dy):
        x, y, w, h = self.rect
        self.rect = (x + dx, y + dy, w, h)

    def draw_gdi(self, r, img):
        x, y, w, h = self.rect
        img.blend_rect(int(x), int(y), int(w), int(h), self.color, 0.42)

    def draw_tk(self, cv, ox, oy, zoom):
        x, y, w, h = self.rect
        return [cv.create_rectangle(ox + x * zoom, oy + y * zoom,
                                    ox + (x + w) * zoom, oy + (y + h) * zoom,
                                    fill=to_tk_color(self.color), stipple="gray50",
                                    outline="")]

    def resize_by_handle(self, index, pos):
        self.rect = self._scale_rect(index, pos)


class MosaicShape(Shape):
    def __init__(self, color, width, rect):
        self.color = color
        self.width = max(1, int(width))
        self.rect = tuple(rect)

    def bounding(self):
        x, y, w, h = self.rect
        return x, y, x + w, y + h

    def move_by(self, dx, dy):
        x, y, w, h = self.rect
        self.rect = (x + dx, y + dy, w, h)

    def draw_gdi(self, r, img):
        x, y, w, h = self.rect
        img.mosaic(int(x), int(y), int(w), int(h), 12)

    def draw_tk(self, cv, ox, oy, zoom):
        # 交互预览：画半透明图案即可（真正的马赛克在导出时做）
        x, y, w, h = self.rect
        return [cv.create_rectangle(ox + x * zoom, oy + y * zoom,
                                    ox + (x + w) * zoom, oy + (y + h) * zoom,
                                    fill="#7a828e", stipple="gray25",
                                    outline="")]

    def resize_by_handle(self, index, pos):
        self.rect = self._scale_rect(index, pos)
