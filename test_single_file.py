# -*- coding: utf-8 -*-
"""验证单文件版 PyShot.py：导入、核心功能、依赖自举逻辑。"""
import importlib.util
import os

os.environ.setdefault("PYSHOT_LANG", "zh_CN")  # 测试断言中文文案
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYSHOT_SKIP_DEPS"] = "1"          # 测试时不真的去装依赖
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "PyShot.py")

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# --- 以模块方式加载单文件 ---
spec = importlib.util.spec_from_file_location("PyShot_single", TARGET)
mod = importlib.util.module_from_spec(spec)
sys.modules["PyShot_single"] = mod
spec.loader.exec_module(mod)
check("单文件可导入", mod is not None)

# --- 全局字体：中文界面要用中文字体（性能关键，且踩过"函数内导入被合并丢掉"）---
# 背景：全局字体原来是 QSS 的 `* { font-family: "Segoe UI", ... }` 设的，
# 中文只能走字体回退扫描，本机实测第一次排版 7.8 秒 → 换成 app.setFont() 后 1.9 秒。
# 而 apply_font 里若用**函数内** `from i18n import current_language`，单文件合并
# 会把那行删掉、被 except 吞掉，中文界面悄悄退回 Segoe UI（本测试就是为此加的）。
# 字体本身要等下面建好 QApplication 之后再验（见"核心功能"之前那段）。
check("单文件：QSS 里没有 `*` 字体规则（性能）",
      not [ln for ln in mod.APP_QSS.splitlines()
           if ln.strip().startswith("*") and "font" in ln])
check("单文件：启动预热与延后恢复都在",
      hasattr(mod.PyShotApp, "_warm_ui")
      and hasattr(mod.PyShotApp, "schedule_boot")
      and hasattr(mod.PyShotApp, "boot_restore"))

# --- 依赖自举逻辑（用假 runner 验证降级尝试链） ---
calls = []
ok = mod.pip_install(["FakePkg"], runner=lambda cmd: (calls.append(cmd), 1)[1])
check("安装失败会依次尝试多种方式", not ok and len(calls) == 4)
check("第一次是直接安装", calls[0][-1] == "FakePkg" and "--user" not in calls[0])
check("包含 --user 降级", any("--user" in c for c in calls))
check("包含镜像源降级", any("-i" in c for c in calls))
calls.clear()
ok2 = mod.pip_install(["FakePkg"], runner=lambda cmd: (calls.append(cmd), 0)[1])
check("安装成功即返回", ok2 and len(calls) == 1)
check("缺失检测正常", mod.missing_packages([("PySide6", "PySide6")]) == [])
check("缺失检测能发现不存在的库",
      mod.missing_packages([("no_such_module_xyz", "no_such_module_xyz")])
      == ["no_such_module_xyz"])
check("依赖报告可读", "PySide6" in mod.deps_report()
      and "内嵌依赖目录" in mod.deps_report())
check("只依赖 PySide6（numpy 已剥离）",
      [p for _, p in mod.REQUIRED_PACKAGES] == ["PySide6"])
check("跳过自举开关有效", mod.ensure_deps() is True)

# --- 核心功能：画布 / 序号 / 撤销 ---
app = mod.QApplication([])

# --- 全局字体（要在 QApplication 建好之后验）---
# PYSHOT_LANG 优先级高于 set_language()，切语言前先摘掉它
_saved_lang = os.environ.pop("PYSHOT_LANG", None)
_fam = {}
for _lang in ("zh_CN", "zh_TW", "en"):
    mod.set_language(_lang, persist=False)
    mod.apply_font(app)
    _fam[_lang] = app.font().family()
if _saved_lang is not None:
    os.environ["PYSHOT_LANG"] = _saved_lang
check("单文件：中文界面用中文字体", _fam["zh_CN"] == "Microsoft YaHei UI", str(_fam))
check("单文件：繁体界面也用中文字体", _fam["zh_TW"] == "Microsoft YaHei UI", str(_fam))
check("单文件：英文界面用 Segoe UI", _fam["en"] == "Segoe UI", str(_fam))
check("单文件：启动预热与延后恢复都在",
      hasattr(mod.PyShotApp, "_warm_ui")
      and hasattr(mod.PyShotApp, "schedule_boot")
      and hasattr(mod.PyShotApp, "boot_restore"))
mod.set_language("zh_CN", persist=False)
mod.apply_font(app)

pix = mod.QPixmap(400, 300)
pix.fill(mod.QColor("#ddeeff"))
canvas = mod.Canvas(pix)
canvas.step_diameter = 80
canvas.shapes.append(mod.StepShape(mod.QColor("red"), 2,
                                   mod.QPointF(50, 50), 1, 20, 80))
check("单文件序号尺寸可调", abs(canvas.shapes[0].diameter - 80) < 0.1)
out = canvas.render_result()
check("单文件可渲染输出", out.width() == 400 and out.height() == 300)

