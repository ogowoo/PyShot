# -*- coding: utf-8 -*-
"""验证：屏蔽 numpy 后应用仍能完整工作（拼接/空白检测/抓帧都是纯 Python）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 让任何 numpy 导入都失败（模拟没装 numpy 的机器）
class _BlockNumpy:
    def find_module(self, name, path=None):
        return self if name == "numpy" or name.startswith("numpy.") else None

    def find_spec(self, name, path=None, target=None):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("numpy 被测试屏蔽")
        return None


sys.meta_path.insert(0, _BlockNumpy())
for mod in list(sys.modules):
    if mod == "numpy" or mod.startswith("numpy."):
        del sys.modules[mod]

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


try:
    import numpy  # noqa: F401
    check("numpy 确实被屏蔽", False)
except ImportError:
    check("numpy 确实被屏蔽", True)

from PySide6.QtCore import QRect, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

# 这些模块都不能再去 import numpy
import capture_utils
import scroller
from scroller import (Frame, ScrollCapture, find_scroll, frame_to_pixmap,
                      pixmap_to_frame, static_strips)
from capture_utils import looks_like_missing_content, pixmap_is_blank

check("numpy 未出现在模块表里",
      not any(m == "numpy" for m in sys.modules))


def make_doc(h=1600, w=400):
    pix = QPixmap(w, h)
    p = QPainter(pix)
    f = QFont("Consolas")
    f.setPixelSize(16)
    p.setFont(f)
    for y in range(0, h, 40):
        p.fillRect(0, y, w, 40, QColor.fromHsl((y // 40 * 9) % 360, 140, 190))
        p.setPen(QColor("#20303c"))
        p.drawText(10, y + 26, f"LINE {y:04d}")
    p.end()
    return pix


doc = make_doc()
fprev = pixmap_to_frame(doc.copy(0, 0, 400, 400))
fcur = pixmap_to_frame(doc.copy(0, 137, 400, 400))
s, diff = find_scroll(fprev, fcur)
check("纯 Python 拼接偏移正确", s == 137, f"s={s} diff={diff}")
check("静止帧识别为 0", find_scroll(fprev, fprev)[0] == 0)
check("静止条带检测可用（同帧对比全部静止，受 45% 上限约束）",
      static_strips(fprev, fprev) == (180, 180),
      str(static_strips(fprev, fprev)))
# 真实滚动：顶部静止条带应被识别出来（选区里的固定标题栏）
fscrolled = pixmap_to_frame(doc.copy(0, 137, 400, 400))
top, bottom = static_strips(fprev, fscrolled)
check("滚动时静止边缘可控", 0 <= top <= 180 and 0 <= bottom <= 180,
      f"top={top} bottom={bottom}")

# 空白检测（纯 Python 统计）
blank = QPixmap(100, 100)
blank.fill(QColor("black"))
check("空白检测：黑屏判为可疑", looks_like_missing_content(blank))
content = make_doc(200, 200)
check("空白检测：有内容不误报", not looks_like_missing_content(content))
check("空白检测：纯色判空白", pixmap_is_blank(blank))

# 完整滚动截图流程（模拟滚动）
state = {"pos": 0}


def grab():
    return doc.copy(0, state["pos"], 400, 400) if state["pos"] + 400 <= 1600 \
        else doc.copy(0, 1200, 400, 400)


def scroll():
    state["pos"] = min(state["pos"] + 150, 1200)


cap = ScrollCapture(QRect(0, 0, 400, 400), grab_fn=grab, scroll_fn=scroll,
                    interval_ms=1, max_frames=12)
out = []
cap.finished_ok.connect(lambda p: out.append(p))
cap.failed.connect(lambda m: out.append(m))
QTimer.singleShot(5000, app.quit)
cap.finished_ok.connect(app.quit)
cap.failed.connect(lambda m: app.quit())
cap.start()
app.exec()
check("无 numpy 也能拼出长图",
      bool(out) and isinstance(out[0], QPixmap),
      f"{out[0].width()}x{out[0].height()}" if out and isinstance(out[0], QPixmap)
      else str(out))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("无 numpy 运行验证通过 ✔")
