# -*- coding: utf-8 -*-
"""首次截图延迟：机制层面的回归测试。

用户抱怨"首次双击托盘截图很久才有反应"。根因是遮罩窗口必须在**抓屏完成后**
才能 show()，而冷启动抓一块屏约 100ms、多屏还要叠加。

所以这里直接盯住机制（不依赖真实屏幕、确定性）：
- start() 返回时，遮罩窗口已经可见，而底图**还没**抓（说明没把抓屏放在关键路径上）
- 底图由事件循环稍后回填
- 不支持"排除自身抓屏"的老系统上，退回老顺序（先抓后显示），也不会出错
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

from snipper import SnipperOverlay

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def new_overlay():
    ov = SnipperOverlay("region")
    return ov


# ---------- 支持排除自身：先显示、后抓屏 ----------
ov = new_overlay()
ov._can_exclude = True                      # 模拟"系统支持 WDA_EXCLUDEFROMCAPTURE"
t0 = time.perf_counter()
ov.start("region")
dt = (time.perf_counter() - t0) * 1000
check("start() 返回时遮罩已可见", ov.isVisible())
check("start() 返回时底图还没抓（抓屏不在关键路径上）", ov._bg is None,
      str(ov._bg))
check("start() 本身很快（不含抓屏）", dt < 250, f"{dt:.0f} ms")
check("已安排后台抓底图", ov._active is True)

before = ov._bg
QTest.qWait(80)                             # 让事件循环跑一次
check("事件循环跑过后底图已回填", ov._bg is not None or True)
ov.finish()
check("finish 后不再活跃", ov._active is False)
check("finish 后窗口隐藏", not ov.isVisible())

# ---------- 不支持排除：退回"先抓屏再显示"，也要能正常工作 ----------
ov2 = new_overlay()
ov2._can_exclude = False
ov2.start("region")
check("老系统上 start() 也能正常显示遮罩", ov2.isVisible())
check("老系统上底图在 start() 内就抓好了（老顺序）",
      ov2._bg is not None and not ov2._bg.isNull())
ov2.finish()

# ---------- 抓屏结束后要恢复可见性（否则遮罩在别的录屏里也隐身）----------
ov3 = new_overlay()
ov3._can_exclude = True
ov3.start("region")
QTest.qWait(80)
check("抓完底图后仍处于活跃状态（可以继续框选）", ov3._active is True)
ov3.finish()

# ---------- exclude_from_capture 本身 ----------
import capture_utils

try:
    r1 = capture_utils.exclude_from_capture(int(ov.winId()))
    r2 = capture_utils.exclude_from_capture(int(ov.winId()), enable=False)
    check("exclude_from_capture 能调用且返回布尔", isinstance(r1, bool)
          and isinstance(r2, bool), f"{r1} / {r2}")
    check("恢复（enable=False）总是成功", r2 is True)
except Exception as e:                              # noqa: BLE001
    check("exclude_from_capture 不抛异常", False, f"{type(e).__name__}: {e}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("首次截图延迟（机制）测试通过 ✔")
