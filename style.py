# -*- coding: utf-8 -*-
"""现代化深色主题：全局 QSS + 自绘矢量工具图标。"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtCore import QRectF
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap)

ACCENT = "#4c9aff"
ACCENT_HOVER = "#66adff"
ACCENT_ACTIVE = "#2f7fe0"
ACCENT_SOFT = "rgba(76, 154, 255, 0.16)"
DANGER = "#ff5c5c"

BG = "#17181c"            # 窗口底色（接近黑）
SURFACE = "#1f2126"       # 面板/工具栏
SURFACE_2 = "#26292f"     # 浮起的控件
BORDER = "#2c2f36"        # 细分隔线
BORDER_STRONG = "#3a3e47" # 需要强调的分隔
TEXT = "#e6e8ec"
TEXT_DIM = "#a2a8b2"

RADIUS = 8
RADIUS_LG = 10

import os as _os
from pathlib import Path as _Path

from PySide6.QtWidgets import (QSpinBox as _QSpinBox, QStyle,
                               QStyleOptionSpinBox)


class SpinBox(_QSpinBox):
    """深色主题的 SpinBox：自己画上/下箭头。

    Qt 的 QSS 在自定义 ::up-button 后就不再画箭头（实测无论调色板还是
    image: 都不可靠），所以这里在 paintEvent 里直接画两个小三角，
    任何主题下都保证可见。
    """

    def paintEvent(self, e):
        super().paintEvent(e)
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        style = self.style()
        color = self.palette().color(QPalette.ButtonText)
        if not self.isEnabled():
            color = self.palette().color(QPalette.Disabled, QPalette.ButtonText)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for sc, up in ((QStyle.SC_SpinBoxUp, True), (QStyle.SC_SpinBoxDown, False)):
            rect = style.subControlRect(QStyle.CC_SpinBox, opt, sc, self)
            if rect.isNull():
                continue
            cx, cy = rect.center().x(), rect.center().y()
            s = max(2.5, min(rect.width(), rect.height()) * 0.30)
            pts = [(cx, cy - s), (cx + s, cy + s), (cx - s, cy + s)] if up else \
                  [(cx, cy + s), (cx + s, cy - s), (cx - s, cy - s)]
            path = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
            p.drawPath(path)
        p.end()


def apply_theme(app):
    """先铺一套深色 QPalette（Fusion 的很多细节——下拉箭头、复选框勾、
    禁用文字、数字框箭头——都靠调色板画），再叠加 QSS 精修。"""
    app.setStyle("Fusion")
    pal = QPalette()
    base = QColor(BG)
    panel = QColor(SURFACE)
    text = QColor(TEXT)
    dim = QColor(TEXT_DIM)
    accent = QColor(ACCENT)
    pal.setColor(QPalette.Window, panel)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, panel)
    pal.setColor(QPalette.ToolTipBase, panel)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, panel)
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.BrightText, QColor("#ff5555"))
    pal.setColor(QPalette.Highlight, accent)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, accent)
    pal.setColor(QPalette.LinkVisited, QColor("#8e24aa"))
    pal.setColor(QPalette.PlaceholderText, QColor("#6b7079"))
    # 禁用态
    disabled = QColor("#5a5e66")
    pal.setColor(QPalette.Disabled, QPalette.Text, disabled)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    pal.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#2a2d33"))
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor("#8a8f98"))
    app.setPalette(pal)
    app.setStyleSheet(APP_QSS)

APP_QSS = f"""
/* ============ PyShot 设计系统 ============ */
* {{ font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG}; color: {TEXT}; }}

/* ---------- 顶栏（流式布局，窗口变窄自动换行） ---------- */
QWidget#topbar {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QWidget#topbar QLabel {{ color: {TEXT_DIM}; padding: 0 2px; }}
QWidget#topbar QToolButton#topbtn {{
    background: transparent; border: none; border-radius: {RADIUS}px;
    padding: 6px 12px; color: {TEXT};
}}
QWidget#topbar QToolButton#topbtn:hover {{ background: {SURFACE_2}; }}
QWidget#topbar QToolButton#topbtn:pressed {{ background: {BORDER_STRONG}; }}
QWidget#topbar QToolButton#topbtn:disabled {{ color: #596069; }}
QPushButton#primarybtn {{
    background: {ACCENT}; color: #ffffff; font-weight: 600;
    border: none; border-radius: {RADIUS}px; padding: 6px 14px;
}}
QPushButton#primarybtn:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primarybtn:pressed {{ background: {ACCENT_ACTIVE}; }}

