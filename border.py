# -*- coding: utf-8 -*-
"""border.py —— 加边框 / 边缘效果（对照 FastStone Capture 的「特效 → 边缘」）。

FSCapture 的边缘效果和「水印」在同一个菜单下，做法是**在图片四周加一圈**，
于是输出图会变大（不是画在图上）。这里照这个思路实现：

- `render_border(pixmap, settings)` 返回**加了边框后的新图**（尺寸更大）
- 编辑器里由 `Canvas.apply_border()` 调用，并把已有标注整体平移
- 提供对话框（样式 + 宽度 + 颜色 + 实时预览 + 用设为默认）

样式列表（FSCapture 的样式名各版本略有出入，这里给了一套常用的）：
    单线 / 双线 / 虚线 / 圆角 / 投影阴影 / 立体浮雕 / 边缘渐隐 / 拍立得白边 / 手撕纸
"""
import json
import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout)
from i18n import tr

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
    ("torn", "手撕纸", "图片贴在一张撕下来的纸上，边缘不规则 + 投影"),
]
STYLE_NAMES = {k: name for k, name, _ in STYLES}

BORDER_DEFAULTS = {
    "style": "shadow",
    "width": 16,             # 边框 / 阴影宽度（像素）
    "color": "#ffffff",      # 边框色 / 渐隐目标色 / 纸张色
    "shadow_alpha": 110,     # 阴影浓度 0-255
    "shadow_spread": 0,      # 阴影额外扩散
    "radius": 16,            # 圆角半径
    "tear": 9,               # 手撕纸：撕边起伏幅度（像素）
    "seed": 7,               # 手撕纸：随机种子（同一种子撕法一致，预览=成品）
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
    # 撕边幅度不能超过纸边宽度，否则锯齿会超出画布
    out["tear"] = max(0, min(int(out["tear"]), out["width"] or 1, 200))
    out["seed"] = int(out["seed"]) % 100000
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
    if style == "torn":
        # 纸边 = width，撕边在此基础上上下起伏 tear，所以要再多留 tear
        extra = w + s["tear"]
        return extra, extra, extra, extra
    if w <= 0:
        return 0, 0, 0, 0
    return w, w, w, w


# ---------------------------------------------------------------- 手撕纸

def _torn_outline(rect: QRectF, tear: float, seed: int, step: float = 0.0):
    """围绕 rect 生成一圈**不规则撕边**的采样点（确定性随机）。

    整圈一次性做带惯性的随机游走（不是按边分段），所以撕痕会自然地绕过四角，
    不会在角上被"掐尖"；偶尔来一道更深的撕裂，像真的撕过头。
    """
    rnd = random.Random(seed)
    if step <= 0:
        step = max(3.0, tear * 0.75)

    # 1) 沿周长按顺序采样整圈：位置 + 指向纸外的法线
    ring = []

    def seg(x0, y0, x1, y1, nx, ny):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(length / step))
        for i in range(n):
            t = i / n
            ring.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, nx, ny))

    seg(rect.left(), rect.top(), rect.right(), rect.top(), 0, -1)
    seg(rect.right(), rect.top(), rect.right(), rect.bottom(), 1, 0)
    seg(rect.right(), rect.bottom(), rect.left(), rect.bottom(), 0, 1)
    seg(rect.left(), rect.bottom(), rect.left(), rect.top(), -1, 0)
    if not ring:
        return []

    # 2) 沿整圈做连续随机游走（惯性能让相邻点相关，形成连续撕痕）
    offs = []
    off = 0.0
    for _ in ring:
        off = off * 0.72 + rnd.uniform(-1.0, 1.0) * tear * 0.55
        if rnd.random() < 0.10:                 # 偶尔一道深撕
            off -= tear * rnd.uniform(0.4, 1.1)
        offs.append(max(-tear, min(tear, off)))
    # 首尾相接处取平均，消除闭合时的台阶
    offs[0] = offs[-1] = (offs[0] + offs[-1]) / 2.0

    return [(x + nx * o, y + ny * o)
            for (x, y, nx, ny), o in zip(ring, offs)]


