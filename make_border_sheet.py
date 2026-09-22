# -*- coding: utf-8 -*-
"""生成边框效果对照图（人工目视检查用）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])
from border import STYLES, normalize_border, render_border


def sample(w=260, h=170):
    pix = QPixmap(w, h)
    p = QPainter(pix)
    p.fillRect(0, 0, w, h, QColor("#f4f6f9"))
    p.setPen(QColor("#c9cdd4"))
    for y in range(26, h, 26):
        p.drawLine(14, y, w - 14, y)
    p.setPen(QColor("#8890a0"))
    f = QFont("Microsoft YaHei")
    f.setPixelSize(13)
    p.setFont(f)
    p.drawText(14, 20, "示例截图内容")
    p.end()
    return pix


opts = {
    "solid": dict(width=14, color="#1e88e5"),
    "double": dict(width=16, color="#ffffff"),
    "dashed": dict(width=14, color="#ffffff"),
    "round": dict(width=14, color="#ffffff", radius=18),
    "shadow": dict(width=18, color="#000000", shadow_alpha=120, radius=10),
    "bevel": dict(width=12, color="#c9cdd4"),
    "fade": dict(width=22, color="#ffffff"),
    "polaroid": dict(width=14, color="#ffffff"),
    "torn": dict(width=18, color="#ffffff", tear=9, seed=7),
}

cells = []
for key, name, _tip in STYLES:
    cfg = normalize_border(dict(opts.get(key, {}), style=key))
    framed = render_border(sample(), cfg)
    cells.append((name, framed))

cols = 4
cw = max(c.width() for _, c in cells) + 24
ch = max(c.height() for _, c in cells) + 24
rows = (len(cells) + cols - 1) // cols
sheet = QPixmap(cw * cols, ch * rows + 8)
sheet.fill(QColor("#17181c"))
sp = QPainter(sheet)
f2 = QFont("Microsoft YaHei")
f2.setPixelSize(12)
sp.setFont(f2)
for i, (name, framed) in enumerate(cells):
    x = (i % cols) * cw
    y = (i // cols) * ch
    # 用浅底（像文档页面）——阴影是黑的，深色底上看不出来
    sp.fillRect(x, y, cw - 2, ch - 18, QColor("#eceef3"))
    sp.drawPixmap(x + (cw - framed.width()) // 2,
                  y + (ch - 18 - framed.height()) // 2, framed)
    sp.setPen(QColor("#e6e8ec"))
    sp.drawText(x + 8, y + ch - 5, name)
sp.end()

out = os.path.join(HERE, "_border_sheet.png")
sheet.save(out)
print(f"已生成 {out} ({sheet.width()}x{sheet.height()})，共 {len(cells)} 种样式")
