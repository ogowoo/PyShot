# -*- coding: utf-8 -*-
"""截图循环的不变量测试（全面 review 用）。

用户的复现路径：截一次 → 关掉编辑器 → 再截 → 遮罩挡住不退。
单屏环境不一定能复现"抢不到焦点"，但整条链路的**残留状态**是可以逐个盯住的：
每一轮截完都必须满足
  - 注册表里没有任何遮罩还 active / 可见
  - self.snipper 已清空
  - _minimized_by_capture 已清空
  - 编辑器（若有）在 self.editors 里且有效
连续跑多轮，任何一轮违反都会失败。
另外验证"逃生口"：遮罩开着时再按一次区域热键 = 取消。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

import main as m
import snipper as snip

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def setContextMenu(self, menu):
        pass

    def setToolTip(self, t):
        pass

    def show(self):
        pass


class P(m.PyShotApp):
    """只搭出截图流程需要的那部分状态。"""

    def __init__(self):
        self.app = app
        self.editors = []
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray_available = True
        self.tray = FakeTray()
        self._overlays = []
        self._overlay_screens = []
        self.snipper = None
        self._scroll_mode = None
        self._minimized_by_capture = []
        self._hotkey_actions = {}


def leftover():
    """还活着的遮罩（active 或可见）。"""
    out = []
    for ov in list(snip._ALL_OVERLAYS):
        try:
            if getattr(ov, "_active", False) or ov.isVisible():
                out.append(ov)
        except Exception:                              # noqa: BLE001
            pass
    return out


def invariants(core, tag):
    bad = []
    left = leftover()
    if left:
        bad.append(f"还有 {len(left)} 个遮罩没收起")
    if core.snipper is not None:
        bad.append("snipper 没清空")
    if getattr(core, "_minimized_by_capture", []):
        bad.append("_minimized_by_capture 没清空")
    check(f"[{tag}] 截图流程收尾干净", not bad, "；".join(bad))


def do_capture(core, w=200, h=150):
    """走一遍区域截图：按下→移动→松开。"""
    core.capture_region()
    QTest.qWait(60)
    ov = core.snipper
    if ov is None:
        return False
    p1, p2 = QPointF(60, 60), QPointF(60 + w, 60 + h)
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, p1, p1, Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    ov.mousePressEvent(ev)
    ev = QMouseEvent(QMouseEvent.MouseMove, p2, p2, Qt.NoButton,
                     Qt.LeftButton, Qt.NoModifier)
    ov.mouseMoveEvent(ev)
    ev = QMouseEvent(QMouseEvent.MouseButtonRelease, p2, p2, Qt.LeftButton,
                     Qt.NoButton, Qt.NoModifier)
    ov.mouseReleaseEvent(ev)
    QTest.qWait(220)                        # 等 _on_captured 的 120ms 延时
    return True


# ---------- 连续 4 轮：每轮截完就关掉编辑器（用户的路径）----------
core = P()
for i in range(1, 5):
    ok = do_capture(core)
    check(f"第 {i} 轮截图有覆盖层并完成", ok and len(core.editors) >= 1,
          f"ok={ok} editors={len(core.editors)}")
    invariants(core, f"第 {i} 轮截完")
    if core.editors:
        core.editors[0].close()             # 用户关掉编辑器
        QTest.qWait(120)
    check(f"第 {i} 轮关掉编辑器后 editors 清空", len(core.editors) == 0,
          str(len(core.editors)))
    invariants(core, f"第 {i} 轮关编辑器后")

# ---------- 逃生口：遮罩开着时再按一次区域热键 = 取消 ----------
core.capture_region()
QTest.qWait(60)
ov = core.snipper
check("逃生口场景：遮罩已打开", ov is not None and ov._active)
core._hotkey_actions[0x5053] = "region"
core._on_hotkey(0x5053)                     # 再按一次 Ctrl+Alt+X
QTest.qWait(120)
check("再按一次热键会取消截图（不依赖窗口焦点）",
      core.snipper is None and not leftover(), str(leftover()))
check("取消后没有留下最小化的编辑器",
      not getattr(core, "_minimized_by_capture", []))

# ---------- Esc / 右键 也都能取消 ----------
core.capture_region()
QTest.qWait(60)
ov = core.snipper
ov.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
QTest.qWait(80)
check("Esc 能取消", core.snipper is None and not leftover())

core.capture_region()
QTest.qWait(60)
ov = core.snipper
pos = QPointF(40, 40)
ev = QMouseEvent(QMouseEvent.MouseButtonPress, pos, pos, Qt.RightButton,
                 Qt.RightButton, Qt.NoModifier)
ov.mousePressEvent(ev)
QTest.qWait(80)
check("右键能取消", core.snipper is None and not leftover())

# ---------- 截图期间编辑器被最小化，结束后要还原 ----------
core2 = P()
core2.open_editor(QPixmap(300, 200))
ed = core2.editors[0]
ed.show()
app.processEvents()
core2.capture_region()
QTest.qWait(60)
check("截图开始时编辑器被最小化（免得把自己拍进去）", ed.isMinimized())
core2._cancel_capture()
QTest.qWait(80)
check("取消后编辑器恢复显示", not ed.isMinimized())
invariants(core2, "取消后")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("截图循环不变量测试通过 ✔")
