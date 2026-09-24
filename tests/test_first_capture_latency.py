# -*- coding: utf-8 -*-
"""首屏延迟回归测试：用真实屏幕抓取测量"托盘双击 → 遮罩真正出现在屏幕上"的耗时。

之前的 bug：Windows 上第一次创建置顶全屏窗口极慢（实测可达数秒），
且每次截图都新建窗口，导致首次双击托盘后遮罩迟迟不出现。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys
import time

os.environ.setdefault("PYSHOT_TEST", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from main import PyShotApp
from snipper import grab_virtual_desktop
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)


def brightness(pix):
    img = pix.toImage()
    total = n = 0
    for y in range(0, img.height(), 60):
        for x in range(0, img.width(), 60):
            c = img.pixelColor(x, y)
            total += c.red() + c.green() + c.blue()
            n += 1
    return total / (n * 3)


base = brightness(grab_virtual_desktop()[0])
core = PyShotApp(app)
QTest.qWait(700)           # 预热窗口正处于"透明上屏保持期"
during = brightness(grab_virtual_desktop()[0])
print(f"屏幕基准亮度: {base:.0f}   预热保持期亮度: {during:.0f}")

failures = []
if during < base * 0.9:
    failures.append(f"预热窗口污染了屏幕画面: {base:.0f} → {during:.0f}")
else:
    print("预热窗口未污染画面 ✔")

QTest.qWait(3200)          # 等预热保持期结束（应已自动隐藏）
if core._overlay is not None:
    print("预热结束后覆盖层是否隐藏:", not core._overlay.isVisible())
    if core._overlay.isVisible():
        failures.append("预热结束后覆盖层没有隐藏")


def measure(label):
    """触发托盘双击，用"间隔取样"判断遮罩何时上屏。

    注意：不能用紧循环连续抓屏 —— 每次抓屏占用 GUI 线程约 50ms，
    会把窗口上屏所需的事件处理饿死，测出来的延迟会假性偏大（实测能差 10 倍）。
    """
    QTest.qWait(300)
    t0 = time.perf_counter()
    core._on_tray_activated(QSystemTrayIcon.DoubleClick)
    latency = None
    delay = 0.06
    while time.perf_counter() - t0 < 8:
        QTest.qWait(int(delay * 1000))        # 让出 GUI 线程，别干扰上屏
        frame = grab_virtual_desktop()[0]
        if brightness(frame) < base * 0.75:   # 遮罩生效 → 画面明显变暗
            latency = (time.perf_counter() - t0) * 1000
            break
        delay = min(delay * 1.6, 0.4)         # 逐步放宽取样间隔
    if core.snipper:
        core.snipper.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        QTest.qWait(300)
    print(f"{label}: {latency:.0f} ms" if latency else f"{label}: !! 8 秒内没看到遮罩")
    return latency


first = measure("首次托盘双击 → 屏幕上出现遮罩")
second = measure("二次托盘双击 → 屏幕上出现遮罩")

if first is None or first > 900:
    failures.append(f"首次遮罩过慢: {first}")
if second is None or second > 700:
    failures.append(f"二次遮罩过慢: {second}")

# ---------- 关键回归：抓到的底图不能是纯色（曾把自己的遮罩拍进图里）----------
from snipper import SnipperOverlay as _SO


def _sample_colors(pix, step=24):
    img = pix.toImage()
    out = set()
    for y in range(0, img.height(), max(1, img.height() // step)):
        for x in range(0, img.width(), max(1, img.width() // step)):
            out.add(img.pixelColor(x, y).name())
    return out


_ov = _SO("region")
_ov.start("region")
_cols = _sample_colors(_ov._bg)
print(f"抓屏自检: {_ov.bg_report()}")
if len(_cols) <= 2:
    failures.append(f"底图疑似纯色（可能拍到了自己的遮罩）: {sorted(_cols)[:4]}")
_ov.finish()

core.shutdown()
print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("首屏延迟达标 ✔（首次 <900ms，二次 <700ms）")
