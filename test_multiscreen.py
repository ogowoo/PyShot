# -*- coding: utf-8 -*-
"""多显示器测试：一屏一窗、按各自 DPR 精确抓取、坐标换算、会话统一收起。

本机通常只有一块屏，所以用假屏幕对象替换 QGuiApplication 来验证多屏逻辑。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import main as main_mod
import snipper as snipper_mod
from snipper import region_to_screen_pixels

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeScreen:
    """只实现我们代码真正用到的那几个方法。"""

    def __init__(self, name, geo, dpr, color):
        self._name = name
        self._geo = QRect(geo)
        self._dpr = float(dpr)
        self._color = QColor(color)
        self.grabs = 0

    def name(self):
        return self._name

    def geometry(self):
        return QRect(self._geo)

    def availableGeometry(self):
        return QRect(self._geo)

    def devicePixelRatio(self):
        return self._dpr

    def grabWindow(self, wid=0):
        self.grabs += 1
        pix = QPixmap(int(self._geo.width() * self._dpr),
                      int(self._geo.height() * self._dpr))
        pix.setDevicePixelRatio(self._dpr)
        pix.fill(self._color)
        return pix


class FakeGui:
    def __init__(self, screens):
        self._screens = screens

    def screens(self):
        return list(self._screens)

    def primaryScreen(self):
        return self._screens[0]

    def screenAt(self, pt):
        for s in self._screens:
            if s.geometry().contains(pt):
                return s
        return None

    def primaryScreen_available(self):
        return self._screens[0].geometry()


# 布局：主屏 1280x720 @100%，右侧副屏 1920x1080 @150%，左侧副屏负坐标
SA = FakeScreen("screenA", QRect(0, 0, 1280, 720), 1.0, "#203040")
SB = FakeScreen("screenB", QRect(1280, 0, 1920, 1080), 1.5, "#402030")
SC = FakeScreen("screenC", QRect(-1600, 0, 1600, 900), 1.25, "#304020")
fake = FakeGui([SA, SB, SC])
snipper_mod.QGuiApplication = fake
main_mod.QGuiApplication = fake
# scroller 也要打桩：它的 PrintWindow 回退路径会读屏幕 dpr
import scroller as scroller_mod
scroller_mod.QGuiApplication = fake

# --- 坐标换算（纯函数） ---
check("主屏 100% 换算 1:1",
      region_to_screen_pixels(QRect(10, 10, 100, 50), SA.geometry(), 1.0)
      == QRect(10, 10, 100, 50))
check("副屏 150% 换算正确",
      region_to_screen_pixels(QRect(1300, 100, 200, 100), SB.geometry(), 1.5)
      == QRect(30, 150, 300, 150))
check("负坐标屏 125% 换算正确",
      region_to_screen_pixels(QRect(-1500, 40, 160, 80), SC.geometry(), 1.25)
      == QRect(125, 50, 200, 100))

# --- 一屏一窗 ---
from main import PyShotApp
core = PyShotApp(app)
overlays = core._ensure_overlays()
check("每块屏一个覆盖层", len(overlays) == 3, f"{len(overlays)} 个")
check("覆盖层各自对应对的显示器",
      [ov.screen.name() for ov in overlays] == ["screenA", "screenB", "screenC"])
check("覆盖层几何等于各自屏幕几何",
      [ov.screen_geometry() for ov in overlays]
      == [SA.geometry(), SB.geometry(), SC.geometry()])

# --- 在 150% 的副屏上截图：尺寸与 dpr 必须按该屏算 ---
core.open_editor(QPixmap(200, 150))
ed = core.editors[0]
core.capture_region()
QTest.qWait(400)
check("截图会话：所有屏的覆盖层都激活",
      all(ov._active for ov in overlays),
      str([ov._active for ov in overlays]))
check("选区阶段编辑器已最小化", ed.isMinimized())

sb_overlay = overlays[1]
captured = []
regions = []
sb_overlay.captured.connect(lambda p: captured.append(p))
sb_overlay.region_selected.connect(lambda r: regions.append(r))
sb_overlay._origin = QPoint(100, 100)
sb_overlay._current = QPoint(400, 350)
sb_overlay._selecting = True
sb_overlay.mouseReleaseEvent(QMouseEvent(
    QMouseEvent.MouseButtonRelease, QPointF(400, 350),
    Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
QTest.qWait(300)

check("副屏截图成功", len(captured) == 1)
if captured:
    pix = captured[0]
    # 注意 QRect(左上, 右下) 是闭区间，选区实际是 301x251，×1.5 → 451x376
    check("截图按副屏 150% 抓取物理像素",
          pix.width() == 451 and pix.height() == 376,
          f"{pix.width()}x{pix.height()}")
    check("截图带上副屏 dpr", abs(pix.devicePixelRatio() - 1.5) < 1e-6,
          str(pix.devicePixelRatio()))
check("选区坐标是全局逻辑坐标（副屏起点 1280）",
      bool(regions) and regions[0] == QRect(1380, 100, 301, 251),
      str(regions[0]) if regions else "无")
check("截图完成后所有覆盖层都收起",
      not any(ov.isVisible() for ov in overlays))
check("编辑器恢复显示", not ed.isMinimized())

# --- 滚动截图在副屏上：抓帧也要走该屏 dpr ---
from scroller import make_default_grab
grab_fn = make_default_grab(QRect(1400, 200, 500, 400))
frame = grab_fn()
check("滚动抓帧按副屏 dpr 裁剪",
      abs(frame.devicePixelRatio() - 1.5) < 1e-6
      and frame.width() == 750 and frame.height() == 600,
      f"{frame.width()}x{frame.height()} dpr={frame.devicePixelRatio()}")

# --- 屏幕组合变化时重建覆盖层 ---
extra = FakeScreen("screenD", QRect(3200, 0, 1024, 768), 1.0, "#101010")
fake._screens = [SA, SB, SC, extra]
overlays2 = core._ensure_overlays()
check("插入新显示器后自动重建", len(overlays2) == 4
      and overlays2[3].screen.name() == "screenD",
      f"{len(overlays2)} 个")

if core.scroller:
    core.scroller.stop()
core.shutdown()
snipper_mod.QGuiApplication = snipper_mod.QGuiApplication  # 还原由进程退出负责

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("多显示器测试通过 ✔")
