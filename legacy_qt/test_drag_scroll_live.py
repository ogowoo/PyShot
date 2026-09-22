# -*- coding: utf-8 -*-
"""真实桌面验证：拖拽真实滚动条自动滚动 + 拼接是否正确（含步长自校准）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QScrollArea

from scroller import ScrollCapture, ScrollDriver, make_default_grab, pixmap_to_array

app = QApplication(sys.argv)
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


DOC_W, DOC_H = 460, 1800
doc = QPixmap(DOC_W, DOC_H)
p = QPainter(doc)
f = QFont("Consolas")
f.setPixelSize(24)
p.setFont(f)
for y in range(0, DOC_H, 50):
    p.fillRect(0, y, DOC_W, 50, QColor.fromHsl((y // 50 * 11) % 360, 150, 190))
    p.setPen(QColor("#22303c"))
    p.drawText(16, y + 34, f"ROW {y:04d} --------------------")
p.end()

win = QMainWindow()
scroll = QScrollArea()
label = QLabel()
label.setPixmap(doc)
scroll.setWidget(label)
scroll.setWidgetResizable(False)
win.setCentralWidget(scroll)
win.setFixedSize(DOC_W + 40, 420)
win.move(160, 140)
win.show()
win.raise_()
win.activateWindow()
QTest.qWait(900)

bar = scroll.verticalScrollBar()
bar.setStyleSheet("QScrollBar:vertical { width: 18px; }")
QTest.qWait(200)

# 视口区域（不含滚动条本身）
vp = scroll.viewport()
region = QRect(vp.mapToGlobal(vp.rect().topLeft()), vp.rect().size())
# 用户应该点的是**滑块**：用 QStyle 取出滑块矩形（点中间那段轨道会变成翻页！）
from PySide6.QtWidgets import QStyle, QStyleOptionSlider
opt = QStyleOptionSlider()
bar.initStyleOption(opt)
slider_rect = bar.style().subControlRect(QStyle.CC_ScrollBar, opt,
                                         QStyle.SC_ScrollBarSlider, bar)
anchor = bar.mapToGlobal(slider_rect.center())
print("视口区域:", region, " 滑块中心:", anchor, " 滑块矩形:", slider_rect,
      " 范围:", bar.minimum(), "-", bar.maximum())

drv = ScrollDriver("drag", region, anchor=anchor)
cap = ScrollCapture(region, grab_fn=make_default_grab(region), driver=drv,
                    interval_ms=700, max_frames=12)
out = []
cap.finished_ok.connect(lambda px: out.append(px))
cap.failed.connect(lambda m: out.append(m))
QTimer.singleShot(200, cap.start)
QTimer.singleShot(40000, app.quit)
cap.finished_ok.connect(app.quit)
cap.failed.connect(lambda m: app.quit())
app.exec()

if out and isinstance(out[0], QPixmap):
    result = out[0]
    path = os.path.join(os.path.dirname(__file__), "_test_drag_long.png")
    result.save(path)
    print(f"拼接结果: {result.width()} x {result.height()}  -> {path}")
    print(f"滚动条最终位置: {bar.value()} / {bar.maximum()}")
    print(f"校准后 px/px: {drv.px_per_unit:.2f}  校准次数: {drv.observations}")
    check("拖拽滚动条真的滚动了", bar.value() > 0, f"value={bar.value()}")
    check("完成了拼接", result.height() > 500, f"高度 {result.height()}")
    check("步长被实测校准", drv.observations >= 1, f"{drv.observations} 次")
    # 校验拼接内容：每 50px 一条色带，带高应保持 50
    col = pixmap_to_array(result)[:, 300].astype(float) / 255
    hues = []
    for i in range(0, col.shape[0], 5):
        r, g, b = col[i]
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn < 0.05:
            continue
        h = 0
        if mx == r:
            h = ((g - b) / (mx - mn)) % 6
        elif mx == g:
            h = (b - r) / (mx - mn) + 2
        else:
            h = (r - g) / (mx - mn) + 4
        hues.append(round(h * 60))
    changes = sum(1 for a, b in zip(hues, hues[1:]) if abs(a - b) > 8)
    print(f"色带边界数: {changes}（原文档 {DOC_H // 50} 条）")
    check("拼接内容连贯（色带数量合理）",
          changes >= DOC_H // 50 - 2, f"{changes} vs {DOC_H // 50}")
else:
    check("完成了拼接", False, str(out))

win.close()
print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("真实滚动条拖拽自动滚动验证通过 ✔")
