# -*- coding: utf-8 -*-
"""首次截图契约：必须"先抓屏、后显示"，且底图不能是纯色。

真实事故：曾为了首屏更快改成"先显示遮罩、后抓屏"，靠
SetWindowDisplayAffinity 把遮罩排除在抓屏之外 —— 实测不可靠，结果
**截出来的整张图就是自己的遮罩**（纯深色 + 蓝色选框边），用户全部白截。
所以这里把契约和兜底都钉住：
- start() 返回时遮罩可见、底图**已经抓好**，且底图不是纯色（没拍到自己）
- 底图因任何原因为空时，交互也不能卡死（右键/Esc 能取消、左键能就地补图）
- 多屏时每块屏都有自己的底图，尺寸与自己的几何一致
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication([])

from snipper import MASK_COLOR, SnipperOverlay

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def sample_colors(pix):
    img = pix.toImage()
    w, h = img.width(), img.height()
    out = set()
    for y in range(0, h, max(1, h // 12)):
        for x in range(0, w, max(1, w // 12)):
            out.add(img.pixelColor(x, y).name())
    return out


# ---------- 1) 契约：先抓屏、后显示；底图不能是纯色 ----------
ov = SnipperOverlay("region")
ov.start("region")
check("start() 返回时遮罩已可见", ov.isVisible())
check("start() 返回时底图已经抓好（先抓屏、后显示）",
      ov._bg is not None and not ov._bg.isNull())
colors = sample_colors(ov._bg)
# 离屏平台抓屏只能得到纯黑，这条只能在真实屏幕下断言；
# 真实屏幕的对应检查在 test_first_capture_latency.py 里
if app.platformName() != "offscreen":
    check("底图不是纯色（没有拍到自己的遮罩）", len(colors) > 2,
          f"采样 {len(colors)} 色: {sorted(colors)[:4]}")
else:
    print("NOTE 离屏平台：跳过「底图非纯色」断言（真实屏幕的检查在延迟测试里）")
check("底图里没有遮罩色（排除自拍）", MASK_COLOR.name() not in colors,
      str(sorted(colors)[:4]))
check("自检信息可读", "底图=" in ov.bg_report(), ov.bg_report())
ov.finish()
check("finish 后不再活跃", ov._active is False)
check("finish 后窗口隐藏", not ov.isVisible())

# ---------- 2) start() 不再依赖"排除自身抓屏"那套（避免再踩）----------
check("start() 不再调用 exclude_from_capture",
      "exclude_from_capture" not in SnipperOverlay.start.__code__.co_names,
      str(SnipperOverlay.start.__code__.co_names))

# ---------- 3) 兜底：底图为空时交互不卡死 ----------
pos = QPointF(50, 50)

ov4 = SnipperOverlay("region")
ov4.start("region")
ov4._bg = None
ov4._img = None
ov4._ensure_cover()                      # 不能因为 _bg 为空就空转
e = QMouseEvent(QMouseEvent.MouseButtonPress, pos, pos, Qt.RightButton,
                Qt.RightButton, Qt.NoModifier)
ov4.mousePressEvent(e)
check("底图没回来时右键也能取消", ov4._active is False)

ov5 = SnipperOverlay("region")
ov5.start("region")
ov5._bg = None
ov5._img = None
e = QMouseEvent(QMouseEvent.MouseButtonPress, pos, pos, Qt.LeftButton,
                Qt.LeftButton, Qt.NoModifier)
ov5.mousePressEvent(e)
check("底图没回来时左键按下会就地补底图",
      ov5._bg is not None and not ov5._bg.isNull())
ov5.finish()

ov6 = SnipperOverlay("region")
ov6.start("region")
ov6._bg = None
ov6._img = None
saved = ov6.screen


class _Boom:
    def grabWindow(self, *a):
        raise RuntimeError("模拟抓屏失败")

    def geometry(self):
        return saved.geometry()

    def devicePixelRatio(self):
        return 1.0


ov6.screen = _Boom()
ov6._ensure_bg()
check("抓屏失败时用兜底图，不留 None",
      ov6._bg is not None and not ov6._bg.isNull())
ov6.screen = saved
ov6.finish()

ov7 = SnipperOverlay("region")
ov7.start("region")
ov7._bg = None
ov7.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
check("底图没回来时 Esc 也能取消", ov7._active is False)

# ---------- 4) 每块屏都有自己的底图 ----------
ovs = []
for scr in app.screens():
    o = SnipperOverlay("region", screen=scr)
    o.start("region")
    ovs.append(o)
check("每块屏的遮罩都有底图",
      all(o._bg is not None and not o._bg.isNull() for o in ovs),
      f"{len(ovs)} 块屏")
check("每块屏的底图尺寸与自己的几何一致",
      all(abs(o._bg.width() - o._geo.width()) <= 2
          and abs(o._bg.height() - o._geo.height()) <= 2 for o in ovs),
      str([(o._bg.width(), o._geo.width()) for o in ovs]))
for o in ovs:
    o.finish()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("首次截图契约测试通过 ✔")
