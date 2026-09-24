# -*- coding: utf-8 -*-
"""无法抓屏场景的处理测试：空白检测 / PrintWindow 回退 / 手动滚动模式。"""
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from capture_utils import (grab_window_printwindow, looks_like_missing_content,
                           pixmap_is_blank, window_at)
from scroller import ScrollCapture, array_to_pixmap, make_default_grab

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# --- 空白检测 ---
black = QPixmap(200, 150)
black.fill(QColor("black"))
white = QPixmap(200, 150)
white.fill(QColor("white"))
content = QPixmap(200, 150)
_p = QPainter(content)
for y in range(0, 150, 12):
    _p.fillRect(0, y, 200, 6, QColor((y * 5) % 255, 100, 180))
_p.end()

check("纯黑画面判为空白", pixmap_is_blank(black))
check("纯色画面判为纯色", pixmap_is_blank(white))
check("正常内容不判为空白", not pixmap_is_blank(content))
check("抓不到内容：黑屏判为可疑", looks_like_missing_content(black))
check("抓不到内容：纯白页面不误报", not looks_like_missing_content(white))
check("抓不到内容：正常内容不误报", not looks_like_missing_content(content))

# --- 回退：常规抓屏空白时应改用注入的备用抓取 ---
def blank_grab():
    p = QPixmap(300, 300)
    p.fill(QColor("black"))
    return p


# 1) 首帧就是空白 → 明确失败并给出 Citrix 相关建议
res = {}
cap = ScrollCapture(QRect(0, 0, 300, 300), grab_fn=blank_grab,
                    scroll_fn=lambda: None, interval_ms=1)
cap.failed.connect(lambda m: res.setdefault("msg", m))
QTimer.singleShot(3000, app.quit)
cap.finished_ok.connect(app.quit)
cap.failed.connect(lambda m: app.quit())
cap.start()
app.exec()
msg = res.get("msg", "")
check("首帧空白立即失败", bool(msg))
check("失败信息点明硬件加速/内容保护", "硬件加速" in msg and "内容保护" in msg)
check("失败信息建议改用手动滚动", "手动滚动" in msg)

# 2) 备用抓取（PrintWindow 生效的情形）应被采用
calls = {"alt": 0}


def fake_grab():
    calls["alt"] += 1
    arr = np.zeros((300, 300, 3), dtype=np.uint8)
    for i in range(20):                      # 有内容的滚动画面
        arr[i * 15:(i * 15) + 7, :, 0] = (i * 12) % 255
    return array_to_pixmap(arr)


cap2 = ScrollCapture(QRect(0, 0, 300, 300), grab_fn=fake_grab,
                     scroll_fn=lambda: None, interval_ms=1,
                     manual=True)
outs = []
cap2.finished_ok.connect(lambda p: outs.append(p))
QTimer.singleShot(200, cap2.stop)
QTimer.singleShot(3000, app.quit)
cap2.finished_ok.connect(app.quit)
cap2.start()
app.exec()
check("手动模式可正常结束并出图", bool(outs))

# --- 手动模式：不注入滚轮、不因"没进展"自动结束 ---
scrolled = []
manual_cap = ScrollCapture(QRect(0, 0, 300, 300), grab_fn=fake_grab,
                           scroll_fn=lambda: scrolled.append(1),
                           interval_ms=1, manual=True)
check("手动模式不会自己滚动页面",
      manual_cap.scroll_fn is None and manual_cap.driver is None and not scrolled)
check("手动模式采样间隔更密", manual_cap.interval_ms <= 400)
auto_cap = ScrollCapture(QRect(0, 0, 300, 300), grab_fn=fake_grab,
                         scroll_fn=lambda: None, interval_ms=650)
check("自动模式仍按原间隔", auto_cap.interval_ms == 650)

# --- PrintWindow 回退函数本身必须安全（拿不到就返回 None，不抛异常） ---
check("非法窗口句柄返回 None", grab_window_printwindow(0) is None)
check("桌面句柄也不会崩", grab_window_printwindow(window_at(0, 0)) is None
      or isinstance(grab_window_printwindow(window_at(0, 0)), QPixmap))

# --- 默认抓屏函数在空白时应尝试回退（此处只验证不抛异常并返回图） ---
g = make_default_grab(QRect(0, 0, 200, 200))
check("默认抓屏可调用", isinstance(g(), QPixmap))

# --- 多块独立滚动区域：必须识别出来并给出建议，而不是拼出一张错图 ---
from scroller import content_band_residuals, find_scroll, static_strips

rng2 = np.random.default_rng(3)
doc = rng2.integers(0, 255, (1400, 400, 3), dtype=np.uint8)
prev = doc[0:400]

single = doc[137:537]
s_single = find_scroll(prev, single)[0]
single_bands = [r for r in content_band_residuals(prev, single, s_single, 0, 400)
                if r is not None]
check("单一滚动：各带残差一致（不误报）",
      len(single_bands) >= 2 and max(single_bands) < 2)

multi = prev.copy()
multi[0:200] = doc[137:337]      # 上半滚 137
multi[200:400] = doc[40:240]     # 下半滚 40（比如明细面板独立滚动）
# 多块滚动时整体匹配置信度低会被拒绝，用"最佳候选"做诊断（应用里也是这条路径）
from scroller import best_candidate_offset
guess = best_candidate_offset(prev, multi)
check("多块滚动时能找到最佳候选用于诊断", guess > 0, f"guess={guess}")
multi_bands = [r for r in content_band_residuals(prev, multi, guess, 0, 400)
               if r is not None]
check("多块独立滚动：各带残差不一致（能识别）",
      len(multi_bands) >= 2
      and max(multi_bands) > max(6.0, min(multi_bands) * 3.0 + 4.0),
      f"残差 {[round(r, 1) for r in multi_bands]}")

fixed = prev.copy()
fixed[0:300] = doc[137:437]      # 上 300 行滚动，下 100 行固定
s_fixed = find_scroll(prev, fixed)[0]
t_fixed, b_fixed = static_strips(prev, fixed)
fixed_bands = [r for r in content_band_residuals(prev, fixed, s_fixed,
                                                 t_fixed, 400 - b_fixed)
               if r is not None]
check("底部固定面板被识别为静止边缘", b_fixed >= 90, f"bottom={b_fixed}")
check("固定面板不会被误判成多块滚动",
      len(fixed_bands) < 2 or max(fixed_bands) < max(6.0, min(fixed_bands) * 3.0 + 4.0))

check("位移过大时跳过判定（不误报）",
      content_band_residuals(prev, doc[250:650], 250, 0, 400) == [])

# --- 抓帧稳定性：手动模式下应等到画面不再变化才采用 ---
frames = []


def jitter_grab():
    """前两次返回不同画面（模拟刚滚完还在重绘），第三次稳定。"""
    n = len(frames)
    arr = np.zeros((300, 300, 3), dtype=np.uint8)
    arr[:] = (n * 37) % 255
    frames.append(arr)
    return array_to_pixmap(arr)


cap3 = ScrollCapture(QRect(0, 0, 300, 300), grab_fn=jitter_grab,
                     interval_ms=50, manual=True)
first = cap3._grab_settled()
check("手动模式会等到画面稳定再取帧", len(frames) >= 2, f"抓了 {len(frames)} 次")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("抓屏异常场景测试通过 ✔")
