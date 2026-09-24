# -*- coding: utf-8 -*-
"""细粒度时间线：托盘双击 → 各阶段实际耗时（含事件循环阻塞点）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import main as main_mod
import snipper
from main import PyShotApp
from snipper import SnipperOverlay
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)

T0 = [0.0]
marks = []


def mark(name):
    marks.append((name, (time.perf_counter() - T0[0]) * 1000))


# 打点：抓屏、窗口显示、首帧绘制、事件循环最大阻塞
_orig_grab = snipper.grab_virtual_desktop


def grab_probe():
    mark("  grab 开始")
    r = _orig_grab()
    mark("  grab 结束")
    return r


snipper.grab_virtual_desktop = grab_probe
main_mod.grab_virtual_desktop = grab_probe

_orig_start = SnipperOverlay.start


def start_probe(self, mode=None):
    mark("start() 进入")
    _orig_start(self, mode)
    mark("start() 返回（窗口已 show）")


SnipperOverlay.start = start_probe

_orig_paint = SnipperOverlay.paintEvent


def paint_probe(self, e):
    if not any(m[0] == "首帧绘制" for m in marks):
        mark("首帧绘制（遮罩可见）")
    _orig_paint(self, e)


SnipperOverlay.paintEvent = paint_probe

# 探测事件循环最大阻塞：每 5ms 打一次心跳，超过 50ms 的间隔说明被卡住
last = [time.perf_counter()]
stalls = []


def heartbeat():
    now = time.perf_counter()
    gap = (now - last[0]) * 1000
    if gap > 50:
        stalls.append((round((last[0] - T0[0]) * 1000), round(gap)))
    last[0] = now


hb = QTimer()
hb.timeout.connect(heartbeat)
hb.start(5)

core = PyShotApp(app)
QTest.qWait(900)          # 等启动预热完成（_warmup 在 400ms 时触发）
marks.clear()
stalls.clear()
T0[0] = time.perf_counter()
last[0] = T0[0]
mark("托盘双击触发")
core._on_tray_activated(QSystemTrayIcon.DoubleClick)

deadline = time.perf_counter() + 25
while not any(m[0] == "首帧绘制（遮罩可见）" for m in marks) and time.perf_counter() < deadline:
    QTest.qWait(10)

mark("测量结束")
print("=== 时间线（ms，从托盘双击算起）===")
for name, ms in marks:
    print(f"{ms:9.0f}  {name}")
print("\n=== 事件循环阻塞（>50ms 的间隔）===")
for at, gap in stalls[:12]:
    print(f"  在 {at} ms 处卡了 {gap} ms")
if not stalls:
    print("  无")

if core.snipper:
    core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(200)

# 第二次：复用已预热窗口
paints2 = []
_t0b = time.perf_counter()
marks.clear()
T0[0] = time.perf_counter()
mark("第二次托盘双击")
core._on_tray_activated(QSystemTrayIcon.DoubleClick)
deadline = time.perf_counter() + 10
while not any(m[0] == "首帧绘制（遮罩可见）" for m in marks) and time.perf_counter() < deadline:
    QTest.qWait(5)
for name, ms in marks:
    if "首帧" in name:
        print(f"\n第二次（复用窗口）→ 遮罩可见: {ms:.0f} ms")
if core.snipper:
    core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(200)
core.shutdown()
