# -*- coding: utf-8 -*-
"""生成水印效果对照图（人工目视检查用）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])
from watermark import draw_watermark, normalize

logo_path = os.path.join(HERE, "_wm_logo.png")
logo = QPixmap(160, 60)
logo.fill(Qt.transparent)
p = QPainter(logo)
p.setRenderHint(QPainter.Antialiasing)
p.setBrush(QColor("#1e88e5"))
p.setPen(Qt.NoPen)
p.drawRoundedRect(0, 0, 60, 60, 12, 12)
p.setBrush(QColor("#ffffff"))
p.drawEllipse(14, 14, 32, 32)
p.setBrush(QColor("#1e88e5"))
p.drawEllipse(22, 22, 16, 16)
f = QFont("Microsoft YaHei")
f.setPixelSize(24)
f.setBold(True)
p.setFont(f)
p.setPen(QColor("#5a6270"))
p.drawText(QRectF(70, 0, 90, 60), Qt.AlignVCenter, "ACME")
p.end()
logo.save(logo_path)

W, H = 440, 280
variants = [
    ("文字 · 右下（不透明度 47%）", dict(use_text=True, text="仅供内部参考",
                                    position=8, text_alpha=120)),
    ("文字 · 平铺", dict(use_text=True, text="内部资料", tile=True, spacing=50,
                     font_size=20, text_alpha=90)),
    ("图片 · 居中（45% 图宽）", dict(use_text=False, use_image=True,
                               image_path=logo_path, image_scale=0.45,
                               position=4, image_alpha=200)),
    ("图片 + 文字 · 右下（组合水印）", dict(use_text=True, use_image=True,
                                     text="ACME 机密", image_path=logo_path,
                                     image_scale=0.3, position=8,
                                     text_alpha=200, image_alpha=220)),
    ("文字 · 旋转 -30°", dict(use_text=True, text="CONFIDENTIAL", position=4,
                          rotation=-30, text_alpha=110)),
    ("文字 · 左上无边距 + 描边", dict(use_text=True, text="草稿", position=0,
                                 margin=0, text_alpha=230, outline=True)),
]

sheet = QPixmap(W * 3 + 40, (H + 26) * 2 + 10)
sheet.fill(QColor("#17181c"))
sp = QPainter(sheet)
f2 = QFont("Microsoft YaHei")
f2.setPixelSize(13)
sp.setFont(f2)
for i, (label, kw) in enumerate(variants):
    s = normalize(kw)
    cell = QPixmap(W, H)
    cp = QPainter(cell)
    cp.fillRect(0, 0, W, H, QColor("#f4f6f9"))
    cp.setPen(QColor("#c9cdd4"))
    for y in range(44, H, 34):
        cp.drawLine(20, y, W - 20, y)
    cp.setPen(QColor("#8890a0"))
    cp.drawText(20, 28, "示例截图内容")
    cp.end()
    p2 = QPainter(cell)
    draw_watermark(p2, s, QSize(W, H))
    p2.end()
    x = 10 + (i % 3) * (W + 10)
    y = 10 + (i // 3) * (H + 26)
    sp.drawPixmap(x, y, cell)
    sp.setPen(QColor("#e6e8ec"))
    sp.drawText(x + 4, y + H + 18, label)
sp.end()
out = os.path.join(HERE, "_wm_sheet.png")
sheet.save(out)
print(f"已生成 {out}  ({sheet.width()}x{sheet.height()})")
for f3 in (logo_path,):
    try:
        os.remove(f3)
    except OSError:
        pass