/* ---------- 左侧工具轨道（工具分组，细线分隔） ---------- */
QFrame#sidebar {{
    background: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
}}
QToolButton#toolbtn {{
    background: transparent; border: none; border-radius: {RADIUS}px;
    padding: 8px;
}}
QToolButton#toolbtn:hover {{ background: {SURFACE_2}; }}
QToolButton#toolbtn:checked {{
    background: {ACCENT_SOFT};
    border: none;
    border-left: 3px solid {ACCENT};
    border-radius: 4px {RADIUS}px {RADIUS}px 4px;
}}
QFrame#railsep {{ background: {BORDER}; max-height: 1px; margin: 4px 10px; border: none; }}

QFrame#topsep {{ background: {BORDER_STRONG}; max-width: 1px; margin: 4px 4px; border: none; }}

/* ---------- 圆形色板 ---------- */
QPushButton#swatch {{ border-radius: 11px; border: 2px solid rgba(0,0,0,0); }}
QPushButton#swatch:hover {{ border: 2px solid {TEXT_DIM}; }}
QPushButton#swatch[selected="true"] {{ border: 2px solid #ffffff; }}
QPushButton#swatchMore {{
    background: {SURFACE_2}; color: {TEXT}; border-radius: 11px; border: none;
}}
QPushButton#swatchMore:hover {{ background: {BORDER_STRONG}; }}

/* ---------- 数字输入框 ---------- */
QSpinBox {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: {RADIUS - 2}px;
    padding: 4px 6px;
}}
QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 16px; background: transparent; border: none;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {BORDER_STRONG}; }}

/* ---------- 画布滚动区 ---------- */
QScrollArea {{ background: {BG}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a5059; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #4a5059; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- 画布标签页（下划线指示，现代风） ---------- */
QTabWidget#canvasTabs::pane {{ border: none; background: {BG}; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabWidget#canvasTabs > QTabBar {{ background: {SURFACE}; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_DIM};
    padding: 8px 6px 9px 14px; margin: 0 2px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QToolButton#tabclose {{
    background: transparent; border: none; border-radius: 4px;
    color: {TEXT_DIM}; font-size: 11px; padding: 1px 4px;
}}
QToolButton#tabclose:hover {{ background: {SURFACE_2}; color: #ffffff; }}
QLabel#sizelabel {{ color: {TEXT_DIM}; padding-right: 6px; }}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background: {SURFACE}; color: {TEXT_DIM};
    border-top: 1px solid {BORDER}; min-height: 30px;
}}
QStatusBar::item {{ border: none; }}
QLabel#toolname {{ color: {TEXT_DIM}; padding-left: 6px; }}

/* ---------- 状态栏右侧缩放胶囊 ---------- */
QWidget#zoomgroup {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
}}
QPushButton#zoombtn {{
    background: transparent; border: none; border-radius: 5px;
    color: {TEXT}; font-size: 14px; font-weight: 600; padding: 0;
}}
QPushButton#zoombtn:hover {{ background: {BORDER_STRONG}; }}
QPushButton#zoombtn:pressed {{ background: {ACCENT_SOFT}; }}
QLabel#zoomlabel {{ color: #ffffff; font-weight: 700; font-size: 13px; padding: 0 2px; }}
QFrame#zoomsep {{ color: {BORDER_STRONG}; background: {BORDER_STRONG};
    max-width: 1px; margin: 5px 4px; border: none; }}

