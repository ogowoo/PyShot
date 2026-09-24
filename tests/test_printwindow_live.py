# -*- coding: utf-8 -*-
"""真实桌面验证：PrintWindow 回退能否抓到窗口内容 + 手动滚动模式端到端可用。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QScrollArea)

from capture_utils import (grab_region_printwindow, grab_window_printwindow,
                           looks_like_missing_content, window_at)
from scroller import ScrollCapture, make_default_grab, pixmap_to_array

app = QApplication(sys.argv)
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# --- 造一个内容明显的窗口 ---
win = QMainWindow()
label = QLabel()
canvas = QPixmap(420, 260)
p = QPainter(canvas)
p.fillRect(0, 0, 420, 260, QColor("#101418"))
p.setPen(QColor("#4ade80"))
f = QFont("Consolas")
f.setPixelSize(22)
p.setFont(f)
for i in range(9):
    p.drawText(20, 32 + i * 26, f"PRINTWINDOW-TEST-LINE-{i:02d}")
p.end()
label.setPixmap(canvas)
win.setCentralWidget(label)
win.setFixedSize(440, 300)
win.move(240, 200)
win.show()
win.raise_()
win.activateWindow()
QTest.qWait(900)

# --- 1) 常规抓屏该区域（应当有内容） ---
region = QRect(win.x() + 8, win.y() + 30, 400, 240)
normal = make_default_grab(region)()
check("常规抓屏能拿到窗口内容", not looks_like_missing_content(normal),
      f"尺寸 {normal.width()}x{normal.height()}")

# --- 2) 直接验证 PrintWindow 管线能取到窗口内容 ---
hwnd = int(win.winId())
pw = grab_window_printwindow(hwnd)
check("PrintWindow 能返回位图", pw is not None and not pw.isNull(),
      f"{pw.width()}x{pw.height()}" if pw is not None and not pw.isNull() else "None")
if pw is not None and not pw.isNull():
    check("PrintWindow 位图有内容（不是黑屏）",
          not looks_like_missing_content(pw),
          f"亮度均值可用性 OK，尺寸 {pw.width()}x{pw.height()}")

# --- 3) 按区域回退抓取 ---
alt = grab_region_printwindow(QRect(region.x(), region.y(),
                                    region.width(), region.height()), 1.0)
check("按区域 PrintWindow 回退可用",
      alt is not None and not looks_like_missing_content(alt),
      f"{alt.width()}x{alt.height()}" if alt is not None else "None")

# --- 4) 手动滚动模式端到端（真实滚动条由"用户"操作） ---
scroll = QScrollArea()
tall = QLabel()
tall_doc = QPixmap(420, 1500)
tp = QPainter(tall_doc)
for y in range(0, 1500, 50):
    tp.fillRect(0, y, 420, 50, QColor.fromHsl((y // 50 * 13) % 360, 150, 190))
tp.end()
tall.setPixmap(tall_doc)
scroll.setWidget(tall)
win.setCentralWidget(scroll)
scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
QTest.qWait(500)

bar = scroll.verticalScrollBar()
sregion = QRect(scroll.mapToGlobal(scroll.rect().topLeft()), scroll.rect().size())
manual = ScrollCapture(sregion, grab_fn=make_default_grab(sregion),
                       interval_ms=200, manual=True)
manual.bar_sizes = None
results = []
manual.finished_ok.connect(lambda px: results.append(px))
manual.failed.connect(lambda m: results.append(m))
QTimer.singleShot(600, manual.start)
# 模拟用户分几次自己滚动
for i in range(6):
    QTimer.singleShot(1200 + i * 450,
                      lambda v=(i + 1) * 150: bar.setValue(min(v, bar.maximum())))
QTimer.singleShot(1200 + 6 * 450 + 400, manual.stop)
QTimer.singleShot(15000, app.quit)
manual.finished_ok.connect(app.quit)
manual.failed.connect(lambda m: app.quit())
app.exec()

check("手动模式能拼出长图",
      bool(results) and isinstance(results[0], QPixmap),
      f"结果类型 {type(results[0]).__name__}" if results else "无结果")
if results and isinstance(results[0], QPixmap):
    h = results[0].height()
    check("手动模式长图高度合理", h > 600, f"高度 {h}px")
win.close()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("真实窗口回退与手动滚动验证通过 ✔")
