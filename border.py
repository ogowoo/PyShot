# -*- coding: utf-8 -*-
"""border.py —— 加边框 / 边缘效果（对照 FastStone Capture 的「特效 → 边缘」）。

FSCapture 的边缘效果和「水印」在同一个菜单下，做法是**在图片四周加一圈**，
于是输出图会变大（不是画在图上）。这里照这个思路实现：

- `render_border(pixmap, settings)` 返回**加了边框后的新图**（尺寸更大）
- 编辑器里由 `Canvas.apply_border()` 调用，并把已有标注整体平移
- 提供对话框（样式 + 宽度 + 颜色 + 实时预览 + 用设为默认）

样式列表（FSCapture 的样式名各版本略有出入，这里给了一套常用的）：
    单线 / 双线 / 虚线 / 圆角 / 投影阴影 / 立体浮雕 / 边缘渐隐 / 拍立得白边
"""
import json
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout)

# (值, 显示名, 说明)
STYLES = [
    ("solid", "单线边框", "纯色边框，最简洁"),
    ("double", "双线边框", "外粗内细的双线"),
    ("dashed", "虚线边框", "虚线描边"),
    ("round", "圆角边框", "图片切圆角 + 描边"),
    ("shadow", "投影阴影", "四周柔和阴影（背景透明，适合贴到文档里）"),
    ("bevel", "立体浮雕", "左上亮、右下暗，做出凹凸感"),
    ("fade", "边缘渐隐", "图片四边渐隐到边框色"),
    ("polaroid", "拍立得白边", "下方留宽白边，像拍立得"),
]
STYLE_NAMES = {k: name for k, name, _ in STYLES}

BORDER_DEFAULTS = {
    "style": "shadow",
    "width": 16,             # 边框 / 阴影宽度（像素）
    "color": "#ffffff",      # 边框色 / 渐隐目标色
    "shadow_alpha": 110,     # 阴影浓度 0-255
    "shadow_spread": 0,      # 阴影额外扩散
    "radius": 16,            # 圆角半径
    "auto": False,           # 设为默认后新截图自动加边框
}

BORDER_CONFIG_PATH = Path.home() / ".pyshot" / "border.json"
_cache = {}


# ---------------------------------------------------------------- 设置

def normalize_border(settings: dict | None) -> dict:
    out = dict(BORDER_DEFAULTS)
    if settings:
        for k, v in settings.items():
            if k in BORDER_DEFAULTS:
                out[k] = v
    if out["style"] not in STYLE_NAMES:
        out["style"] = BORDER_DEFAULTS["style"]
    out["width"] = max(0, min(400, int(out["width"])))
    out["shadow_alpha"] = max(0, min(255, int(out["shadow_alpha"])))
    out["shadow_spread"] = max(0, min(200, int(out["shadow_spread"])))
    out["radius"] = max(0, min(400, int(out["radius"])))
    out["auto"] = bool(out["auto"])
    if not isinstance(out["color"], str):
        out["color"] = BORDER_DEFAULTS["color"]
    return out


def load_border_default() -> dict:
    global _cache
    if _cache:
        return dict(_cache)
    try:
        with open(BORDER_CONFIG_PATH, encoding="utf-8") as f:
            _cache = normalize_border(json.load(f))
    except Exception:                        # noqa: BLE001
        _cache = dict(BORDER_DEFAULTS)
    return dict(_cache)


def save_border_default(settings: dict) -> bool:
    global _cache
    _cache = normalize_border(settings)
    try:
        BORDER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BORDER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
        return True
    except Exception:                        # noqa: BLE001
        return False


def clear_border_cache():
    global _cache
    _cache = {}


def describe_border(settings: dict) -> str:
    s = normalize_border(settings)
    return f"{STYLE_NAMES[s['style']]} {s['width']}px"


# ---------------------------------------------------------------- 边距与绘制

def border_padding(settings: dict) -> tuple:
    """返回 (左, 上, 右, 下) 需要扩出去的像素。"""
    s = normalize_border(settings)
    w = s["width"]
    style = s["style"]
    if style == "shadow":
        extra = w + s["shadow_spread"]
        return extra, extra, extra, extra
    if style == "polaroid":
        return w, w, w, max(w * 3, 24)
    if w <= 0:
        return 0, 0, 0, 0
    return w, w, w, w


