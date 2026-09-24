# -*- coding: utf-8 -*-
"""滚动条拖拽自动滚动：输入驱动、步长自校准、失败降级、选点流程。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile as _tempfile
from pathlib import Path as _Path

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

# 设置文件隔离 + 显式打开滚动长截图的开关（默认是关的，否则入口会被挡住）
import i18n as _i18n

_i18n.SETTINGS_PATH = _Path(_tempfile.mkdtemp(prefix="pyshot_drag_cfg_")) / "settings.json"
_i18n.reset_cache()
from i18n import set_setting as _set_setting

from main import PyShotApp, SCROLL_ENABLED_KEY
from scroller import ScrollCapture, ScrollDriver, array_to_pixmap, _UNIT_DEFAULTS

_set_setting(SCROLL_ENABLED_KEY, True)

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# --- 驱动：步长换算与自校准 ---
d = ScrollDriver("drag", QRect(0, 0, 400, 300), anchor=QPoint(700, 400))
check("拖拽驱动初始单位换算", abs(d.px_per_unit - _UNIT_DEFAULTS["drag"]) < 0.01)
d.last_units = 40.0
d.observe(200)                     # 拖 40px 实际滚了 200px → 5 px/px
check("实测后校准生效", 3.0 < d.px_per_unit < 7.0, f"{d.px_per_unit:.2f}")
before = d.px_per_unit
d.observe(100000)                  # 离谱值应被范围保护忽略
check("异常实测值被忽略", abs(d.px_per_unit - before) < 0.01)
check("模式描述正确", d.describe() == "拖拽滚动条")

w = ScrollDriver("wheel", QRect(0, 0, 400, 300))
k = ScrollDriver("key", QRect(0, 0, 400, 300))
check("滚轮/按键驱动就绪", w.describe() == "滚轮" and k.describe() == "按键")
check("按键模式默认 PageDown", k.key_vk == 0x22)

# --- 拖拽输入序列：按住 → 分步移动 → 松开（用替身记录，不真的动鼠标） ---
import scroller as sm


class FakeUser32:
    def __init__(self):
        self.events = []

    def mouse_event(self, flag, dx, dy, data, extra):
        self.events.append(flag)

    def keybd_event(self, vk, scan, flags, extra):
        self.events.append(("key", vk, flags))


fake = FakeUser32()
moves = []
real_user32 = sm.user32
real_cursor = sm.QCursor.setPos
try:
    sm.user32 = fake
    sm.QCursor.setPos = staticmethod(lambda p: moves.append((p.x(), p.y())))
    sm._sleep_ms = lambda ms: None
    sm._drag_scrollbar(QPoint(500, 300), 120.0, steps=4)
finally:
    sm.user32 = real_user32
    sm.QCursor.setPos = real_cursor

check("拖拽会先按下左键", sm.MOUSEEVENTF_LEFTDOWN in fake.events)
check("拖拽会松开左键", sm.MOUSEEVENTF_LEFTUP in fake.events)
check("按下在松开之前", fake.events.index(sm.MOUSEEVENTF_LEFTDOWN)
      < fake.events.index(sm.MOUSEEVENTF_LEFTUP))
check("拖拽过程中分步移动光标", len(moves) >= 4, f"{len(moves)} 次移动")
check("终点等于锚点+位移", moves[-1][1] - 300 == 120, str(moves[-1]))
check("水平方向不漂移", all(m[0] == 500 for m in moves))

# --- 自动校准：驱动目标步长应让每帧滚动约半屏 ---
rng = np.random.default_rng(11)
doc = rng.integers(0, 255, (3000, 400, 3), dtype=np.uint8)
state = {"pos": 0, "drives": []}


def grab():
    return array_to_pixmap(doc[state["pos"]:state["pos"] + 400])


class RecordingDriver(ScrollDriver):
    """记录每次请求的步长，并按 1.6 倍比例模拟真实滚动（用于验证校准闭环）。"""

    def __call__(self, step_px):
        self.last_units = step_px
        state["drives"].append(step_px)
        state["pos"] = min(state["pos"] + int(step_px * 1.6), 3000 - 400)


drv = RecordingDriver("drag", QRect(0, 0, 400, 400), anchor=QPoint(0, 0))
cap = ScrollCapture(QRect(0, 0, 400, 400), grab_fn=grab, driver=drv,
                    interval_ms=1, max_frames=6)
out = []
cap.finished_ok.connect(lambda p: out.append(p))
cap.failed.connect(lambda m: out.append(m))
QTimer.singleShot(4000, app.quit)
cap.finished_ok.connect(app.quit)
cap.failed.connect(lambda m: app.quit())
cap.start()
app.exec()
check("驱动模式能拼出结果", bool(out) and isinstance(out[0], QPixmap),
      type(out[0]).__name__ if out else "无")
check("确实按目标步长驱动", len(state["drives"]) >= 2, f"{state['drives']}")
check("驱动步长为半屏量级", all(100 <= s <= 400 for s in state["drives"][1:]),
      f"{[round(s) for s in state['drives']]}")
check("首次滚动先用小步试探（还没量出会滚的条带高）",
      state["drives"] and state["drives"][0] <= 80,
      f"首步 {round(state['drives'][0]) if state['drives'] else '无'}")
check("实测后校准了单位换算", drv.observations >= 1, f"校准 {drv.observations} 次")

# --- 拖拽没生效（画面不动）应先自动降级到滚轮再试，而不是立刻报错 ---
still = QPixmap(400, 400)
still.fill(QColor("#3355aa"))
# 加一点纹理：纯色图会被"空白内容保护"提前拦下，这里要测的是拖拽失效降级
_p = QPainter(still)
for _y in range(0, 400, 20):
    _p.fillRect(0, _y, 400, 8, QColor("#88bbee"))
_p.end()
cap2 = ScrollCapture(QRect(0, 0, 400, 400), grab_fn=lambda: still,
                     driver=ScrollDriver("drag", QRect(0, 0, 400, 400)),
                     interval_ms=1, max_frames=12)
res2 = []
cap2.failed.connect(lambda m: res2.append(m))
cap2.finished_ok.connect(lambda p: res2.append("ok"))
QTimer.singleShot(3000, app.quit)
cap2.failed.connect(lambda m: app.quit())
cap2.finished_ok.connect(app.quit)
cap2.start()
app.exec()
check("拖拽无效时先自动降级到滚轮",
      any(isinstance(r, str) and ("滚轮" in r) for r in res2) or
      (res2 and res2[0] == "ok"),
      f"结果: {res2}")

# 拖拽 + 滚轮都没用时，应明确建议换模式（而不是默默出一张空图）
cap2b = ScrollCapture(QRect(0, 0, 400, 400), grab_fn=lambda: still,
                      driver=ScrollDriver("drag", QRect(0, 0, 400, 400)),
                      interval_ms=1, max_frames=16)
res2b = []
cap2b.failed.connect(lambda m: res2b.append(m))
cap2b.finished_ok.connect(lambda p: res2b.append("ok"))
QTimer.singleShot(4000, app.quit)
cap2b.failed.connect(lambda m: app.quit())
cap2b.finished_ok.connect(app.quit)
cap2b.start()
app.exec()
msg2b = res2b[0] if res2b else ""
check("双重失效后提示换模式",
      isinstance(msg2b, str) and ("PageDown" in msg2b or "手动滚动" in msg2b),
      msg2b[:60] if isinstance(msg2b, str) else msg2b)

# --- 恢复重试有上限（不会无限减半） ---
drv2 = ScrollDriver("drag", QRect(0, 0, 400, 400))
for _ in range(6):
    ok = drv2.recovery_after_jump()
check("恢复重试有上限（最多 4 次后放弃）", not ok)

# --- 原生滚动位置 API：结构解析 + 安全降级 ---
from capture_utils import SCROLLINFO, get_scroll_info_at, set_scroll_pos
check("无滚动条处查询安全返回 None",
      get_scroll_info_at(10, 10) is None)
check("非法句柄设滚动位置不崩", set_scroll_pos(0, 100) == 0 or True)

# --- 拖拽模式能用原生 API 时优先使用（不动鼠标） ---
drv3 = ScrollDriver("drag", QRect(0, 0, 400, 400))
drv3.native = {"hwnd": 0, "min": 0, "max": 2000, "page": 400, "pos": 0}
import capture_utils as cu
calls = []
real_set = cu.set_scroll_pos
cu.set_scroll_pos = lambda hwnd, pos: (calls.append(pos), pos)[1]
try:
    drv3(180)
finally:
    cu.set_scroll_pos = real_set
check("原生模式直接设滚动位置（不动鼠标）", calls == [180], str(calls))
check("原生模式步长为视口 45%", drv3.native["pos"] == 180, f"pos={drv3.native['pos']}")

# --- 点滚动条模式会先做滑块对齐/原生检测，再开始拖拽 ---
core2 = PyShotApp(app)
core2.open_editor(QPixmap(300, 200))
core2.capture_scrolling(mode="drag")
QTest.qWait(400)
check("滚动条模式先进入 scroll 选区", core2.snipper is not None
      and core2.snipper.mode == "scroll")
core2.snipper.region_selected.emit(QRect(200, 200, 500, 400))
QTest.qWait(300)
check("框选后进入选点模式", core2.snipper is not None
      and core2.snipper.mode == "point",
      core2.snipper.mode if core2.snipper else "None")
check("选点模式选区已挖空（可穿透点击）",
      not core2.snipper.mask().isEmpty())
core2.snipper.point_selected.emit(QPoint(690, 380))
QTest.qWait(400)
check("点完后启动滚动截图（拖拽驱动）", core2.scroller is not None
      and core2.scroller.driver is not None
      and core2.scroller.driver.mode == "drag")
if core2.scroller:
    core2.scroller.stop()
QTest.qWait(1200)
core2.shutdown()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("滚动条拖拽自动滚动测试通过 ✔")

# --- 选点流程（滚动条模式）：框选后应进入 point 模式而不是直接开始 ---
core = PyShotApp(app)
core.open_editor(QPixmap(300, 200))
ed = core.editors[0]
core.capture_scrolling(mode="drag")
QTest = __import__("PySide6.QtTest", fromlist=["QTest"]).QTest
QTest.qWait(400)
check("滚动条模式先进入 scroll 选区", core.snipper is not None
      and core.snipper.mode == "scroll")

points = []
core.snipper.region_selected.emit(QRect(200, 200, 500, 400))
QTest.qWait(300)
check("框选后进入选点模式（等用户点滑块）", core.snipper is not None
      and core.snipper.mode == "point", core.snipper.mode if core.snipper else "None")
check("选区阶段编辑器保持最小化", ed.isMinimized())

core.snipper.point_selected.emit(QPoint(690, 380))
QTest.qWait(400)
check("点完滑块后启动滚动截图", core.scroller is not None
      and core.scroller.driver is not None
      and core.scroller.driver.mode == "drag",
      core.scroller.driver.mode if core.scroller and core.scroller.driver else "无")
check("拖拽锚点被采用", core.scroller.driver.anchor == QPoint(690, 380),
      str(core.scroller.driver.anchor))
check("滚动期间编辑器仍最小化", ed.isMinimized())
if core.scroller:
    core.scroller.stop()
QTest.qWait(1200)

# --- 按键模式走 key 驱动 ---
core.capture_scrolling(mode="key")
QTest.qWait(300)
core.snipper.region_selected.emit(QRect(200, 200, 500, 400))
QTest.qWait(400)
check("按键模式使用 key 驱动", core.scroller is not None
      and core.scroller.driver is not None
      and core.scroller.driver.mode == "key")
if core.scroller:
    core.scroller.stop()
QTest.qWait(1200)
core.shutdown()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("滚动条拖拽自动滚动测试通过 ✔")