/* ---------- 菜单 / 提示 / 通用控件 ---------- */
QMenu {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_LG}px; padding: 5px;
}}
QMenu::item {{ padding: 7px 28px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 10px; }}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 5px 8px;
}}
QLineEdit, QPlainTextEdit, QComboBox, QSlider::groove:horizontal {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: {RADIUS - 2}px;
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QFileDialog QListView, QFileDialog QTreeView {{
    background: {BG}; color: {TEXT}; border: 1px solid {BORDER};
}}
QPushButton {{
    background: {SURFACE_2}; color: {TEXT};
    border: none; border-radius: {RADIUS}px; padding: 7px 16px;
}}
QPushButton:hover {{ background: {BORDER_STRONG}; }}
QPushButton:default {{ background: {ACCENT}; color: white; }}
QColorDialog {{ background: {BG}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HOVER}; }}
"""


# ---------------------------------------------------------------- 工具图标

def _icon_pixmap(draw_fn, color: QColor, size=24, dpr=2) -> QPixmap:
    pix = QPixmap(size * dpr, size * dpr)
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    draw_fn(p, color)
    p.end()
    return pix


def _draw_select(p, c):
    path = QPainterPath(QPointF(7, 3.5))
    for pt in [(7, 18.5), (10.8, 15), (13, 20.5), (15.6, 19.2), (13.4, 13.8), (18.5, 13.8)]:
        path.lineTo(*pt)
    path.closeSubpath()
    p.setBrush(c)
    p.drawPath(path)


def _draw_rect(p, c):
    p.drawRoundedRect(4.5, 6.5, 15, 11, 1.5, 1.5)


def _draw_ellipse(p, c):
    p.drawEllipse(4.5, 6.5, 15, 11)


def _draw_line(p, c):
    p.drawLine(QPointF(5, 19), QPointF(19, 5))


def _draw_arrow(p, c):
    p.drawLine(QPointF(4.5, 19.5), QPointF(17, 7))
    p.drawLine(QPointF(17, 7), QPointF(10.5, 7.8))
    p.drawLine(QPointF(17, 7), QPointF(16.2, 13.5))


def _draw_pen(p, c):
    path = QPainterPath(QPointF(4, 19))
    path.cubicTo(QPointF(8, 10), QPointF(10, 15), QPointF(13, 11))
    path.cubicTo(QPointF(15, 8.5), QPointF(17, 8), QPointF(20, 5))
    p.drawPath(path)


def _draw_step(p, c):
    p.drawEllipse(4, 4, 16, 16)
    f = QFont("Segoe UI")
    f.setPixelSize(12)
    f.setBold(True)
    p.setFont(f)
    p.drawText(4, 4, 16, 16, Qt.AlignCenter, "1")


def _draw_text(p, c):
    f = QFont("Segoe UI")
    f.setPixelSize(17)
    f.setBold(True)
    p.setFont(f)
    p.drawText(4, 3, 16, 19, Qt.AlignCenter, "T")


def _draw_highlight(p, c):
    fill = QColor(c)
    fill.setAlpha(90)
    p.setPen(Qt.NoPen)
    p.setBrush(fill)
    p.drawRoundedRect(4, 9, 16, 7, 2, 2)
    p.setPen(QPen(c, 2.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(4, 16.5), QPointF(20, 16.5))


def _draw_mosaic(p, c):
    s = 4.6
    for i in range(3):
        for j in range(3):
            if (i + j) % 2 == 0:
                p.fillRect(4.2 + j * (s + 0.8), 4.2 + i * (s + 0.8), s, s, c)


def _draw_pick(p, c):
    # 滴管：斜杆 + 顶部菱形
    p.drawLine(QPointF(5.5, 18.5), QPointF(13.5, 10.5))
    path = QPainterPath(QPointF(15.5, 4))
    for pt in [(20, 8.5), (15.5, 13), (11, 8.5)]:
        path.lineTo(*pt)
    path.closeSubpath()
    p.drawPath(path)
    p.setBrush(c)
    p.drawEllipse(QPointF(5, 20), 1.8, 1.8)


def _draw_crop(p, c):
    for x1, y1, x2, y2, x3, y3 in [
            (5, 10, 5, 5, 10, 5), (14, 5, 19, 5, 19, 10),
            (19, 14, 19, 19, 14, 19), (10, 19, 5, 19, 5, 14)]:
        path = QPainterPath(QPointF(x1, y1))
        path.lineTo(x2, y2)
        path.lineTo(x3, y3)
        p.drawPath(path)


def _draw_camera(p, c):
    """相机图标（顶栏"截图"按钮用）。"""
    p.drawRoundedRect(3.5, 7.5, 17, 12, 2, 2)
    p.drawLine(QPointF(9, 7.5), QPointF(10.5, 5))
    p.drawLine(QPointF(10.5, 5), QPointF(13.5, 5))
    p.drawLine(QPointF(13.5, 5), QPointF(15, 7.5))
    p.drawEllipse(QPointF(12, 13.5), 3.4, 3.4)


# ---- 托盘菜单图标 ----

def _draw_monitor(p, c):
    """显示器：屏幕 + 底座。"""
    p.drawRoundedRect(3, 5, 18, 12, 2, 2)
    p.drawLine(QPointF(12, 17), QPointF(12, 20))
    p.drawLine(QPointF(8, 20), QPointF(16, 20))


def _draw_scroll(p, c):
    """滚动长截图：向下的箭头 + 两横线。"""
    p.drawLine(QPointF(12, 3.5), QPointF(12, 14))
    p.drawLine(QPointF(12, 14), QPointF(8, 10))
    p.drawLine(QPointF(12, 14), QPointF(16, 10))
    p.drawLine(QPointF(5, 18), QPointF(19, 18))
    p.drawLine(QPointF(5, 21), QPointF(19, 21))


def _draw_image(p, c):
    """图片：相框 + 山形。"""
    p.drawRoundedRect(3.5, 5, 17, 14, 2, 2)
    p.drawEllipse(QPointF(8, 9.5), 1.6, 1.6)
    p.drawLine(QPointF(5, 17), QPointF(10.5, 11.5))
    p.drawLine(QPointF(10.5, 11.5), QPointF(14, 15))
    p.drawLine(QPointF(14, 15), QPointF(16.5, 12.5))
    p.drawLine(QPointF(16.5, 12.5), QPointF(20, 17))


def _draw_window(p, c):
    """窗口/编辑器：标题栏 + 内容。"""
    p.drawRoundedRect(3.5, 4.5, 17, 15, 2, 2)
    p.drawLine(QPointF(3.5, 9), QPointF(20.5, 9))
    p.drawLine(QPointF(6, 6.8), QPointF(6.2, 6.8))
    p.drawLine(QPointF(9, 6.8), QPointF(9.2, 6.8))


def _draw_pin(p, c):
    """图钉：贴图用。"""
    p.drawLine(QPointF(12, 12), QPointF(12, 20))
    path = QPainterPath(QPointF(7, 11))
    path.lineTo(17, 11)
    path.lineTo(14.5, 5)
    path.lineTo(9.5, 5)
    path.closeSubpath()
    p.drawPath(path)


def _draw_exit(p, c):
    """退出：电源符号。"""
    path = QPainterPath(QPointF(7, 5.5))
    path.cubicTo(QPointF(2.5, 9), QPointF(4, 19), QPointF(12, 19))
    path.cubicTo(QPointF(20, 19), QPointF(21.5, 9), QPointF(17, 5.5))
    p.drawPath(path)
    p.drawLine(QPointF(12, 3), QPointF(12, 10))


def _draw_undo(p, c):
    """撤销：左向弧线箭头。"""
    path = QPainterPath(QPointF(5, 9))
    path.cubicTo(QPointF(11, 4), QPointF(19, 6), QPointF(19, 13))
    path.cubicTo(QPointF(19, 18), QPointF(14, 20), QPointF(9, 19))
    p.drawPath(path)
    p.drawLine(QPointF(5, 9), QPointF(5, 4))
    p.drawLine(QPointF(5, 9), QPointF(10, 9))


def _draw_redo(p, c):
    """重做：右向弧线箭头（撤销的镜像）。"""
    path = QPainterPath(QPointF(19, 9))
    path.cubicTo(QPointF(13, 4), QPointF(5, 6), QPointF(5, 13))
    path.cubicTo(QPointF(5, 18), QPointF(10, 20), QPointF(15, 19))
    p.drawPath(path)
    p.drawLine(QPointF(19, 9), QPointF(19, 4))
    p.drawLine(QPointF(19, 9), QPointF(14, 9))


def _draw_globe(p, c):
    """地球（语言切换菜单用）。"""
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawEllipse(QPointF(12, 12), 3.8, 8.5)          # 经线
    p.drawLine(QPointF(3.5, 12), QPointF(20.5, 12))   # 赤道
    p.drawArc(QRectF(3.5, 6.5, 17, 11), 0, 180 * 16)


_ICON_DRAWERS = {
    "select": _draw_select, "rect": _draw_rect, "ellipse": _draw_ellipse,
    "line": _draw_line, "arrow": _draw_arrow, "pen": _draw_pen,
    "step": _draw_step, "text": _draw_text, "highlight": _draw_highlight,
    "mosaic": _draw_mosaic, "pick": _draw_pick, "crop": _draw_crop,
    "camera": _draw_camera, "undo": _draw_undo, "redo": _draw_redo,
    "monitor": _draw_monitor, "scroll": _draw_scroll, "image": _draw_image,
    "window": _draw_window, "pin": _draw_pin, "exit": _draw_exit,
    "globe": _draw_globe,
}


def make_menu_icon(name: str) -> QIcon:
    """托盘/菜单项图标（浅灰，深色菜单上清晰）。"""
    return make_icon(name, off_color="#c8ccd4", on_color="#ffffff")


def make_icon(name: str, off_color: str = "#b8c0cc",
              on_color: str = "#ffffff") -> QIcon:
    """生成双色态图标：普通=浅灰，选中/悬停=白色。"""
    icon = QIcon()
    fn = _ICON_DRAWERS[name]
    icon.addPixmap(_icon_pixmap(fn, QColor(off_color)), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_icon_pixmap(fn, QColor(on_color)), QIcon.Normal, QIcon.On)
    icon.addPixmap(_icon_pixmap(fn, QColor(on_color)), QIcon.Active, QIcon.Off)
    return icon


def make_tool_icon(tool_id: str) -> QIcon:
    """工具图标：未选中=浅灰，选中/悬停=强调色（配合柔和的选中底色）。"""
    return make_icon(tool_id, off_color="#9aa3af", on_color=ACCENT)