# --- 核心功能：滚动拼接算法 ---
import numpy as np
rng = np.random.default_rng(7)
doc = rng.integers(0, 255, (900, 300, 3), dtype=np.uint8)
s, _ = mod.find_scroll(doc[0:300], doc[111:411])
check("单文件滚动拼接算法正确", s == 111)

# --- 核心功能：编辑器标签页 ---
win = mod.EditorWindow(mod.QPixmap(200, 150))
win.add_canvas(mod.QPixmap(300, 200))
check("单文件编辑器标签可用", win.tabs.count() == 2 and win.canvas is not None)

# --- 水印：必须走**合并后**的模块（各模块共用一个命名空间）---
# 这里的价值在于：模块间顶层重名会让名字互相覆盖，多文件版察觉不到，
# 单文件版却会崩（曾出过：style.py 的 _draw_text 覆盖 watermark.py 的同名函数，
# 一点水印就 TypeError）。所以必须在合并件上真跑一遍水印链路。
base = mod.QPixmap(400, 300)
base.fill(mod.QColor("#204060"))
before = mod.pixmap_to_array(base).copy()
p = mod.QPainter(base)
mod.draw_watermark(p, mod.DEFAULT_SETTINGS, mod.QSize(400, 300))
p.end()
after = mod.pixmap_to_array(base)
check("单文件：水印能画上去", np.abs(after.astype(int)
                                - before.astype(int)).max() > 40)
check("单文件：水印尺寸可算",
      mod.watermark_size(mod.DEFAULT_SETTINGS, mod.QSize(400, 300)).width() > 10)

# 对话框：构造 + 预览渲染 + 取设置（最接近用户点「水印」按钮的那条路径）
dlg = mod.WatermarkDialog(None, mod.DEFAULT_SETTINGS, mod.QSize(400, 300))
check("单文件：水印对话框能构造", dlg is not None)
check("单文件：预览已渲染", not dlg.preview.pixmap().isNull())
s_dlg = dlg.settings()
check("单文件：对话框能取出设置",
      s_dlg["use_text"] is True and "text_alpha" in s_dlg)
# 平铺分支（走 placements）
tiled = dict(mod.DEFAULT_SETTINGS)
tiled.update({"tile": True, "spacing": 30})
check("单文件：平铺水印能算出多处位置",
      len(mod.placements(tiled, mod.QSize(400, 300),
                         mod.watermark_size(tiled, mod.QSize(400, 300)))) > 3)
dlg.deleteLater()

# --- 用户真正点的按钮：走 EditorWindow 的方法（会弹模态对话框）---
# 这里必须测，因为踩过两次坑：
#   1) 跨模块重名（style 覆盖 watermark 的 _draw_text）——一画水印就崩
#   2) 本地导入用了 as 别名，合并后导入被删、别名悬空 —— 一点边框就 NameError
# 两次都是"多文件正常、单文件崩"，且都因为只测了底层函数、没测用户路径。
_orig_exec = mod.QDialog.exec
mod.QDialog.exec = lambda self: mod.QDialog.Accepted      # 不弹模态框，直接确定
try:
    win3 = mod.EditorWindow(mod.QPixmap(220, 160))
    before_w, before_h = (win3.canvas.base_pixmap.width(),
                          win3.canvas.base_pixmap.height())
    win3.add_border()                     # ← 用户点「边框」按钮
    check("单文件：点「边框」真的加上边框了",
          win3.canvas.base_pixmap.width() > before_w,
          f"{before_w} -> {win3.canvas.base_pixmap.width()}")
    win3.canvas.undo()
    check("单文件：撤销能退回加边框前",
          win3.canvas.base_pixmap.width() == before_w,
          str(win3.canvas.base_pixmap.width()))
    win3.canvas.redo()
    win3.add_watermark()                  # ← 用户点「水印」按钮
    check("单文件：点「水印」不报错",
          any(isinstance(s, mod.WatermarkShape) for s in win3.canvas.shapes),
          str([type(s).__name__ for s in win3.canvas.shapes]))
finally:
    mod.QDialog.exec = _orig_exec

# --- 构建期就该拦住的重名 ---
from build_single import MODULES, find_collisions
_collisions = find_collisions(MODULES)
if _collisions:
    print("   冲突明细:", _collisions)
check("当前源码没有会互相覆盖的跨模块重名", _collisions == [])

# --- 单文件不应残留本地 import ---
src = open(TARGET, encoding="utf-8").read()
check("无残留本地 import",
      not any(l.strip().startswith(("from shapes", "from style", "from snipper",
                                    "from editor", "from scroller",
                                    "from bootstrap", "from pinboard",
                                    "from capture_utils", "from watermark"))
              for l in src.splitlines()))
check("内嵌了抓屏回退工具", "def grab_region_printwindow" in src
      and "def looks_like_missing_content" in src)
check("内嵌了水印功能", "def draw_watermark" in src and "class WatermarkDialog" in src)
check("内嵌了依赖自举", "def ensure_deps" in src and "REQUIRED_PACKAGES" in src)
check("入口支持 --check-deps", "--check-deps" in src)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("单文件版全部通过 ✔")
