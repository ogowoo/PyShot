# -*- coding: utf-8 -*-
"""水印功能测试：绘制、定位、平铺、透明度、持久化、自动应用、可撤销。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

import watermark
from editor import EditorWindow
from scroller import pixmap_to_array
from shapes import WatermarkShape
from watermark import (DEFAULT_SETTINGS, draw_watermark, load_default,
                       normalize, placements, save_default, watermark_size)

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def settings(**kw):
    s = dict(DEFAULT_SETTINGS)
    s.update(kw)
    return s


SZ = QSize(600, 400)


def render(s, size=SZ):
    pix = QPixmap(size)
    pix.fill(QColor("#204060"))
    p = QPainter(pix)
    draw_watermark(p, s, size)
    p.end()
    return pix


# --- 尺寸计算 ---
s_text = settings(text="水印文本", font_size=30)
size = watermark_size(s_text, SZ)
check("文字水印尺寸合理", size.width() > 20 and size.height() > 10,
      f"{size.width():.0f}x{size.height():.0f}")

# --- 九宫格定位 ---
def center_of(s):
    pts = placements(s, SZ, watermark_size(s, SZ))
    sz = watermark_size(s, SZ)
    return (pts[0].x() + sz.width() / 2, pts[0].y() + sz.height() / 2)


cx, cy = center_of(settings(text="水印", position=4))          # 居中
check("居中位置正确", abs(cx - 300) < 2 and abs(cy - 200) < 2, f"{cx:.0f},{cy:.0f}")
lx, ly = center_of(settings(text="水印", position=0))          # 左上
rx, ry = center_of(settings(text="水印", position=8))          # 右下
check("左上靠左靠上", lx < 300 and ly < 200)
check("右下靠右靠下", rx > 300 and ry > 200)
check("右上在右且在上", center_of(settings(text="水印", position=2))[0] > 300
      and center_of(settings(text="水印", position=2))[1] < 200)

# --- 平铺 ---
tiled = settings(text="内部资料", position=9, spacing=40, font_size=20)
pts = placements(tiled, SZ, watermark_size(tiled, SZ))
check("平铺会重复多次", len(pts) > 4, f"{len(pts)} 处")

# --- 真的画上去了（画面发生变化） ---
plain = QPixmap(SZ)
plain.fill(QColor("#204060"))
s_center = settings(text="测试水印", position=4, color="#ffffff", alpha=255)
out = render(s_center)
diff = np.abs(pixmap_to_array(out).astype(int)
              - pixmap_to_array(plain).astype(int))
check("水印确实绘制到画面上", diff.max() > 40, f"最大差异 {diff.max()}")
check("只在中心区域有水印（位置可控）",
      diff[:100, :].max() < 30 and diff[:, :100].max() < 30)

# --- 透明度：alpha 越低越淡 ---
low = pixmap_to_array(render(settings(text="测试水印", position=4, alpha=40)))
high = pixmap_to_array(render(settings(text="测试水印", position=4, alpha=255)))
base = pixmap_to_array(plain)
check("透明度生效（低 alpha 更接近底图）",
      np.abs(low.astype(int) - base.astype(int)).mean()
      < np.abs(high.astype(int) - base.astype(int)).mean())

# --- 旋转 ---
out_rot = render(settings(text="测试水印", position=4, rotation=45))
check("旋转能正常绘制", pixmap_to_array(out_rot).max() != base.max())
check("旋转后与未旋转效果不同",
      not np.array_equal(pixmap_to_array(out_rot), high))

# --- 图片水印 ---
img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_wm_test.png")
logo = QPixmap(120, 60)
logo.fill(Qt.transparent)
lp = QPainter(logo)
lp.fillRect(0, 0, 120, 60, QColor("#ffcc00"))
lp.end()
logo.save(img_path)
s_img = settings(kind="image", image_path=img_path, image_scale=0.4, position=6)
img_size = watermark_size(s_img, SZ)
check("图片水印按图宽比例缩放", abs(img_size.width() - SZ.width() * 0.4) < 2,
      f"{img_size.width():.0f}")
out_img = render(s_img)
check("图片水印能绘制", pixmap_to_array(out_img).max() > 100)

# --- 设置持久化 ---
orig_conf = watermark.CONFIG_PATH
tmp_conf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_wm_conf.json")
watermark.CONFIG_PATH = type(orig_conf)(tmp_conf)
watermark.clear_cache()
saved = settings(text="持久化测试", alpha=123, position=2, auto=True)
check("保存默认水印成功", save_default(saved))
watermark.clear_cache()
loaded = load_default()
check("重新读取设置一致", loaded["text"] == "持久化测试"
      and loaded["alpha"] == 123 and loaded["position"] == 2
      and loaded["auto"] is True)
check("缺失字段会被补齐", normalize({"text": "x"})["font_size"] == DEFAULT_SETTINGS["font_size"])
check("未知字段被忽略", "不存在的字段" not in normalize({"不存在的字段": 1}))

# --- 自动应用到新标签 + 可撤销 ---
win = EditorWindow(QPixmap(400, 300))
check("默认水印已自动应用", len(win.canvas.shapes) == 1
      and isinstance(win.canvas.shapes[0], WatermarkShape),
      f"{[type(s).__name__ for s in win.canvas.shapes]}")
win.canvas.undo()
check("自动水印可撤销掉", len(win.canvas.shapes) == 0)
win.canvas.redo()
check("撤销后可重做", len(win.canvas.shapes) == 1)

# --- 手动添加水印（走编辑器方法）---
win2 = EditorWindow(QPixmap(500, 320))
win2.apply_watermark(win2.canvas, settings(text="手动水印", position=4))
check("手动添加水印", any(isinstance(s, WatermarkShape) for s in win2.canvas.shapes))
out2 = win2.canvas.render_result()
check("水印会出现在导出结果里",
      pixmap_to_array(out2).std() > pixmap_to_array(
          win2.canvas.base_pixmap).std())

# --- 关闭自动水印，避免影响其它测试 ---
save_default(normalize({"auto": False}))
watermark.CONFIG_PATH = orig_conf
watermark.clear_cache()
for f in (tmp_conf, img_path):
    try:
        os.remove(f)
    except OSError:
        pass

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("水印测试通过 ✔")
