# -*- coding: utf-8 -*-
"""生成一张演示图：模拟 FSCapture 风格的指引标注效果。"""
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from editor import Canvas
from shapes import (ArrowShape, HighlightShape, MosaicShape, RectShape,
                    StepShape, TextShape)

app = QApplication([])

# 伪造一个"软件界面"截图
base = QPixmap(760, 480)
grad = QLinearGradient(0, 0, 0, 480)
grad.setColorAt(0, QColor("#f5f7fa"))
grad.setColorAt(1, QColor("#e4eaf2"))
p = QPainter(base)
p.fillRect(base.rect(), grad)
p.fillRect(0, 0, 760, 48, QColor("#2f3542"))          # 标题栏
p.setPen(QColor("white"))
f = QFont("Microsoft YaHei"); f.setPixelSize(18); f.setBold(True)
p.setFont(f)
p.drawText(20, 31, "示例应用程序 — 设置面板")
p.fillRect(0, 48, 180, 432, QColor("#dfe4ea"))        # 侧边栏
f.setPixelSize(14); f.setBold(False)
p.setFont(f); p.setPen(QColor("#2f3542"))
for i, name in enumerate(["常规", "账户", "通知", "隐私", "关于"]):
    p.drawText(30, 100 + i * 40, name)
p.setPen(QColor("#57606f"))
p.drawText(220, 100, "服务器地址：")
p.drawRect(340, 80, 300, 30)
p.drawText(220, 150, "API 密钥：sk-************************")
p.drawText(220, 220, "自动同步：")
p.drawRect(340, 200, 44, 24)
p.fillRect(560, 400, 120, 40, QColor("#1e88e5"))
p.setPen(QColor("white"))
p.drawText(590, 426, "保 存")
p.end()

# 用编辑器画布做指引标注
canvas = Canvas(base)
canvas.shapes.extend([
    StepShape(QColor("#e53935"), 2, QPointF(360, 95), 1, 22),
    RectShape(QColor("#e53935"), 3, QRectF(330, 72, 320, 46)),
    ArrowShape(QColor("#e53935"), 3, QPointF(360, 118), QPointF(300, 180)),
    TextShape(QColor("#e53935"), 2, QPointF(180, 200), "① 填入服务器地址", 22),
    StepShape(QColor("#e53935"), 2, QPointF(362, 212), 2, 22),
    TextShape(QColor("#e53935"), 2, QPointF(180, 260), "② 打开自动同步", 22),
    HighlightShape(QColor("#fdd835"), 1, QRectF(218, 130, 260, 30)),
    MosaicShape(QColor("#000"), 1, QRectF(340, 136, 300, 26)),
    StepShape(QColor("#e53935"), 2, QPointF(620, 392), 3, 22),
    ArrowShape(QColor("#e53935"), 3, QPointF(640, 360), QPointF(640, 396)),
    TextShape(QColor("#e53935"), 2, QPointF(520, 350), "③ 点击保存", 22),
])
out = canvas.render_result()
out.save(os.path.join(ROOT_DIR,  "demo.png"))
print("demo.png saved")