def _fill(painter, rect: QRectF, color: QColor):
    painter.fillRect(rect, color)


def _draw_shadow(painter, image_rect: QRectF, s: dict):
    """柔和阴影：从外向内叠一圈圈低透明度圆角矩形，靠重叠累积成渐变。

    每圈透明度都取一个小值（约 base 的 12%），越靠近图片被叠加的圈数越多，
    于是自然形成"贴边最暗、向外渐隐"的效果；比按圈递增透明度更均匀，
    也不会在中间出现明显色阶。
    """
    base = QColor(s["color"])
    steps = max(10, min(30, max(6, s["width"])))
    per = max(6, int(s["shadow_alpha"] * 0.12))
    painter.setPen(Qt.NoPen)
    for i in range(steps, 0, -1):
        k = i / steps
        c = QColor(base)
        c.setAlpha(per)
        grow_x = s["width"] * k + s["shadow_spread"] * k
        grow_y = s["width"] * k * 0.72 + s["shadow_spread"] * k
        r = image_rect.adjusted(-grow_x, -grow_y, grow_x, grow_y)
        radius = max(0.0, s["radius"] * k)
        painter.setBrush(c)
        radius = max(0.0, s["radius"] * k)
        painter.drawRoundedRect(r, radius, radius)


def render_border(pix: QPixmap, settings: dict) -> QPixmap:
    """在图片四周加边框，返回**更大的新图**。"""
    s = normalize_border(settings)
    left, top, right, bottom = border_padding(s)
    w = pix.width() + left + right
    h = pix.height() + top + bottom
    if w <= 0 or h <= 0 or (left + top + right + bottom) == 0:
        return QPixmap(pix)

    dpr = float(pix.devicePixelRatio() or 1.0)
    style = s["style"]
    color = QColor(s["color"])
    # 阴影与渐隐需要透明背景（贴到文档里才自然）
    transparent_bg = style in ("shadow", "fade")

    out = QPixmap(w, h)
    out.fill(Qt.transparent if transparent_bg else color)
    out.setDevicePixelRatio(dpr)

    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    img_rect = QRectF(left, top, pix.width(), pix.height())

    if style == "shadow":
        _draw_shadow(p, img_rect, s)
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
    elif style == "bevel":
        # 先画底色，再在图片外圈画亮/暗两条边
        p.fillRect(QRectF(0, 0, w, h), color)
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
        light = QColor(s["color"]).lighter(165)
        dark = QColor(s["color"]).darker(155)
        for i in range(max(1, s["width"] // 3)):
            inset = i
            p.setPen(QPen(light, 1))
            p.drawLine(QPointF(inset, h - inset),
                       QPointF(inset, inset))
            p.drawLine(QPointF(inset, inset), QPointF(w - inset, inset))
            p.setPen(QPen(dark, 1))
            p.drawLine(QPointF(w - 1 - inset, inset),
                       QPointF(w - 1 - inset, h - 1 - inset))
            p.drawLine(QPointF(w - 1 - inset, h - 1 - inset),
                       QPointF(inset, h - 1 - inset))
    elif style == "round":
        path = QPainterPath()
        path.addRoundedRect(img_rect, s["radius"], s["radius"])
        p.fillRect(QRectF(0, 0, w, h), color)
        p.save()
        p.setClipPath(path)
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
        p.restore()
        p.setPen(QPen(color.darker(140), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(img_rect, s["radius"], s["radius"])
    elif style == "double":
        p.fillRect(QRectF(0, 0, w, h), color)
        inner = QColor(s["color"]).darker(150)
        p.setPen(QPen(inner, max(1, s["width"] // 5)))
        inset = max(1.0, s["width"] * 0.32)
        p.setBrush(Qt.NoBrush)
        p.drawRect(img_rect.adjusted(-inset, -inset, inset, inset))
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
    elif style == "dashed":
        p.fillRect(QRectF(0, 0, w, h), color)
        p.setPen(QPen(QColor(s["color"]).darker(160), max(1, s["width"] // 4),
                      Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        inset = s["width"] / 2.0
        p.drawRect(QRectF(inset, inset, w - inset * 2, h - inset * 2))
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
    elif style == "fade":
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
        # 图片四边用边框色渐隐（内阴影式晕开）
        band = max(2.0, s["width"] * 0.8)
        c0 = QColor(color)
        c0.setAlpha(230)
        c1 = QColor(color)
        c1.setAlpha(0)
        edges = [
            (QRectF(left, top, pix.width(), band), (0, 1)),
            (QRectF(left, top + pix.height() - band, pix.width(), band),
             (0, -1)),
            (QRectF(left, top, band, pix.height()), (1, 0)),
            (QRectF(left + pix.width() - band, top, band, pix.height()),
             (-1, 0)),
        ]
        for rect, (dx, dy) in edges:
            if dy:
                g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                if dy > 0:
                    g.setColorAt(0.0, c0)
                    g.setColorAt(1.0, c1)
                else:
                    g.setColorAt(0.0, c1)
                    g.setColorAt(1.0, c0)
            else:
                g = QLinearGradient(rect.topLeft(), rect.topRight())
                if dx > 0:
                    g.setColorAt(0.0, c0)
                    g.setColorAt(1.0, c1)
                else:
                    g.setColorAt(0.0, c1)
                    g.setColorAt(1.0, c0)
            p.fillRect(rect, g)
    elif style == "polaroid":
        p.fillRect(QRectF(0, 0, w, h), color)
        # 图片下方留白处画一条淡淡的分隔阴影，像相纸压痕
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))
        p.setPen(QPen(QColor(0, 0, 0, 28), 1))
        p.drawLine(QPointF(left, top + pix.height() + 0.5),
                   QPointF(left + pix.width(), top + pix.height() + 0.5))
    else:                                    # solid 及其它
        p.fillRect(QRectF(0, 0, w, h), color)
        p.drawPixmap(img_rect, pix, QRectF(pix.rect()))

    p.end()
    return out


# ---------------------------------------------------------------- 对话框

class BorderDialog(QDialog):
    """边框对话框（样式 + 宽度 + 颜色 + 实时预览）。"""

    PREVIEW_MAX = QSize(430, 170)

    def __init__(self, parent=None, settings: dict | None = None,
                 image_size: QSize | None = None):
        super().__init__(parent)
        self.setWindowTitle("边框 / 边缘效果")
        self.setMinimumWidth(520)
        self._s = normalize_border(settings or load_border_default())
        self._image_size = image_size if (image_size and image_size.isValid()) \
            else QSize(640, 400)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.style = QComboBox()
        for key, name, tip in STYLES:
            self.style.addItem(name, key)
            self.style.setItemData(self.style.count() - 1, tip, Qt.ToolTipRole)
        idx = [k for k, _, _ in STYLES].index(self._s["style"])
        self.style.setCurrentIndex(idx)
        self.style.currentIndexChanged.connect(self._on_style)
        form.addRow("样式", self.style)

        row = QHBoxLayout()
        self.width = QSpinBox()
        self.width.setRange(0, 400)
        self.width.setSuffix(" px")
        self.width.setValue(self._s["width"])
        self.width.valueChanged.connect(self._on_width)
        row.addWidget(self.width)
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(52, 26)
        self.color_btn.clicked.connect(self._pick_color)
        row.addWidget(QLabel("颜色"))
        row.addWidget(self.color_btn)
        row.addStretch(1)
        form.addRow("宽度", row)

        row2 = QHBoxLayout()
        self.radius = QSpinBox()
        self.radius.setRange(0, 400)
        self.radius.setSuffix(" px")
        self.radius.setValue(self._s["radius"])
        self.radius.valueChanged.connect(self._on_radius)
        self.radius_label = QLabel("圆角")
        row2.addWidget(self.radius_label)
        row2.addWidget(self.radius)

        self.alpha = QSlider(Qt.Horizontal)
        self.alpha.setRange(0, 100)
        self.alpha.setValue(int(round(self._s["shadow_alpha"] * 100 / 255)))
        self.alpha.valueChanged.connect(self._on_alpha)
        self.alpha.valueChanged.connect(
            lambda v: self.alpha_label.setText(f"{v}%"))
        self.alpha_label = QLabel(f"{int(round(self._s['shadow_alpha'] * 100 / 255))}%")
        self.alpha_label.setMinimumWidth(40)
        self.alpha_text = QLabel("阴影浓度")
        row2.addWidget(self.alpha_text)
        row2.addWidget(self.alpha, 1)
        row2.addWidget(self.alpha_label)
        row2.addStretch(1)
        form.addRow("细节", row2)
        root.addLayout(form)

        prev = QGroupBox("预览")
        pl = QVBoxLayout(prev)
        self.preview = QLabel()
        self.preview.setFixedSize(self.PREVIEW_MAX)
        self.preview.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.preview)
        root.addWidget(prev)

        self.note = QLabel()
        self.note.setStyleSheet("color:#9aa0ab;")
        root.addWidget(self.note)

        buttons = QDialogButtonBox()
        self.btn_apply = buttons.addButton("应用", QDialogButtonBox.AcceptRole)
        self.btn_default = buttons.addButton("应用并设为默认",
                                             QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.btn_apply.clicked.connect(self._accept_apply)
        self.btn_default.clicked.connect(self._accept_default)
        root.addWidget(buttons)

        self._update_color_button()
        self._on_style()
        self._refresh_preview()

    # ---------- 交互 ----------
    def _on_style(self, *args):
        key = self.style.currentData()
        self._s["style"] = key
        # 每种样式只显示相关参数
        show_radius = key in ("shadow", "round")
        show_alpha = key == "shadow"
        self.radius.setVisible(show_radius)
        self.radius_label.setVisible(show_radius)
        self.alpha.setVisible(show_alpha)
        self.alpha_label.setVisible(show_alpha)
        self.alpha_text.setVisible(show_alpha)
        tips = {k: t for k, _, t in STYLES}
        self.note.setText(tips.get(key, ""))
        self._refresh_preview()

    def _on_width(self, v):
        self._s["width"] = v
        self._refresh_preview()

    def _on_radius(self, v):
        self._s["radius"] = v
        self._refresh_preview()

    def _on_alpha(self, v):
        self._s["shadow_alpha"] = int(round(v * 255 / 100))
        self._refresh_preview()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._s["color"]), self, "边框颜色")
        if c.isValid():
            self._s["color"] = c.name()
            self._update_color_button()
            self._refresh_preview()

    def _update_color_button(self):
        self.color_btn.setStyleSheet(
            f"background:{self._s['color']};"
            "border:1px solid #3a3e47;border-radius:4px;")

    # ---------- 预览 ----------
    def _sample(self) -> QPixmap:
        """造一张"截图"样张（用真实比例，但缩小到预览框内）。"""
        w = min(self._image_size.width(), 300)
        h = int(w * self._image_size.height()
                / max(1, self._image_size.width()))
        pix = QPixmap(w, h)
        p = QPainter(pix)
        p.fillRect(0, 0, w, h, QColor("#f4f6f9"))
        p.setPen(QColor("#c9cdd4"))
        for y in range(18, h, 22):
            p.drawLine(12, y, w - 12, y)
        p.fillRect(10, 8, max(20, w // 4), 5, QColor("#8890a0"))
        p.end()
        return pix

    def _refresh_preview(self, *args):
        if not hasattr(self, "preview"):
            return
        framed = render_border(self._sample(), self._s)
        if framed.width() > self.PREVIEW_MAX.width() \
                or framed.height() > self.PREVIEW_MAX.height():
            framed = framed.scaled(self.PREVIEW_MAX, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        # 放在棋盘格底上，透明背景的阴影样式才看得出来
        canvas = QPixmap(self.PREVIEW_MAX)
        canvas.fill(QColor("#1f2126"))
        cp = QPainter(canvas)
        for y in range(0, self.PREVIEW_MAX.height(), 12):
            for x in range(0, self.PREVIEW_MAX.width(), 12):
                if (x // 12 + y // 12) % 2 == 0:
                    cp.fillRect(x, y, 12, 12, QColor("#26292f"))
        cp.drawPixmap(
            (self.PREVIEW_MAX.width() - framed.width()) // 2,
            (self.PREVIEW_MAX.height() - framed.height()) // 2, framed)
        cp.end()
        self.preview.setPixmap(canvas)

    # ---------- 结果 ----------
    def settings(self) -> dict:
        self._s["style"] = self.style.currentData()
        self._s["width"] = self.width.value()
        self._s["radius"] = self.radius.value()
        self._s["shadow_alpha"] = int(round(self.alpha.value() * 255 / 100))
        return normalize_border(self._s)

    def _accept_apply(self):
        self._save_as_default = False
        self.accept()

    def _accept_default(self):
        self._save_as_default = True
        self.accept()

    def save_as_default(self) -> bool:
        return bool(getattr(self, "_save_as_default", False))
