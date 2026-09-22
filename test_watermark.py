# -*- coding: utf-8 -*-
"""水印测试（对照 FSCapture 的功能点）。

覆盖：文字/图片各自开关与同时启用、九宫格定位、平铺、独立透明度、旋转、
边距、图片按图宽缩放、v1 配置迁移、持久化、自动应用、可撤销、导出可见、
以及对话框的交互（勾选/位置网格/平铺禁用位置）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

import watermark
from editor import EditorWindow
from scroller import pixmap_to_array
from shapes import WatermarkShape
from watermark import (DEFAULT_SETTINGS, WatermarkDialog, describe,
                       draw_watermark, load_default, normalize, placements,
                       save_default, watermark_size)

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
HERE = os.path.dirname(os.path.abspath(__file__))


def render(s, size=SZ):
    pix = QPixmap(size)
    pix.fill(QColor("#204060"))
    p = QPainter(pix)
    draw_watermark(p, s, size)
    p.end()
    return pix


def arr(pix):
    return pixmap_to_array(pix).astype(int)


# ---------- 尺寸与九宫格 ----------
s_text = settings(text="水印文本", font_size=30)
size = watermark_size(s_text, SZ)
check("文字水印尺寸合理", size.width() > 20 and size.height() > 10,
      f"{size.width():.0f}x{size.height():.0f}")


def center_of(s):
    pts = placements(s, SZ, watermark_size(s, SZ))
    sz = watermark_size(s, SZ)
    return (pts[0].x() + sz.width() / 2, pts[0].y() + sz.height() / 2)


cx, cy = center_of(settings(text="水印", position=4))
check("居中位置正确", abs(cx - 300) < 2 and abs(cy - 200) < 2, f"{cx:.0f},{cy:.0f}")
lx, ly = center_of(settings(text="水印", position=0))
rx, ry = center_of(settings(text="水印", position=8))
check("左上靠左靠上", lx < 300 and ly < 200)
check("右下靠右靠下", rx > 300 and ry > 200)
check("右上在右且在上",
      center_of(settings(text="水印", position=2))[0] > 300
      and center_of(settings(text="水印", position=2))[1] < 200)

# ---------- 平铺（FSCapture 的 Tile）----------
tiled = settings(text="内部资料", tile=True, spacing=40, font_size=20)
pts = placements(tiled, SZ, watermark_size(tiled, SZ))
check("平铺会重复多次", len(pts) > 4, f"{len(pts)} 处")
not_tiled = settings(text="内部资料", tile=False, position=4)
check("不平铺时只有一处",
      len(placements(not_tiled, SZ, watermark_size(not_tiled, SZ))) == 1)

# ---------- 真的画上去了 ----------
plain = QPixmap(SZ)
plain.fill(QColor("#204060"))
base = arr(plain)
s_center = settings(text="测试水印", position=4, color="#ffffff",
                    text_alpha=255)
out = render(s_center)
diff = np.abs(arr(out) - base)
check("水印确实绘制到画面上", diff.max() > 40, f"最大差异 {diff.max()}")
check("只在指定区域有水印（位置可控）",
      diff[:100, :].max() < 30 and diff[:, :100].max() < 30)

# ---------- 透明度（文字/图片各自独立）----------
low = arr(render(settings(text="测试水印", position=4, text_alpha=40)))
high = arr(render(settings(text="测试水印", position=4, text_alpha=255)))
check("文字透明度生效（低 alpha 更接近底图）",
      np.abs(low - base).mean() < np.abs(high - base).mean())

# ---------- 旋转 ----------
out_rot = render(settings(text="测试水印", position=4, rotation=45))
check("旋转能正常绘制", arr(out_rot).max() != base.max())
check("旋转后与未旋转效果不同", not np.array_equal(arr(out_rot), high))

# ---------- 边距 ----------
far = settings(text="水印", position=8, margin=80)
near = settings(text="水印", position=8, margin=4)
fx, fy = center_of(far)
nx, ny = center_of(near)
check("边距越大离角越远", fx < nx and fy < ny, f"{fx:.0f},{fy:.0f} vs {nx:.0f},{ny:.0f}")

# ---------- 图片水印 ----------
img_path = os.path.join(HERE, "_wm_test.png")
logo = QPixmap(120, 60)
logo.fill(Qt.transparent)
lp = QPainter(logo)
lp.fillRect(0, 0, 120, 60, QColor("#ffcc00"))
lp.end()
logo.save(img_path)
watermark.clear_cache()

s_img = settings(use_text=False, use_image=True, image_path=img_path,
                 image_scale=0.4, position=6)
img_size = watermark_size(s_img, SZ)
check("图片水印按图宽比例缩放", abs(img_size.width() - SZ.width() * 0.4) < 2,
      f"{img_size.width():.0f}")
out_img = render(s_img)
check("图片水印能绘制", arr(out_img).max() > 100)
check("图片透明度生效",
      np.abs(arr(render(settings(use_text=False, use_image=True,
                                 image_path=img_path, image_scale=0.4,
                                 position=4, image_alpha=30))) - base).mean()
      < np.abs(arr(render(settings(use_text=False, use_image=True,
                                   image_path=img_path, image_scale=0.4,
                                   position=4, image_alpha=255))) - base).mean())

# ---------- 文字 + 图片同时启用（FSCapture 的组合水印）----------
both = settings(use_text=True, use_image=True, text="公司机密",
                image_path=img_path, image_scale=0.3, position=4,
                text_alpha=255, image_alpha=255)
only_text = settings(use_text=True, use_image=False, text="公司机密",
                     position=4, text_alpha=255)
only_img = settings(use_text=False, use_image=True, image_path=img_path,
                    image_scale=0.3, position=4, image_alpha=255)
both_size = watermark_size(both, SZ)
text_size_ = watermark_size(only_text, SZ)
img_size_ = watermark_size(only_img, SZ)
check("同时启用时尺寸为两者之和",
      both_size.height() > text_size_.height() + img_size_.height() - 1,
      f"{both_size.height():.0f} vs {text_size_.height():.0f}+{img_size_.height():.0f}")
out_both = arr(render(both))
check("组合水印确实都画上了",
      np.abs(out_both - base).sum() > np.abs(arr(render(only_text)) - base).sum()
      and np.abs(out_both - base).sum() > np.abs(arr(render(only_img)) - base).sum())

# ---------- v1 配置迁移 ----------
mig = normalize({"kind": "image", "alpha": 123, "position": 9,
                 "shadow": False, "text": "旧配置"})
check("旧 kind 迁移为 use_image",
      mig["use_image"] is True and mig["use_text"] is False)
check("旧 alpha 迁移到两个透明度",
      mig["text_alpha"] == 123 and mig["image_alpha"] == 123)
check("旧 position=9 迁移为平铺", mig["tile"] is True and mig["position"] == 8)
check("旧 shadow 迁移为 outline", mig["outline"] is False)
mig2 = normalize({"kind": "text", "alpha": 200})
check("旧 kind=text 迁移为 use_text",
      mig2["use_text"] is True and mig2["use_image"] is False)

# ---------- 描述文本 ----------
check("描述能反映启用内容",
      "文字" in describe(both) and "图片" in describe(both), describe(both))
check("未启用时描述为未启用",
      describe(settings(use_text=False, use_image=False)) == "未启用")

# ---------- 对话框交互 ----------
dlg = WatermarkDialog(None, settings(use_text=True, use_image=True,
                                     image_path=img_path, position=8), SZ)
check("对话框：文字开关同步", dlg.grp_text.isChecked() is True)
check("对话框：图片开关同步", dlg.grp_image.isChecked() is True)
check("对话框：九宫格有 9 个按钮", len(dlg._pos_buttons) == 9)
check("对话框：位置按钮选中当前值",
      dlg._pos_buttons[8].isChecked() is True)
dlg._pos_buttons[4].click()
check("对话框：点格子能改位置", dlg.settings()["position"] == 4)
dlg.grp_text.setChecked(False)
check("对话框：关掉文字开关后设置随之变化",
      dlg.settings()["use_text"] is False)
try:
    dlg.grp_text.setChecked(True)
    dlg.tile.setChecked(True)
    check("对话框：平铺时位置按钮禁用",
          all(not b.isEnabled() for b in dlg._pos_buttons))
    check("对话框：平铺时启用了间距", dlg.spacing.isEnabled())
    check("对话框：平铺写入设置", dlg.settings()["tile"] is True)
    dlg.tile.setChecked(False)
    check("对话框：取消平铺后位置按钮恢复",
          all(b.isEnabled() for b in dlg._pos_buttons))
finally:
    dlg.deleteLater()
img_size_dlg = QSize(600, 400)
check("对话框：预览已渲染", not dlg.preview.pixmap().isNull()
      if hasattr(dlg, "preview") else False)

# ---------- 持久化 ----------
orig_conf = watermark.CONFIG_PATH
tmp_conf = os.path.join(HERE, "_wm_conf.json")
watermark.CONFIG_PATH = type(orig_conf)(tmp_conf)
watermark.clear_cache()
saved = settings(text="持久化测试", text_alpha=123, position=2, auto=True,
                 use_image=True, image_path=img_path, tile=True)
check("保存默认水印成功", save_default(saved))
watermark.clear_cache()
loaded = load_default()
check("重新读取设置一致",
      loaded["text"] == "持久化测试" and loaded["text_alpha"] == 123
      and loaded["position"] == 2 and loaded["auto"] is True
      and loaded["use_image"] is True and loaded["tile"] is True)
check("缺失字段会被补齐",
      normalize({"text": "x"})["font_size"] == DEFAULT_SETTINGS["font_size"])
check("未知字段被忽略", "不存在的字段" not in normalize({"不存在的字段": 1}))
check("越界值被夹取",
      normalize({"position": 99, "text_alpha": 999, "rotation": 999})["position"] == 8
      and normalize({"text_alpha": 999})["text_alpha"] == 255)

# ---------- 自动应用到新标签 + 可撤销 ----------
win = EditorWindow(QPixmap(400, 300))
check("默认水印已自动应用", len(win.canvas.shapes) == 1
      and isinstance(win.canvas.shapes[0], WatermarkShape),
      f"{[type(s).__name__ for s in win.canvas.shapes]}")
win.canvas.undo()
check("自动水印可撤销掉", len(win.canvas.shapes) == 0)
win.canvas.redo()
check("撤销后可重做", len(win.canvas.shapes) == 1)

# ---------- 手动添加（走编辑器方法）+ 导出可见 ----------
win2 = EditorWindow(QPixmap(500, 320))
win2.apply_watermark(win2.canvas, settings(text="手动水印", position=4))
check("手动添加水印",
      any(isinstance(s, WatermarkShape) for s in win2.canvas.shapes))
out2 = win2.canvas.render_result()
check("水印会出现在导出结果里",
      pixmap_to_array(out2).std() > pixmap_to_array(
          win2.canvas.base_pixmap).std())

# ---------- 收尾：关掉自动水印 ----------
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
