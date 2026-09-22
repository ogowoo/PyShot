# -*- coding: utf-8 -*-
"""水印：配置、绘制与设置持久化（对标 FSCapture 的水印功能）。

能力
====
- 文字水印：多行文本、字体/字号/粗斜体、颜色、透明度
- 图片水印：选一张图，按比例缩放
- 位置：九宫格（左上…右下）+ 平铺
- 旋转角度、边距、平铺间距
- 可"设为默认"，之后每次新截图自动加上

绘制逻辑集中在 draw_watermark()，编辑器里的水印图形和对话框预览共用同一份，
保证"预览 = 实际效果"。
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPixmap
from style import SpinBox
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSlider, QSpinBox, QVBoxLayout)

POSITIONS = ["左上", "上中", "右上", "左中", "居中", "右中", "左下", "下中", "右下", "平铺"]

DEFAULT_SETTINGS = {
    "kind": "text",              # text | image
    "text": "仅供参考",
    "font_family": "Microsoft YaHei",
    "font_size": 28,             # 图像像素
    "bold": True,
    "italic": False,
    "color": "#ffffff",
    "alpha": 90,                 # 0-255
    "image_path": "",
    "image_scale": 0.2,          # 占图像宽度的比例
    "position": 8,               # 0-8 九宫格；9 = 平铺
    "rotation": 0,               # 角度
    "margin": 24,                # 距边距离（像素）
    "spacing": 60,               # 平铺间距（像素）
    "shadow": True,              # 文字描边阴影，任何背景都看得清
    "auto": False,               # 设为默认后，新截图自动应用
}

CONFIG_PATH = Path.home() / ".pyshot" / "watermark.json"
_cache = {}


# ---------------------------------------------------------------- 设置读写

def normalize(settings: dict | None) -> dict:
    """补全缺失字段（兼容旧配置/手改配置）。"""
    out = dict(DEFAULT_SETTINGS)
    if settings:
        for k, v in settings.items():
            if k in DEFAULT_SETTINGS:
                out[k] = v
    return out


def load_default() -> dict:
    """读取默认水印设置（不存在的字段用默认值补齐）。"""
    global _cache
    if _cache:
        return dict(_cache)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _cache = normalize(json.load(f))
    except Exception:                       # noqa: BLE001
        _cache = dict(DEFAULT_SETTINGS)
    return dict(_cache)


def save_default(settings: dict) -> bool:
    """保存默认水印设置。返回是否写盘成功（失败不影响本次运行）。"""
    global _cache
    _cache = normalize(settings)
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
        return True
    except Exception:                       # noqa: BLE001
        return False


def clear_cache():
    """测试用：清掉内存缓存。"""
    global _cache
    _cache = {}


# ---------------------------------------------------------------- 绘制

def make_font(settings: dict) -> QFont:
    font = QFont(settings.get("font_family") or "Microsoft YaHei")
    font.setPixelSize(max(6, int(settings.get("font_size", 28))))
    font.setBold(bool(settings.get("bold")))
    font.setItalic(bool(settings.get("italic")))
    return font


def watermark_size(settings: dict, image_size: QSize) -> QSizeF:
    """水印自身占据的尺寸（未旋转）。"""
    if settings.get("kind") == "image":
        pix = load_image(settings)
        if pix is None or pix.isNull():
            return QSizeF(0, 0)
        scale = max(0.01, float(settings.get("image_scale", 0.2)))
        w = image_size.width() * scale
        h = w * pix.height() / max(1, pix.width())
        return QSizeF(w, h)
    text = settings.get("text") or ""
    metrics = QFontMetricsF(make_font(settings))
    lines = text.split("\n") or [""]
    width = max((metrics.horizontalAdvance(line) for line in lines), default=0)
    height = metrics.lineSpacing() * len(lines)
    return QSizeF(width, height)


def _image_cache(settings: dict):
    if not hasattr(_image_cache, "_pix"):
        _image_cache._pix = {}
    key = settings.get("image_path", "")
    pix = _image_cache._pix.get(key)
    if pix is None and key and os.path.exists(key):
        pix = QPixmap(key)
        _image_cache._pix[key] = pix
    return pix


def load_image(settings: dict) -> QPixmap | None:
    return _image_cache(settings)


def placements(settings: dict, image_size: QSize, size: QSizeF) -> list:
    """返回每个水印的左上角坐标（平铺时返回多个）。"""
    iw, ih = image_size.width(), image_size.height()
    margin = float(settings.get("margin", 24))
    pos = int(settings.get("position", 8))
    if pos == 9:                        # 平铺
        spacing = float(settings.get("spacing", 60))
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
    col, row = pos % 3, pos // 3
    fx, fy = col / 2.0, row / 2.0
    x = margin + fx * max(0.0, iw - margin * 2 - size.width())
    y = margin + fy * max(0.0, ih - margin * 2 - size.height())
    return [QPointF(x, y)]


def draw_watermark(painter: QPainter, settings: dict, image_size: QSize,
                   offset: QPointF | None = None):
    """把水印画到 painter 上（坐标系 = 图像像素）。"""
    size = watermark_size(settings, image_size)
    if size.width() <= 0 or size.height() <= 0:
        return
    color = QColor(settings.get("color", "#ffffff"))
    color.setAlpha(int(settings.get("alpha", 90)))
    rotation = float(settings.get("rotation", 0))
    offset = offset or QPointF(0, 0)

    pix = load_image(settings) if settings.get("kind") == "image" else None
    text = settings.get("text") or ""
    font = make_font(settings)
    metrics = QFontMetricsF(font)
    shadow = bool(settings.get("shadow")) and settings.get("kind") != "image"

    painter.save()
    painter.setOpacity(1.0)
    for pt in placements(settings, image_size, size):
        painter.save()
        cx = pt.x() + offset.x() + size.width() / 2
        cy = pt.y() + offset.y() + size.height() / 2
        painter.translate(cx, cy)
        if rotation:
            painter.rotate(rotation)
        box = QRectF(-size.width() / 2, -size.height() / 2,
                     size.width(), size.height())
        if pix is not None and not pix.isNull():
            painter.drawPixmap(box, pix, QRectF(pix.rect()))
        else:
            painter.setFont(font)
            line_h = metrics.lineSpacing()
            for i, line in enumerate(text.split("\n")):
                y = box.top() + metrics.ascent() + i * line_h
                if shadow:                      # 描边，深浅背景都清晰
                    shadow_color = QColor(0, 0, 0, min(200, color.alpha() + 40))
                    painter.setPen(shadow_color)
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        painter.drawText(QPointF(box.left() + dx, y + dy), line)
                painter.setPen(color)
                painter.drawText(QPointF(box.left(), y), line)
        painter.restore()
    painter.restore()


# ---------------------------------------------------------------- 对话框

class WatermarkDialog(QDialog):
    """水印设置对话框（带实时预览）。"""

    def __init__(self, parent=None, settings: dict | None = None,
                 image_size: QSize | None = None):
        super().__init__(parent)
        self.setWindowTitle("水印")
        self.setMinimumWidth(560)
        self._settings = normalize(settings or load_default())
        self._image_size = image_size or QSize(640, 400)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.kind = QComboBox()
        self.kind.addItems(["文字水印", "图片水印"])
        self.kind.setCurrentIndex(0 if self._settings["kind"] == "text" else 1)
        self.kind.currentIndexChanged.connect(self._on_kind)
        form.addRow("类型", self.kind)

        self.text = QPlainTextEdit(self._settings["text"])
        self.text.setFixedHeight(56)
        self.text.textChanged.connect(self._refresh_preview)
        form.addRow("文字", self.text)

        self.font_box = QComboBox()
        self.font_box.setEditable(True)
        self.font_box.addItems(["Microsoft YaHei", "Segoe UI", "Arial",
                                "Consolas", "SimSun", "SimHei"])
        self.font_box.setCurrentText(self._settings["font_family"])
        self.font_box.currentTextChanged.connect(self._refresh_preview)
        form.addRow("字体", self.font_box)

        row = QHBoxLayout()
        self.size = SpinBox()
        self.size.setRange(8, 400)
        self.size.setValue(int(self._settings["font_size"]))
        self.size.setSuffix(" px")
        self.size.valueChanged.connect(self._refresh_preview)
        self.bold = QCheckBox("粗体")
        self.bold.setChecked(bool(self._settings["bold"]))
        self.bold.toggled.connect(self._refresh_preview)
        self.italic = QCheckBox("斜体")
        self.italic.setChecked(bool(self._settings["italic"]))
        self.italic.toggled.connect(self._refresh_preview)
        row.addWidget(self.size)
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        row.addStretch(1)
        form.addRow("字号", row)

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(60, 24)
        self.color_btn.clicked.connect(self._pick_color)
        form.addRow("颜色", self.color_btn)

        arow = QHBoxLayout()
        self.alpha = QSlider(Qt.Horizontal)
        self.alpha.setRange(10, 255)
        self.alpha.setValue(int(self._settings["alpha"]))
        self.alpha.valueChanged.connect(self._refresh_preview)
        self.alpha_label = QLabel()
        arow.addWidget(self.alpha)
        arow.addWidget(self.alpha_label)
        form.addRow("透明度", arow)

        self.image_path = QLineEdit(self._settings["image_path"])
        browse = QPushButton("选择…")
        browse.clicked.connect(self._browse_image)
        irow = QHBoxLayout()
        irow.addWidget(self.image_path)
        irow.addWidget(browse)
        form.addRow("图片", irow)

        self.image_scale = SpinBox()
        self.image_scale.setRange(2, 100)
        self.image_scale.setValue(int(float(self._settings["image_scale"]) * 100))
        self.image_scale.setSuffix(" % 图宽")
        self.image_scale.valueChanged.connect(self._refresh_preview)
        form.addRow("图片大小", self.image_scale)

        self.position = QComboBox()
        self.position.addItems(POSITIONS)
        self.position.setCurrentIndex(int(self._settings["position"]))
        self.position.currentIndexChanged.connect(self._refresh_preview)
        form.addRow("位置", self.position)

        rrow = QHBoxLayout()
        self.rotation = SpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setValue(int(self._settings["rotation"]))
        self.rotation.setSuffix(" °")
        self.rotation.valueChanged.connect(self._refresh_preview)
        self.margin = SpinBox()
        self.margin.setRange(0, 400)
        self.margin.setValue(int(self._settings["margin"]))
        self.margin.setSuffix(" px 边距")
        self.margin.valueChanged.connect(self._refresh_preview)
        self.spacing = SpinBox()
        self.spacing.setRange(0, 800)
        self.spacing.setValue(int(self._settings["spacing"]))
        self.spacing.setSuffix(" px 间距")
        self.spacing.valueChanged.connect(self._refresh_preview)
        rrow.addWidget(self.rotation)
        rrow.addWidget(self.margin)
        rrow.addWidget(self.spacing)
        form.addRow("旋转/间距", rrow)

        self.shadow = QCheckBox("文字加描边（深浅背景都清晰）")
        self.shadow.setChecked(bool(self._settings["shadow"]))
        self.shadow.toggled.connect(self._refresh_preview)
        form.addRow("", self.shadow)

        self.auto = QCheckBox("设为默认水印：之后每次新截图自动添加")
        self.auto.setChecked(bool(self._settings["auto"]))
        form.addRow("", self.auto)

        root.addLayout(form)

        self.preview = QLabel()
        self.preview.setFixedHeight(180)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "background: #2b2f36; border: 1px solid #3a3d45; border-radius: 6px;")
        root.addWidget(QLabel("预览"))
        root.addWidget(self.preview)

        buttons = QDialogButtonBox()
        self.btn_apply = buttons.addButton("应用", QDialogButtonBox.AcceptRole)
        self.btn_default = buttons.addButton("应用并设为默认",
                                             QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.btn_default.clicked.connect(self._mark_default)
        root.addWidget(buttons)

        self._on_kind()
        self._refresh_preview()

    # ---------- 交互 ----------
    def _mark_default(self):
        self.auto.setChecked(True)
        self.accept()

    def _on_kind(self, *_):
        is_text = self.kind.currentIndex() == 0
        for w in (self.text, self.font_box, self.size, self.bold, self.italic,
                  self.shadow):
            w.setEnabled(is_text)
        for w in (self.image_path, self.image_scale):
            w.setEnabled(not is_text)
        self._refresh_preview()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._settings.get("color", "#ffffff")),
                                  self, "水印颜色")
        if c.isValid():
            self._settings["color"] = c.name()
            self._refresh_preview()

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择水印图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.image_path.setText(path)
            self._refresh_preview()

    # ---------- 数据 ----------
    def settings(self) -> dict:
        s = dict(self._settings)
        s.update({
            "kind": "text" if self.kind.currentIndex() == 0 else "image",
            "text": self.text.toPlainText(),
            "font_family": self.font_box.currentText(),
            "font_size": self.size.value(),
            "bold": self.bold.isChecked(),
            "italic": self.italic.isChecked(),
            "alpha": self.alpha.value(),
            "image_path": self.image_path.text().strip(),
            "image_scale": self.image_scale.value() / 100.0,
            "position": self.position.currentIndex(),
            "rotation": self.rotation.value(),
            "margin": self.margin.value(),
            "spacing": self.spacing.value(),
            "shadow": self.shadow.isChecked(),
            "auto": self.auto.isChecked(),
        })
        return s

    def _refresh_preview(self, *_):
        self.color_btn.setStyleSheet(
            f"background:{self._settings.get('color', '#ffffff')};"
            "border:1px solid #666; border-radius:4px;")
        self.alpha_label.setText(f"{int(self.alpha.value() / 255 * 100)}%")
        s = self.settings()
        w = max(200, self.preview.width() or 420)
        h = 180
        pix = QPixmap(w, h)
        pix.fill(QColor("#39404a"))
        p = QPainter(pix)
        # 画一点"内容"条纹，方便判断水印在真实画面上的效果
        for y in range(20, h, 34):
            p.fillRect(0, y, w, 12, QColor(255, 255, 255, 26))
        draw_watermark(p, s, QSize(w, h))
        p.end()
        self.preview.setPixmap(pix)
