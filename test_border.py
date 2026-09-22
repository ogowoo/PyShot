# -*- coding: utf-8 -*-
"""加边框测试（对照 FSCapture 的「特效 → 边缘」）。

重点验证：
- 各样式都能出图，且**输出比输入大**（边框加在图片外面）
- 透明背景的样式（阴影/渐隐）确实带 alpha
- 编辑器里加边框后：底图变大、已有标注整体平移、可 Ctrl+Z 撤销回去
- 对话框交互与持久化
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

import border
from border import (BORDER_DEFAULTS, STYLES, BorderDialog,
                    border_padding, normalize_border, render_border)
from editor import EditorWindow
from scroller import pixmap_to_array
from shapes import RectShape

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def settings(**kw):
    s = dict(BORDER_DEFAULTS)
    s.update(kw)
    return s


def make_image(w=200, h=140, dpr=1.0):
    pix = QPixmap(w, h)
    pix.fill(QColor("#f4f6f9"))
    p = QPainter(pix)
    p.setPen(QColor("#b9bec7"))
    for y in range(20, h, 24):
        p.drawLine(10, y, w - 10, y)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def has_alpha(pix):
    img = pix.toImage().convertToFormat(img_format_alpha())
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            if img.pixelColor(x, y).alpha() < 250:
                return True
    return False


def img_format_alpha():
    from PySide6.QtGui import QImage
    return QImage.Format_ARGB32


# ---------- 边距计算 ----------
check("普通样式边距 = 宽度",
      border_padding(settings(style="solid", width=12)) == (12, 12, 12, 12))
check("阴影边距含扩散",
      border_padding(settings(style="shadow", width=10, shadow_spread=6))
      == (16, 16, 16, 16))
pl, pt, pr, pb = border_padding(settings(style="polaroid", width=10))
check("拍立得下方留更宽", pb > pt and pl == pr == pt == 10, f"{pl},{pt},{pr},{pb}")
check("宽度为 0 时无边距", border_padding(settings(width=0)) == (0, 0, 0, 0))

# ---------- 各样式都能出图，且尺寸正确 ----------
base = make_image()
for key, name, _tip in STYLES:
    out = render_border(base, settings(style=key, width=12, shadow_spread=0))
    pl, pt, pr, pb = border_padding(settings(style=key, width=12, shadow_spread=0))
    expect = (base.width() + pl + pr, base.height() + pt + pb)
    changed = not np.array_equal(pixmap_to_array(out),
                                pixmap_to_array(base)[:out.height(), :out.width()]
                                if out.width() <= base.width() else None) \
        if False else True
    check(f"样式「{name}」出图尺寸正确",
          out.width() == expect[0] and out.height() == expect[1],
          f"{out.width()}x{out.height()} 期望 {expect[0]}x{expect[1]}")
    if out.isNull():
        check(f"样式「{name}」不是空图", False)

check("输出确实比输入大（边框加在外面）",
      render_border(base, settings(style="solid", width=12)).width()
      == base.width() + 24)
check("dpr 被保留",
      abs(render_border(make_image(dpr=1.5),
                        settings(style="solid", width=8)
                        ).devicePixelRatio() - 1.5) < 1e-6)

# ---------- 透明背景 ----------
check("阴影样式背景透明",
      has_alpha(render_border(base, settings(style="shadow", width=16))))
check("渐隐样式背景透明",
      has_alpha(render_border(base, settings(style="fade", width=16))))
solid_out = render_border(base, settings(style="solid", width=10))
check("单线样式背景不透明（整幅填充）",
      not has_alpha(solid_out))

# ---------- 边框颜色生效 ----------
red = render_border(base, settings(style="solid", width=10, color="#ff0000"))
c = red.toImage().pixelColor(2, 2)
check("边框色生效", c.red() > 200 and c.green() < 60 and c.blue() < 60,
      c.name())
check("原图内容在中间（未被裁掉）",
      red.toImage().pixelColor(12, 12) == base.toImage().pixelColor(2, 2))

# ---------- 设置校验 ----------
check("未知样式回落到默认",
      normalize_border({"style": "不存在"})["style"] == BORDER_DEFAULTS["style"])
check("宽度被夹取", normalize_border({"width": 9999})["width"] == 400)
check("阴影浓度被夹取",
      normalize_border({"shadow_alpha": -5})["shadow_alpha"] == 0
      and normalize_border({"shadow_alpha": 999})["shadow_alpha"] == 255)
check("描述可读", "阴影" in border.describe_border(settings(style="shadow", width=10)),
      border.describe_border(settings(style="shadow", width=10)))

# ---------- 对话框 ----------
dlg = BorderDialog(None, settings(style="solid", width=18, color="#123456"),
                   QSize(400, 300))
check("对话框：样式下拉列出全部样式", dlg.style.count() == len(STYLES),
      f"{dlg.style.count()} 项")
check("对话框：宽度同步", dlg.width.value() == 18)
check("对话框：预览已渲染", not dlg.preview.pixmap().isNull())
check("对话框：取出设置", dlg.settings()["style"] == "solid"
      and dlg.settings()["width"] == 18)
dlg.style.setCurrentIndex([k for k, _, _ in STYLES].index("shadow"))
app.processEvents()
# 注意：对话框没 show() 时 isVisible() 恒为假，这里要看显式隐藏状态
check("对话框：切到阴影后显示浓度滑条", not dlg.alpha.isHidden())
check("对话框：阴影样式下显示圆角", not dlg.radius.isHidden())
dlg.style.setCurrentIndex([k for k, _, _ in STYLES].index("solid"))
app.processEvents()
check("对话框：单线样式隐藏浓度滑条", dlg.alpha.isHidden())
check("对话框：单线样式也隐藏圆角", dlg.radius.isHidden())
dlg.width.setValue(30)
app.processEvents()
check("对话框：改宽度进设置", dlg.settings()["width"] == 30)
dlg.deleteLater()

# ---------- 编辑器集成：底图变大 + 标注平移 + 可撤销 ----------
win = EditorWindow(QPixmap(300, 200))
canvas = win.canvas
shape = RectShape(QColor("#e53935"), 3, QRectF(20, 20, 100, 60))
canvas.shapes.append(shape)
before_size = (canvas.base_pixmap.width(), canvas.base_pixmap.height())
before_pos = (shape.rect.x(), shape.rect.y())
ok = win.apply_border(canvas, settings(style="solid", width=15))
check("编辑器：加边框返回成功", ok is True)
check("编辑器：底图变大",
      canvas.base_pixmap.width() == before_size[0] + 30
      and canvas.base_pixmap.height() == before_size[1] + 30,
      f"{canvas.base_pixmap.width()}x{canvas.base_pixmap.height()}")
check("编辑器：标注整体平移了边框宽度",
      abs(shape.rect.x() - (before_pos[0] + 15)) < 0.01
      and abs(shape.rect.y() - (before_pos[1] + 15)) < 0.01,
      f"{shape.rect.x()},{shape.rect.y()}")
check("编辑器：画布控件尺寸跟着变大",
      abs(canvas.width() - canvas.base_pixmap.width() / canvas.dpr
          * canvas.zoom) < 2)
out = canvas.render_result()
check("编辑器：导出结果包含边框",
      out.width() == canvas.base_pixmap.width())
canvas.undo()
check("编辑器：撤销后底图恢复",
      canvas.base_pixmap.width() == before_size[0]
      and canvas.base_pixmap.height() == before_size[1],
      f"{canvas.base_pixmap.width()}x{canvas.base_pixmap.height()}")
check("编辑器：撤销后标注位置也恢复",
      abs(canvas.shapes[-1].rect.x() - before_pos[0]) < 0.01)
canvas.redo()
check("编辑器：可重做", canvas.base_pixmap.width() == before_size[0] + 30)
# 宽度 0 不做改动
check("编辑器：宽度 0 不改变图片",
      win.apply_border(canvas, settings(width=0)) is False)

# ---------- 设为默认后新截图自动加边框 ----------
orig2 = border.BORDER_CONFIG_PATH
tmp2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bd_auto.json")
border.BORDER_CONFIG_PATH = type(orig2)(tmp2)
border.clear_border_cache()
border.save_border_default(normalize_border({"style": "solid", "width": 20,
                                             "auto": True}))
border.clear_border_cache()
win2 = EditorWindow(QPixmap(200, 150))
check("默认边框会自动应用到新截图",
      win2.canvas.base_pixmap.width() == 240
      and win2.canvas.base_pixmap.height() == 190,
      f"{win2.canvas.base_pixmap.width()}x{win2.canvas.base_pixmap.height()}")
win2.canvas.undo()
check("自动边框可以撤销",
      win2.canvas.base_pixmap.width() == 200)
border.save_border_default(normalize_border({"auto": False}))
border.BORDER_CONFIG_PATH = orig2
border.clear_border_cache()
try:
    os.remove(tmp2)
except OSError:
    pass

# ---------- 持久化 ----------
orig = border.BORDER_CONFIG_PATH
tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_bd_conf.json")
border.BORDER_CONFIG_PATH = type(orig)(tmp)
border.clear_border_cache()
check("保存默认边框成功",
      border.save_border_default(settings(style="round", width=22, auto=True)))
border.clear_border_cache()
loaded = border.load_border_default()
check("重新读取一致",
      loaded["style"] == "round" and loaded["width"] == 22
      and loaded["auto"] is True)
border.save_border_default(normalize_border({"auto": False}))
border.BORDER_CONFIG_PATH = orig
border.clear_border_cache()
try:
    os.remove(tmp)
except OSError:
    pass

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("加边框测试通过 ✔")