def _torn_path(rect: QRectF, tear: float, seed: int) -> QPainterPath:
    pts = _torn_outline(rect, tear, seed)
    if not pts:
        path = QPainterPath()
        path.addRect(rect)
        return path
    # 用折线而不是曲线：撕纸的断口本来就该是硬边
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def _draw_torn(painter: QPainter, pix: QPixmap, out_h: int, img_rect: QRectF,
               s: dict):
    """画"贴在一张撕下来的纸上"的效果：投影 → 纸面 → 撕边描边 → 纤维 → 图片。"""
    tear = float(s["tear"])
    paper = QColor(s["color"])
    seed = int(s["seed"])

    # 纸的"标称外沿"：距图片 width，撕边在 ±tear 起伏
    nominal = img_rect.adjusted(-s["width"], -s["width"],
                                s["width"], s["width"])
    pts = _torn_outline(nominal, tear, seed)
    path = _torn_path(nominal, tear, seed)

    # 1) 投影：同一路径多次小偏移叠加，得到柔和阴影
    shade = max(10, s["shadow_alpha"] // 4)
    for i in (4, 3, 2, 1):
        painter.save()
        painter.translate(i * 0.9, i * 1.1)
        painter.fillPath(path, QColor(0, 0, 0, shade))
        painter.restore()

    # 2) 纸面（带极淡的纵向渐变，像纸张受光）
    grad = QLinearGradient(0, 0, 0, out_h)
    grad.setColorAt(0.0, paper.lighter(103))
    grad.setColorAt(1.0, paper.darker(104))
    painter.fillPath(path, QBrush(grad))

    # 3) 撕边描一条极淡的灰线，纸才有厚度感
    painter.setPen(QPen(QColor(0, 0, 0, 34), 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    # 4) 断口纤维：沿撕边取点，画 1px 短须
    rnd = random.Random(seed + 991)
    painter.setPen(QPen(QColor(0, 0, 0, 26), 1))
    for _ in range(max(12, int(len(pts) * 0.5))):
        px, py = pts[rnd.randrange(len(pts))]
        painter.drawLine(QPointF(px, py),
                         QPointF(px + rnd.uniform(-1.4, 1.4),
                                 py + rnd.uniform(-1.4, 1.4)))

    # 5) 图片本体
    painter.drawPixmap(img_rect, pix, QRectF(pix.rect()))


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
    # 阴影 / 渐隐 / 手撕纸需要透明背景（贴到文档里才自然）
    transparent_bg = style in ("shadow", "fade", "torn")

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
    elif style == "torn":
        _draw_torn(p, pix, h, img_rect, s)
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
        self.setWindowTitle(tr("边框 / 边缘效果"))
        self.setMinimumWidth(520)
        self._s = normalize_border(settings or load_border_default())
        self._image_size = image_size if (image_size and image_size.isValid()) \
            else QSize(640, 400)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.style = QComboBox()
        for key, name, tip in STYLES:
            self.style.addItem(tr(name), key)
            self.style.setItemData(self.style.count() - 1, tr(tip), Qt.ToolTipRole)
        idx = [k for k, _, _ in STYLES].index(self._s["style"])
        self.style.setCurrentIndex(idx)
        self.style.currentIndexChanged.connect(self._on_style)
        form.addRow(tr("样式"), self.style)

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
        row.addWidget(QLabel(tr("颜色")))
        row.addWidget(self.color_btn)
        row.addStretch(1)
        form.addRow(tr("宽度"), row)

        row2 = QHBoxLayout()
        self.radius = QSpinBox()
        self.radius.setRange(0, 400)
        self.radius.setSuffix(" px")
        self.radius.setValue(self._s["radius"])
        self.radius.valueChanged.connect(self._on_radius)
        self.radius_label = QLabel(tr("圆角"))
        row2.addWidget(self.radius_label)
        row2.addWidget(self.radius)

        # 手撕纸专用：撕边幅度 + 换一个撕法
        self.tear_label = QLabel(tr("撕边"))
        self.tear = QSpinBox()
        self.tear.setRange(0, 200)
        self.tear.setSuffix(" px")
        self.tear.setToolTip(tr("撕口的起伏幅度；不能超过纸边宽度"))
        self.tear.setValue(self._s["tear"])
        self.tear.valueChanged.connect(self._on_tear)
        self.reseed = QPushButton(tr("换一个撕法"))
        self.reseed.setToolTip(tr("重新随机撕口（同一个种子预览和成品一致）"))
        self.reseed.clicked.connect(self._on_reseed)
        row2.addWidget(self.tear_label)
        row2.addWidget(self.tear)
        row2.addWidget(self.reseed)

        self.alpha = QSlider(Qt.Horizontal)
        self.alpha.setRange(0, 100)
        self.alpha.setValue(int(round(self._s["shadow_alpha"] * 100 / 255)))
        self.alpha.valueChanged.connect(self._on_alpha)
        self.alpha.valueChanged.connect(
            lambda v: self.alpha_label.setText(f"{v}%"))
        self.alpha_label = QLabel(f"{int(round(self._s['shadow_alpha'] * 100 / 255))}%")
        self.alpha_label.setMinimumWidth(40)
        self.alpha_text = QLabel(tr("阴影浓度"))
        row2.addWidget(self.alpha_text)
        row2.addWidget(self.alpha, 1)
        row2.addWidget(self.alpha_label)
        row2.addStretch(1)
        form.addRow(tr("细节"), row2)
        root.addLayout(form)

        prev = QGroupBox(tr("预览"))
        pl = QVBoxLayout(prev)
        self.preview = QLabel()
        self.preview.setFixedSize(self.PREVIEW_MAX)
        self.preview.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.preview)
        root.addWidget(prev)

        self.note = QLabel()
        self.note.setStyleSheet("color:#9aa0ab;")
        root.addWidget(self.note)

        # 注意 QDialogButtonBox 一定要给 parent（self）：
        # Qt 只在 box 的父对象是 QDialog 时，才把它的 accepted()/rejected()
        # 自动接到对话框的 accept()/reject()。没有 parent 时"取消"点了没反应
        # （应用能用只是因为下面显式连了）—— 踩过这个坑，所以这里 parent 和
        # 显式连接都给上，不依赖隐式行为。
        buttons = QDialogButtonBox(self)
        self.btn_apply = buttons.addButton(tr("应用"), QDialogButtonBox.AcceptRole)
        self.btn_default = buttons.addButton(tr("应用并设为默认"),
                                             QDialogButtonBox.AcceptRole)
        self.btn_cancel = buttons.addButton(tr("取消"),
                                            QDialogButtonBox.RejectRole)
        self.btn_cancel.clicked.connect(self.reject)
        buttons.rejected.connect(self.reject)
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
        is_torn = key == "torn"
        show_radius = key in ("shadow", "round") or is_torn
        show_alpha = key in ("shadow", "torn")
        self.radius.setVisible(show_radius and not is_torn)
        self.radius_label.setVisible(show_radius and not is_torn)
        self.tear.setVisible(is_torn)
        self.tear_label.setVisible(is_torn)
        self.reseed.setVisible(is_torn)
        self.alpha.setVisible(show_alpha)
        self.alpha_label.setVisible(show_alpha)
        self.alpha_text.setVisible(show_alpha)
        if is_torn:
            self.alpha_text.setText(tr("投影浓度"))
            self.tear.setMaximum(max(1, self.width.value()))
        else:
            self.alpha_text.setText(tr("阴影浓度"))
        tips = {k: t for k, _, t in STYLES}
        self.note.setText(tr(tips.get(key, "")))
        self._refresh_preview()

    def _on_width(self, v):
        self._s["width"] = v
        # 撕边幅度不能超过纸边宽度
        if self._s.get("style") == "torn":
            self.tear.setMaximum(max(1, v))
        self._refresh_preview()

    def _on_tear(self, v):
        self._s["tear"] = v
        self._refresh_preview()

    def _on_reseed(self):
        self._s["seed"] = int(self._s.get("seed", 0)) + 1
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
        self._s["tear"] = self.tear.value()
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
