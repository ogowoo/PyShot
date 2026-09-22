# -*- coding: utf-8 -*-
"""真实屏幕滚动截图测试：真实的 QScrollArea + 真实屏幕抓取，
只把"滚轮输入"换成直接滚动条操作（避免移动真实鼠标）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QScrollArea

from scroller import ScrollCapture, make_default_grab, pixmap_to_array

app = QApplication(sys.argv)

# --- 造一个 500x1600 的带编号长页面 ---
DOC_W, DOC_H = 500, 1600
doc_pix = QPixmap(DOC_W, DOC_H)
p = QPainter(doc_pix)
f = QFont("Microsoft YaHei")
f.setPixelSize(28)
p.setFont(f)
for y in range(0, DOC_H, 40):
    hue = (y // 40) % 36
    p.fillRect(0, y, DOC_W, 40, QColor.fromHsl(hue * 10, 120, 200))
    p.setPen(QColor("#333"))
    p.drawText(20, y + 30, f"第 {y:4d} 行 ━━━━━━━━━━")
p.end()

# --- 真实可滚动窗口 ---
win = QMainWindow()
scroll = QScrollArea()
label = QLabel()
label.setPixmap(doc_pix)
scroll.setWidget(label)
scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
win.setCentralWidget(scroll)
win.setFixedSize(520, 320)
win.move(150, 120)
win.show()
win.raise_()
win.activateWindow()
QTest.qWait(800)

bar = scroll.verticalScrollBar()
region = QRect(scroll.mapToGlobal(scroll.rect().topLeft()), scroll.rect().size())
print("scroll region:", region)

result = []

def fake_scroll():
    bar.setValue(min(bar.value() + 117, bar.maximum()))  # 模拟一次滚轮

cap = ScrollCapture(region, grab_fn=make_default_grab(region),
                    scroll_fn=fake_scroll, interval_ms=600)
cap.finished_ok.connect(lambda pix: (result.append(pix), app.quit()))
cap.failed.connect(lambda msg: (result.append(msg), app.quit()))
QTimer.singleShot(60000, app.quit)
cap.start()
app.exec()

if result and isinstance(result[0], QPixmap):
    out = result[0]
    path = os.path.join(os.path.dirname(__file__), "_test_long.png")
    out.save(path)
    print("拼接结果:", out.width(), "x", out.height(), "->", path)
else:
    print("失败:", result)
