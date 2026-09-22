# -*- coding: utf-8 -*-
"""离屏冒烟测试：不弹窗验证编辑器核心逻辑。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from editor import Canvas, EditorWindow
from shapes import (ArrowShape, MosaicShape, RectShape, StepShape, TextShape)

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


app = QApplication([])

# --- 构造底图 ---
base = QPixmap(400, 300)
base.fill(QColor("#ddeeff"))
from PySide6.QtGui import QPainter
_p = QPainter(base)
for i in range(20):  # 画上彩色条纹，便于验证马赛克生效
    _p.fillRect(i * 20, 0, 10, 300, QColor(i * 12 % 255, i * 30 % 255, 100))
_p.end()

canvas = Canvas(base)
check("canvas 初始尺寸", canvas.width() == 400 and canvas.height() == 300)

# --- 直接注入图形并渲染 ---
canvas.shapes.append(RectShape(QColor("red"), 3, QRectF(10, 10, 100, 60)))
canvas.shapes.append(ArrowShape(QColor("blue"), 2, QPointF(10, 280), QPointF(200, 200)))
canvas.shapes.append(StepShape(QColor("red"), 2, QPointF(50, 50), 1, 20))
canvas.shapes.append(StepShape(QColor("red"), 2, QPointF(90, 50), 2, 20))
canvas.shapes.append(TextShape(QColor("black"), 2, QPointF(120, 120), "步骤说明", 20))
canvas.shapes.append(MosaicShape(QColor("black"), 1, QRectF(200, 20, 80, 60)))
out = canvas.render_result()
check("渲染输出尺寸", out.width() == 400 and out.height() == 300)
check("马赛克区域被修改", out.toImage().pixelColor(240, 50) !=
      base.toImage().pixelColor(240, 50))

# --- 撤销 / 重做 ---
canvas.push_undo()
before = len(canvas.shapes)
canvas.push_undo()
canvas.shapes.append(RectShape(QColor("green"), 3, QRectF(0, 0, 20, 20)))
canvas.undo()
check("撤销后图形数恢复", len(canvas.shapes) == before)
canvas.redo()
check("重做后图形数+1", len(canvas.shapes) == before + 1)
canvas.undo()

# --- 序号计数器 ---
n = canvas.step_counter
canvas.tool = "step"
from PySide6.QtCore import QPoint
from PySide6.QtGui import QMouseEvent
ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(30, 30),
                 Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.mousePressEvent(ev)
check("序号工具放置后计数+1", canvas.step_counter == n + 1)

# --- 拖拽画矩形 ---
canvas.tool = "rect"
press = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(50, 50),
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
move = QMouseEvent(QMouseEvent.MouseMove, QPointF(150, 120),
                   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
release = QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(150, 120),
                      Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
canvas.mousePressEvent(press)
canvas.mouseMoveEvent(move)
canvas.mouseReleaseEvent(release)
check("拖拽生成矩形", any(isinstance(s, RectShape) and
      abs(s.rect.width() - 100) < 2 for s in canvas.shapes))

# --- 选择并删除 ---
canvas.tool = "select"
target = canvas.shapes[-1]
sel_ev = QMouseEvent(QMouseEvent.MouseButtonPress,
                     QPointF(*target.bounding_rect().center().toTuple()),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.mousePressEvent(sel_ev)
check("点选命中矩形", canvas._selected is target)
count = len(canvas.shapes)
from PySide6.QtGui import QKeyEvent
del_ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
canvas.keyPressEvent(del_ev)
check("Delete 删除选中图形", len(canvas.shapes) == count - 1)
canvas.undo()
check("撤销恢复删除", len(canvas.shapes) == count)

# --- 裁剪 ---
canvas.tool = "crop"
canvas._crop_rect = QRectF(20, 20, 200, 150)
canvas.apply_crop()
check("裁剪后底图尺寸", canvas.base_pixmap.width() == 200
      and canvas.base_pixmap.height() == 150)
check("裁剪可撤销", (canvas.undo() or True)
      and canvas.base_pixmap.width() == 400)

# --- 编辑器窗口装配 ---
win = EditorWindow(QPixmap(400, 300))
win.set_tool("arrow")
check("切换工具", win.canvas.tool == "arrow")
win.set_tool("mosaic")
win.copy_to_clipboard()
check("复制到剪贴板", not QApplication.clipboard().pixmap().isNull())

# --- 取色工具：点击吸取颜色并自动切回 ---
probe = QPixmap(60, 60)
probe.fill(QColor("#123456"))
win2 = EditorWindow(probe)
win2.set_tool("rect")
win2.set_tool("pick")
ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(30, 30),
                 Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
win2.canvas.mousePressEvent(ev)
check("取色器吸取颜色", win2.canvas.color.name() == "#123456")
check("取色后切回原工具", win2.canvas.tool == "rect")

# --- 贴图钉板 ---
from pinboard import PinWindow
pin = PinWindow(QPixmap(120, 80))
check("贴图窗口尺寸", pin.width() == 120 and pin.height() == 80)

# --- 滚动拼接算法 ---
import numpy as np
from scroller import array_to_pixmap, find_scroll, pixmap_to_array

rng = np.random.default_rng(42)
doc = rng.integers(0, 255, (1400, 500, 3), dtype=np.uint8)  # 模拟 1400px 长页面

frame0 = doc[0:300]
frame1 = doc[137:437]
s, diff = find_scroll(frame0, frame1)
check("拼接偏移识别 s=137", s == 137)
s0, _ = find_scroll(frame0, frame0)
check("静止画面识别 s=0", s0 == 0)
s_bad, _ = find_scroll(frame0, doc[500:800])
check("无关画面识别为可接受或失败", s_bad in (-1,) or s_bad > 0)

# --- 滚动截图全流程（注入模拟的抓取/滚动函数，离屏跑真实状态机） ---
from PySide6.QtCore import QRect, QTimer
from scroller import ScrollCapture

state = {"offset": 0, "results": []}
VIEW, DOC_H, STEP = 300, 1400, 120

def fake_grab():
    off = state["offset"]
    return array_to_pixmap(doc[off:off + VIEW].copy())

def fake_scroll():
    state["offset"] = min(state["offset"] + STEP, DOC_H - VIEW)

cap = ScrollCapture(QRect(0, 0, 500, VIEW), grab_fn=fake_grab,
                    scroll_fn=fake_scroll, interval_ms=5)
cap.finished_ok.connect(lambda pix: state["results"].append(pix))
cap.failed.connect(lambda msg: state["results"].append(msg))
QTimer.singleShot(15000, app.quit)  # 超时保护
cap.finished_ok.connect(app.quit)
cap.failed.connect(lambda m: app.quit())
cap.start()
app.exec()

if state["results"] and isinstance(state["results"][0], QPixmap):
    long_pix = state["results"][0]
    check("长图拼接完成", long_pix.height() == DOC_H)
    arr = pixmap_to_array(long_pix)
    check("长图内容与原页面一致", bool((arr == doc).all()))
else:
    check("长图拼接完成", False)

# --- 缩放下取色：点击位置应映射到正确的源像素 ---
half = QPixmap(800, 600)
_hp = QPainter(half)
_hp.fillRect(0, 0, 400, 600, QColor("#0000ff"))
_hp.fillRect(400, 0, 400, 600, QColor("#ff0000"))
_hp.end()
win4 = EditorWindow(half)
win4.canvas.set_zoom(0.5)
win4.set_tool("pick")
ev = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(300, 150),
                 Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
win4.canvas.mousePressEvent(ev)
check("缩放 50% 下取色映射到源像素", win4.canvas.color.name() == "#ff0000")
# 放大镜绘制不抛异常
win4.canvas._hover_pos = QPointF(300, 150)
win4.canvas.grab()
check("取色放大镜渲染", True)
win4.close()

# --- Esc 分层行为：裁剪框 → 选中 → 空闲关闭窗口 ---
win3 = EditorWindow(QPixmap(300, 200))
win3.show()
esc = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
# 1. 有裁剪框：第一次 Esc 取消裁剪，不关窗
win3.canvas.tool = "crop"
canvas_rect = QRectF(10, 10, 100, 80)
win3.canvas._crop_rect = canvas_rect
win3.canvas.keyPressEvent(esc)
check("Esc 取消裁剪框", win3.canvas._crop_rect is None and win3.isVisible())
# 2. 有选中图形：第二次 Esc 取消选中，不关窗
win3.canvas.tool = "select"
win3.canvas.shapes.append(RectShape(QColor("red"), 3, QRectF(5, 5, 50, 40)))
win3.canvas._selected = win3.canvas.shapes[-1]
win3.canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
check("Esc 取消选中", win3.canvas._selected is None and win3.isVisible())
# 3. 空闲：第三次 Esc 关闭窗口
win3.canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
check("Esc 空闲时关闭窗口", not win3.isVisible())
win3.close()

# --- 标签页：多张截图共用一个编辑器 ---
win5 = EditorWindow(QPixmap(300, 200))
check("初始一个标签", win5.tabs.count() == 1)
c1 = win5.canvas
win5.add_canvas(QPixmap(400, 300))
win5.add_canvas(QPixmap(500, 200))
check("连续截图新增标签", win5.tabs.count() == 3)
check("新标签自动激活", win5.canvas is not c1)
check("标签切换画布独立", win5.canvas.base_pixmap.width() == 500)
# 工具与颜色跨标签共享
win5.set_tool("arrow")
win5.set_color(QColor("#1e88e5"))
win5.tabs.setCurrentIndex(0)
check("切回旧标签仍沿用工具", win5.canvas.tool == "arrow")
check("切回旧标签仍沿用颜色", win5.canvas.color.name() == "#1e88e5")
# 撤销栈各自独立
win5.canvas.push_undo()
win5.canvas.shapes.append(RectShape(QColor("red"), 2, QRectF(1, 1, 10, 10)))
win5.tabs.setCurrentIndex(1)
check("新标签撤销栈独立", len(win5.canvas._undo_stack) == 0)
# 关闭标签
total = win5.tabs.count()
win5.close_tab(1)
check("关闭标签后数量-1", win5.tabs.count() == total - 1)
win5.close_tab(0)
win5.close_tab(0)
check("关闭最后一个标签会关窗", not win5.isVisible())
win5.close()

# --- 空构造 + 后续加标签（main.open_editor 的真实调用方式） ---
win6 = EditorWindow()          # 不允许要求必传 pixmap（曾因缺省参数导致编辑器静默打不开）
check("编辑器可空构造", win6.tabs.count() == 0 and win6.canvas is None)
win6.add_canvas(QPixmap(320, 240))
check("空构造后可加标签", win6.tabs.count() == 1 and win6.canvas is not None)
check("空构造后状态栏尺寸可用", win6.size_label.text().startswith("320"))
win6.set_tool("mosaic")
check("空构造后设置工具不崩", win6.canvas.tool == "mosaic")
win6.close()

# --- 序号大小可调 ---
from shapes import StepShape as _Step
s_small = _Step(QColor("red"), 2, QPointF(50, 50), 1, 20, 24)
s_big = _Step(QColor("red"), 2, QPointF(50, 50), 1, 20, 120)
check("序号直径独立于字号", abs(s_small.diameter - 24) < 0.1 and abs(s_big.diameter - 120) < 0.1)
check("序号绘制尺寸随直径", s_big.bounding_rect().width() > s_small.bounding_rect().width() * 4)
check("序号数字随直径缩放", s_big.digit_pixel_size() > s_small.digit_pixel_size())

win7 = EditorWindow(QPixmap(400, 300))
win7.set_tool("step")
ev_step = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(80, 80),
                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
win7.canvas.step_diameter = 60
win7.canvas.mousePressEvent(ev_step)
placed = win7.canvas.shapes[-1]
check("新序号使用设定直径", abs(placed.diameter - 60) < 0.1)
# 选中它后用控件调整大小
win7.set_tool("select")
sel = QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(80, 80),
                  Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
win7.canvas.mousePressEvent(sel)
check("可选中序号", win7.canvas.selected_step() is placed)
check("选中后控件同步为当前尺寸", win7.step_spin.value() == 60)
win7.step_spin.setValue(140)
check("控件改尺寸实时生效", abs(placed.diameter - 140) < 0.1)
win7.canvas.undo()   # 撤销是快照恢复，画布里的序号会换成副本
restored = [s for s in win7.canvas.shapes if isinstance(s, _Step)][-1]
check("序号尺寸可撤销", abs(restored.diameter - 60) < 0.1)
check("控件过大/过小有范围限制", win7.step_spin.minimum() >= 16 and win7.step_spin.maximum() <= 240)
win7.close()

# --- 高 DPI（缩放显示器）：保留 dpr、按逻辑尺寸布局、导出逐位不重采样 ---
hidpi = QPixmap(800, 600)
_hp2 = QPainter(hidpi)
for y in range(0, 600, 20):
    _hp2.fillRect(0, y, 800, 10, QColor((y * 3) % 255, 120, 200))
_hp2.end()
hidpi.setDevicePixelRatio(2.0)
win8 = EditorWindow(hidpi)
c8 = win8.canvas
check("高 DPI 底图保留 dpr", abs(c8.dpr - 2.0) < 1e-6)
c8.set_zoom(1.0)
check("高 DPI 画布按逻辑尺寸布局（100% 不被放大）",
      c8.width() == 400 and c8.height() == 300)
check("高 DPI 坐标映射到物理像素",
      c8.to_image(QPointF(400, 300)) == QPointF(800, 600))
out_hi = c8.render_result()
check("高 DPI 导出保持物理像素", out_hi.width() == 800 and out_hi.height() == 600)
check("高 DPI 导出逐位无损",
      bool((pixmap_to_array(out_hi) == pixmap_to_array(hidpi)).all()))
check("高 DPI 导出带 dpr 便于显示", abs(out_hi.devicePixelRatio() - 2.0) < 1e-6)
c8.shapes.append(MosaicShape(QColor("black"), 1, QRectF(100, 100, 200, 100)))
c8.render_result()
check("高 DPI 下马赛克可正常渲染", True)
from pinboard import PinWindow as _Pin
check("贴图窗口按逻辑尺寸显示", _Pin(hidpi).width() == 400)
win8.close()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("全部通过 ✔")
