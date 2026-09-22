# -*- coding: utf-8 -*-
"""watermark.py —— 水印（对照 FastStone Capture 的「特效 → 水印」重做）。

FSCapture 的水印对话框是：**文字水印**和**图片水印**各自独立开关（可以同时
启用，于是得到「公司 logo + 文字」的组合）、分别设字体/图片与透明度，再用
九宫格选位置（或勾选平铺），可旋转、可设边距，右侧实时预览，最后「应用」；
还有一个「设为默认」让之后每次截图自动加。

本模块按这个结构组织：
- 设置项：use_text / use_image 两个开关 + 各自的透明度
- 位置：0..8 九宫格 + tile 平铺
- 绘制：draw_watermark() 统一负责，编辑器里的 WatermarkShape 和对话框预览共用
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QIcon, QPainter,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFontDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QSlider, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

DEFAULT_SETTINGS = {
    # ---- 文字水印 ----
    "use_text": True,
    "text": "仅供参考",
    "font_family": "Microsoft YaHei",
    "font_size": 28,             # 图像像素
    "bold": True,
    "italic": False,
    "color": "#ffffff",
    "text_alpha": 90,            # 0-255
    "outline": True,             # 描边，深浅背景都看得清
    # ---- 图片水印 ----
    "use_image": False,
    "image_path": "",
    "image_scale": 0.20,         # 占图像宽度的比例
    "image_alpha": 140,          # 0-255
    # ---- 位置与排布 ----
    "position": 8,               # 0..8 九宫格（0=左上 4=居中 8=右下）
    "tile": False,               # 平铺整张图
    "spacing": 60,               # 平铺间距（像素）
    "rotation": 0,               # 旋转角度
    "margin": 24,                # 距图像边缘（像素）
    # ---- 其它 ----
    "auto": False,               # 设为默认后，新截图自动套用
}

POSITION_NAMES = ["左上", "上中", "右上", "左中", "居中", "右中",
                  "左下", "下中", "右下"]

CONFIG_PATH = Path.home() / ".pyshot" / "watermark.json"
_cache = {}

# 文字与图片同时启用时的上下间距（图像像素）
GAP = 8.0


# ---------------------------------------------------------------- 设置读写

def normalize(settings: dict | None) -> dict:
    """补全/校验字段，并把旧版本配置迁移过来。

    旧版（v1）用 kind="text|image" + alpha + position=9 表示平铺，
    这里统一迁移到 use_text/use_image + 各自 alpha + tile。
    """
    out = dict(DEFAULT_SETTINGS)
    if not settings:
        return out
    s = dict(settings)

    if "kind" in s:                     # v1 → v2
        kind = s.pop("kind")
        out["use_text"] = (kind == "text")
        out["use_image"] = (kind == "image")
    if "alpha" in s:
        a = s.pop("alpha")
        out["text_alpha"] = a
        out["image_alpha"] = a
    if "shadow" in s:                   # 旧的 shadow ≈ 新的 outline
        out["outline"] = bool(s.pop("shadow"))
    if s.get("position") == 9:          # 旧的平铺写法
        out["tile"] = True
        s["position"] = 8

    for k, v in s.items():
        if k in DEFAULT_SETTINGS:
            out[k] = v

    # 类型与范围夹取（配置文件可能被手改坏）
    for key in ("use_text", "use_image", "bold", "italic", "outline", "tile",
                "auto"):
        out[key] = bool(out[key])
    out["position"] = max(0, min(8, int(out["position"])))
    out["font_size"] = max(6, min(400, int(out["font_size"])))
    for key in ("text_alpha", "image_alpha"):
        out[key] = max(0, min(255, int(out[key])))
    out["image_scale"] = max(0.01, min(3.0, float(out["image_scale"])))
    out["rotation"] = max(-180, min(180, int(out["rotation"])))
    out["margin"] = max(0, min(2000, int(out["margin"])))
    out["spacing"] = max(0, min(2000, int(out["spacing"])))
    if not isinstance(out["text"], str):
        out["text"] = str(out["text"])
    return out


def load_default() -> dict:
    """读取默认水印设置（缺字段自动补齐）。"""
    global _cache
    if _cache:
        return dict(_cache)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _cache = normalize(json.load(f))
    except Exception:                        # noqa: BLE001
        _cache = dict(DEFAULT_SETTINGS)
    return dict(_cache)


def save_default(settings: dict) -> bool:
    """保存为默认（之后新截图自动套用）。返回是否写盘成功。"""
    global _cache
    _cache = normalize(settings)
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
        return True
    except Exception:                        # noqa: BLE001
        return False


def clear_cache():
    """测试用：清掉内存缓存与图片缓存。"""
    global _cache
    _cache = {}
    if hasattr(_image_cache, "_pix"):
        _image_cache._pix.clear()


def describe(settings: dict) -> str:
    """一句话描述当前水印（托盘/状态栏提示用）。"""
    s = normalize(settings)
    parts = []
    if s["use_text"]:
        parts.append(f"文字「{s['text'].splitlines()[0][:12] if s['text'] else ''}」")
    if s["use_image"]:
        parts.append(f"图片 {os.path.basename(s['image_path']) or '（未选择）'}")
    if not parts:
        return "未启用"
    where = "平铺" if s["tile"] else POSITION_NAMES[s["position"]]
    return " + ".join(parts) + f" · {where}"


# ---------------------------------------------------------------- 字体/图片

def make_font(settings: dict) -> QFont:
    font = QFont(settings.get("font_family") or "Microsoft YaHei")
    font.setPixelSize(max(6, int(settings.get("font_size", 28))))
    font.setBold(bool(settings.get("bold")))
    font.setItalic(bool(settings.get("italic")))
    return font


def _image_cache(settings: dict):
    if not hasattr(_image_cache, "_pix"):
        _image_cache._pix = {}
    key = settings.get("image_path", "")
    if key not in _image_cache._pix:
        pix = QPixmap(key) if key and os.path.exists(key) else QPixmap()
        _image_cache._pix[key] = pix
    return _image_cache._pix[key]


def load_image(settings: dict) -> QPixmap | None:
    pix = _image_cache(settings)
    return pix if pix is not None and not pix.isNull() else None


# ---------------------------------------------------------------- 尺寸与位置

def text_size(settings: dict) -> QSizeF:
    metrics = QFontMetricsF(make_font(settings))
    lines = (settings.get("text") or "").split("\n") or [""]
    width = max((metrics.horizontalAdvance(line) for line in lines), default=0.0)
    height = metrics.lineSpacing() * len(lines)
    return QSizeF(max(0.0, width), max(0.0, height))


def image_size(settings: dict, image_size: QSize) -> QSizeF:
    pix = load_image(settings)
    if pix is None:
        return QSizeF(0, 0)
    scale = max(0.01, float(settings.get("image_scale", 0.2)))
    w = image_size.width() * scale
    h = w * pix.height() / max(1, pix.width())
    return QSizeF(w, h)


def watermark_size(settings: dict, canvas_size: QSize) -> QSizeF:
    """整组水印的包围尺寸（文字与图片同时启用时上下排列）。

    注意：一个都不启用时返回 (0,0)，调用方应据此跳过绘制。
    参数名刻意不叫 image_size —— 那会遮蔽同名函数。
    """
    s = normalize(settings)
    tw = text_size(s) if s["use_text"] else QSizeF(0, 0)
    iw = image_size(s, canvas_size) if s["use_image"] else QSizeF(0, 0)
    if tw.height() <= 0 and iw.height() <= 0:
        return QSizeF(0, 0)
    width = max(tw.width(), iw.width())
    height = tw.height() + iw.height()
    if tw.height() > 0 and iw.height() > 0:
        height += GAP
    return QSizeF(width, height)


def placements(settings: dict, canvas_size: QSize, size: QSizeF) -> list:
    """返回每个水印组的左上角坐标（平铺时多组）。"""
    s = normalize(settings)
    iw, ih = float(canvas_size.width()), float(canvas_size.height())
    margin = float(s["margin"])
    if s["tile"]:
        spacing = float(s["spacing"])
        step_x = size.width() + spacing
        step_y = size.height() + spacing
        if step_x <= 1 or step_y <= 1:
            return []
        out = []
        y = margin
        while y < ih:
            x = margin
            while x < iw:
                out.append(QPointF(x, y))
                x += step_x
            y += step_y
        return out
    col, row = s["position"] % 3, s["position"] // 3
    fx, fy = col / 2.0, row / 2.0
    avail_w = max(0.0, iw - margin * 2 - size.width())
    avail_h = max(0.0, ih - margin * 2 - size.height())
    return [QPointF(margin + fx * avail_w, margin + fy * avail_h)]


# ---------------------------------------------------------------- 绘制

def _wm_draw_text(painter: QPainter, settings: dict, box: QRectF):
    color = QColor(settings.get("color", "#ffffff"))
    color.setAlpha(int(settings.get("text_alpha", 90)))
    if color.alpha() <= 0:
        return
    font = make_font(settings)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    line_h = metrics.lineSpacing()
    lines = (settings.get("text") or "").split("\n")
    for i, line in enumerate(lines):
        y = box.top() + metrics.ascent() + i * line_h
        if settings.get("outline"):
            shadow = QColor(0, 0, 0, min(210, color.alpha() + 50))
            painter.setPen(shadow)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(QPointF(box.left() + dx, y + dy), line)
        painter.setPen(color)
        painter.drawText(QPointF(box.left(), y), line)


def _wm_draw_image(painter: QPainter, settings: dict, box: QRectF):
    pix = load_image(settings)
    if pix is None:
        return
    alpha = int(settings.get("image_alpha", 140))
    if alpha <= 0:
        return
    painter.save()
    painter.setOpacity(alpha / 255.0)
    painter.drawPixmap(box, pix, QRectF(pix.rect()))
    painter.restore()


def draw_watermark(painter: QPainter, settings: dict, canvas_size: QSize,
                   offset: QPointF | None = None):
    """把水印画到 painter 上（坐标系 = 图像像素）。

    图片水印在下、文字水印在上（同时启用时上下排列成一组）。
    """
    s = normalize(settings)
    size = watermark_size(s, canvas_size)
    if size.width() <= 0 or size.height() <= 0:
        return
    tw = text_size(s) if s["use_text"] else QSizeF(0, 0)
    iw = image_size(s, canvas_size) if s["use_image"] else QSizeF(0, 0)
    rotation = float(s["rotation"])
    off = offset or QPointF(0, 0)

    painter.save()
    for pt in placements(s, canvas_size, size):
        painter.save()
        cx = pt.x() + off.x() + size.width() / 2
        cy = pt.y() + off.y() + size.height() / 2
        painter.translate(cx, cy)
        if rotation:
            painter.rotate(rotation)
        top = -size.height() / 2
        if iw.height() > 0:
            _wm_draw_image(painter, s, QRectF(-iw.width() / 2, top,
                                            iw.width(), iw.height()))
            top += iw.height() + (GAP if tw.height() > 0 else 0)
        if tw.height() > 0:
            _wm_draw_text(painter, s,
                          QRectF(-tw.width() / 2, top, tw.width(), tw.height()))
        painter.restore()
    painter.restore()


# ---------------------------------------------------------------- 对话框

def _pct(alpha: int) -> int:
    return int(round(alpha * 100 / 255))


def _alpha(pct: int) -> int:
    return int(round(pct * 255 / 100))


class WatermarkDialog(QDialog):
    """水印对话框（对照 FSCapture：文字/图片各自开关 + 九宫格位置 + 实时预览）。

    确定后由调用方取 settings()；保存为默认则之后新截图自动套用。
    """

    PREVIEW_W, PREVIEW_H = 460, 170

    def __init__(self, parent=None, settings: dict | None = None,
                 image_size: QSize | None = None):
        super().__init__(parent)
        self.setWindowTitle("水印")
        self.setMinimumWidth(560)
        self._s = normalize(settings or load_default())
        self._image_size = image_size if (image_size and image_size.isValid()) \
            else QSize(640, 400)
        self._color = QColor(self._s["color"])
        self._pos_buttons = []

        root = QVBoxLayout(self)
        root.setSpacing(8)

        root.addWidget(self._build_text_group())
        root.addWidget(self._build_image_group())
        root.addWidget(self._build_layout_group())
        root.addWidget(self._build_preview_group())

        buttons = QDialogButtonBox()
        self.btn_apply = buttons.addButton("应用", QDialogButtonBox.AcceptRole)
        self.btn_default = buttons.addButton("应用并设为默认",
                                             QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self.btn_apply.clicked.connect(self._accept_apply)
        self.btn_default.clicked.connect(self._accept_default)
        root.addWidget(buttons)

        self._sync_enabled()
        self._refresh_preview()

    # ---------- 文字水印 ----------
    def _build_text_group(self) -> QGroupBox:
        box = QGroupBox("文字水印")
        box.setCheckable(True)
        box.setChecked(self._s["use_text"])
        self.grp_text = box
        box.toggled.connect(self._on_use_text)
        lay = QVBoxLayout(box)

        self.text = QPlainTextEdit(self._s["text"])
        self.text.setFixedHeight(54)
        self.text.setPlaceholderText("要加在水印上的文字（可多行）")
        self.text.textChanged.connect(self._refresh_preview)
        lay.addWidget(self.text)

        row = QHBoxLayout()
        self.font_btn = QPushButton()
        self.font_btn.setMinimumWidth(220)
        self.font_btn.clicked.connect(self._pick_font)
        row.addWidget(QLabel("字体"))
        row.addWidget(self.font_btn, 1)

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(52, 26)
        self.color_btn.setToolTip("文字颜色")
        self.color_btn.clicked.connect(self._pick_color)
        row.addWidget(QLabel("颜色"))
        row.addWidget(self.color_btn)
        row.addStretch(1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("不透明度"))
        self.text_alpha = QSlider(Qt.Horizontal)
        self.text_alpha.setRange(0, 100)
        self.text_alpha.setValue(_pct(self._s["text_alpha"]))
        self.text_alpha.valueChanged.connect(self._refresh_preview)
        self.text_alpha.valueChanged.connect(
            lambda v: self.text_alpha_label.setText(f"{v}%"))
        row2.addWidget(self.text_alpha, 1)
        self.text_alpha_label = QLabel(f"{_pct(self._s['text_alpha'])}%")
        self.text_alpha_label.setMinimumWidth(42)
        row2.addWidget(self.text_alpha_label)

        self.outline = QCheckBox("描边（深浅背景都清晰）")
        self.outline.setChecked(self._s["outline"])
        self.outline.toggled.connect(self._refresh_preview)
        row2.addWidget(self.outline)
        lay.addLayout(row2)
        self._update_font_button()
        self._update_color_button()
        return box

    def _on_use_text(self, on):
        self._s["use_text"] = on
        self._sync_enabled()
        self._refresh_preview()

    def _pick_font(self):
        font, ok = QFontDialog.getFont(make_font(self._s), self, "选择水印字体")
        if not ok:
            return
        self._s["font_family"] = font.family()
        self._s["font_size"] = max(6, font.pixelSize()
                                   if font.pixelSize() > 0 else 28)
        self._s["bold"] = font.bold()
        self._s["italic"] = font.italic()
        self._update_font_button()
        self._refresh_preview()

    def _update_font_button(self):
        styles = []
        if self._s["bold"]:
            styles.append("粗体")
        if self._s["italic"]:
            styles.append("斜体")
        tail = (" " + " ".join(styles)) if styles else ""
        self.font_btn.setText(f"{self._s['font_family']}  "
                              f"{self._s['font_size']}px{tail}")

    def _pick_color(self):
        c = QColorDialog.getColor(self._color, self, "水印颜色")
        if c.isValid():
            self._color = c
            self._s["color"] = c.name()
            self._update_color_button()
            self._refresh_preview()

    def _update_color_button(self):
        self.color_btn.setStyleSheet(
            f"background:{self._color.name()};"
            "border:1px solid #3a3e47;border-radius:4px;")

    # ---------- 图片水印 ----------
    def _build_image_group(self) -> QGroupBox:
        box = QGroupBox("图片水印")
        box.setCheckable(True)
        box.setChecked(self._s["use_image"])
        self.grp_image = box
        box.toggled.connect(self._on_use_image)
        lay = QVBoxLayout(box)

        row = QHBoxLayout()
        self.image_path = QLineEdit(self._s["image_path"])
        self.image_path.setReadOnly(True)
        self.image_path.setPlaceholderText("选择一张图片（建议用透明底的 PNG）")
        row.addWidget(self.image_path, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_image)
        row.addWidget(browse)
        clear = QPushButton("清除")
        clear.clicked.connect(self._clear_image)
        row.addWidget(clear)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("大小"))
        self.image_scale = QSpinBox()
        self.image_scale.setRange(1, 300)
        self.image_scale.setSuffix(" % 图宽")
        self.image_scale.setValue(int(round(self._s["image_scale"] * 100)))
        self.image_scale.valueChanged.connect(self._on_scale)
        row2.addWidget(self.image_scale)

        row2.addWidget(QLabel("不透明度"))
        self.image_alpha = QSlider(Qt.Horizontal)
        self.image_alpha.setRange(0, 100)
        self.image_alpha.setValue(_pct(self._s["image_alpha"]))
        self.image_alpha.valueChanged.connect(self._refresh_preview)
        self.image_alpha.valueChanged.connect(
            lambda v: self.image_alpha_label.setText(f"{v}%"))
        row2.addWidget(self.image_alpha, 1)
        self.image_alpha_label = QLabel(f"{_pct(self._s['image_alpha'])}%")
        self.image_alpha_label.setMinimumWidth(42)
        row2.addWidget(self.image_alpha_label)

        self.image_thumb = QLabel()
        self.image_thumb.setFixedSize(72, 40)
        self.image_thumb.setAlignment(Qt.AlignCenter)
        self.image_thumb.setStyleSheet(
            "border:1px solid #3a3e47;border-radius:4px;color:#9aa0ab;")
        row2.addWidget(self.image_thumb)
        lay.addLayout(row2)
        self._update_image_thumb()
        return box

    def _on_use_image(self, on):
        self._s["use_image"] = on
        self._sync_enabled()
        self._refresh_preview()

    def _on_scale(self, v):
        self._s["image_scale"] = max(0.01, v / 100.0)
        self._refresh_preview()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择水印图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if not path:
            return
        self._s["image_path"] = path
        self.image_path.setText(path)
        if not self.grp_image.isChecked():
            self.grp_image.setChecked(True)      # 选了图就顺手打开开关
        _image_cache._pix.pop(path, None) if hasattr(_image_cache, "_pix") else None
        self._update_image_thumb()
        self._sync_enabled()
        self._refresh_preview()

    def _clear_image(self):
        self._s["image_path"] = ""
        self.image_path.setText("")
        self._update_image_thumb()
        self._refresh_preview()

    def _update_image_thumb(self):
        pix = load_image(self._s)
        if pix is None:
            self.image_thumb.setPixmap(QPixmap())
            self.image_thumb.setText("无")
            return
        self.image_thumb.setText("")
        self.image_thumb.setPixmap(
            pix.scaled(self.image_thumb.size(), Qt.KeepAspectRatio,
                       Qt.SmoothTransformation))

    # ---------- 位置与排布 ----------
    def _build_layout_group(self) -> QGroupBox:
        box = QGroupBox("位置与排布")
        lay = QHBoxLayout(box)

        grid = QGridLayout()
        grid.setSpacing(3)
        for i in range(9):
            b = QToolButton()
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setFixedSize(30, 26)
            b.setToolTip(POSITION_NAMES[i])
            b.clicked.connect(lambda checked=False, k=i: self._set_position(k))
            grid.addWidget(b, i // 3, i % 3)
            self._pos_buttons.append(b)
        self._pos_buttons[self._s["position"]].setChecked(True)
        lay.addLayout(grid)

        right = QVBoxLayout()
        self.tile = QCheckBox("平铺整张图")
        self.tile.setChecked(self._s["tile"])
        self.tile.toggled.connect(self._on_tile)
        right.addWidget(self.tile)

        row = QHBoxLayout()
        row.addWidget(QLabel("间距"))
        self.spacing = QSpinBox()
        self.spacing.setRange(0, 2000)
        self.spacing.setSuffix(" px")
        self.spacing.setValue(self._s["spacing"])
        self.spacing.valueChanged.connect(self._on_spacing)
        row.addWidget(self.spacing)
        row.addStretch(1)
        right.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("旋转"))
        self.rotation = QSpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setSuffix(" °")
        self.rotation.setValue(self._s["rotation"])
        self.rotation.valueChanged.connect(self._on_rotation)
        row2.addWidget(self.rotation)

        row2.addWidget(QLabel("边距"))
        self.margin = QSpinBox()
        self.margin.setRange(0, 2000)
        self.margin.setSuffix(" px")
        self.margin.setValue(self._s["margin"])
        self.margin.valueChanged.connect(self._on_margin)
        row2.addWidget(self.margin)
        row2.addStretch(1)
        right.addLayout(row2)
        lay.addLayout(right, 1)
        return box

    def _set_position(self, idx):
        self._s["position"] = idx
        self._refresh_preview()

    def _on_tile(self, on):
        self._s["tile"] = on
        for b in self._pos_buttons:
            b.setEnabled(not on)                 # 平铺时位置无意义
        self.spacing.setEnabled(on)
        self._refresh_preview()

    def _on_spacing(self, v):
        self._s["spacing"] = v
        self._refresh_preview()

    def _on_rotation(self, v):
        self._s["rotation"] = v
        self._refresh_preview()

    def _on_margin(self, v):
        self._s["margin"] = v
        self._refresh_preview()

    # ---------- 预览 ----------
    def _build_preview_group(self) -> QGroupBox:
        box = QGroupBox("预览")
        lay = QVBoxLayout(box)
        self.preview = QLabel()
        self.preview.setFixedSize(self.PREVIEW_W, self.PREVIEW_H)
        self.preview.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.preview)
        return box

    def _preview_pixmap(self) -> QPixmap:
        pix = QPixmap(self.PREVIEW_W, self.PREVIEW_H)
        painter = QPainter(pix)
        # 模拟一张截图：渐变 + 几行"文字"，方便看清水印效果
        for y in range(self.PREVIEW_H):
            k = y / max(1, self.PREVIEW_H - 1)
            painter.fillRect(
                0, y, self.PREVIEW_W, 1,
                QColor(int(246 - 40 * k), int(247 - 40 * k), int(250 - 40 * k)))
        painter.setPen(QColor("#b9bec7"))
        for i in range(4):
            painter.fillRect(24, 26 + i * 30, 150 + i * 60, 6,
                             QColor("#c8ccd3"))
        painter.end()
        p2 = QPainter(pix)
        draw_watermark(p2, self._s, QSize(self.PREVIEW_W, self.PREVIEW_H))
        p2.end()
        return pix

    def _refresh_preview(self, *args):
        if not hasattr(self, "preview"):
            return
        self.preview.setPixmap(self._preview_pixmap())

    def _sync_enabled(self):
        on_text = self.grp_text.isChecked()
        for w in (self.text, self.font_btn, self.color_btn, self.text_alpha,
                  self.outline):
            w.setEnabled(on_text)
        if hasattr(self, "text_alpha_label"):
            self.text_alpha_label.setEnabled(on_text)
        on_img = self.grp_image.isChecked()
        for w in (self.image_scale, self.image_alpha, self.image_thumb):
            w.setEnabled(on_img)
        if hasattr(self, "image_alpha_label"):
            self.image_alpha_label.setEnabled(on_img)
        self.spacing.setEnabled(self.tile.isChecked())
        for b in self._pos_buttons:
            b.setEnabled(not self.tile.isChecked())

    # ---------- 结果 ----------
    def settings(self) -> dict:
        self._s["use_text"] = self.grp_text.isChecked()
        self._s["use_image"] = self.grp_image.isChecked()
        self._s["text"] = self.text.toPlainText()
        self._s["text_alpha"] = _alpha(self.text_alpha.value())
        self._s["image_alpha"] = _alpha(self.image_alpha.value())
        self._s["outline"] = self.outline.isChecked()
        self._s["tile"] = self.tile.isChecked()
        self._s["spacing"] = self.spacing.value()
        self._s["rotation"] = self.rotation.value()
        self._s["margin"] = self.margin.value()
        self._s["image_scale"] = max(0.01, self.image_scale.value() / 100.0)
        return normalize(self._s)

    def _accept_apply(self):
        self._save_as_default = False
        self.accept()

    def _accept_default(self):
        self._save_as_default = True
        self.accept()

    def save_as_default(self) -> bool:
        """调用方在 accepted 之后询问：是否要把本次设置存为默认。"""
        return bool(getattr(self, "_save_as_default", False))
