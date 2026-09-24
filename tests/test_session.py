# -*- coding: utf-8 -*-
"""会话缓存测试：关软件再开，上次的截图还在（但不需要用户保存）。

关键点：
- 存的不是"拼好的图"，而是**底图 + 标注**，恢复后还能继续编辑
- 只保留最后一次会话；关掉开关或清除后不再恢复
- 文件都在 ~/.pyshot/session/ 缓存里，不碰用户目录
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import json
import pathlib
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import session
from editor import EditorWindow
from shapes import (ArrowShape, EllipseShape, LineShape, MosaicShape, PenShape,
                    RectShape, StepShape, TextShape)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# 把缓存目录和设置都指到临时位置，别动用户真实数据
tmp_root = Path(tempfile.mkdtemp(prefix="pyshot_session_"))
orig_dir, orig_settings = session.SESSION_DIR, session.SESSION_SETTINGS_PATH
session.SESSION_DIR = tmp_root / "session"
session.SESSION_SETTINGS_PATH = tmp_root / "settings.json"


def make_editor():
    pix = QPixmap(400, 300)
    pix.fill(QColor("#4c9aff"))
    return EditorWindow(pix)


# ---------- 1) 保存 → 读取round trip ----------
win = make_editor()
canvas = win.canvas
canvas.shapes.append(RectShape(QColor("#e53935"), 4, QRectF(20, 30, 100, 60)))
canvas.shapes.append(EllipseShape(QColor("#43a047"), 3, QRectF(150, 40, 80, 80)))
canvas.shapes.append(LineShape(QColor("#1e88e5"), 2, QPointF(10, 10), QPointF(90, 90)))
canvas.shapes.append(ArrowShape(QColor("#8e24aa"), 3, QPointF(5, 5), QPointF(60, 70)))
canvas.shapes.append(PenShape(QColor("#fb8c00"), 3,
                             [QPointF(1, 1), QPointF(2, 2), QPointF(3, 4)]))
canvas.shapes.append(StepShape(QColor("#fdd835"), 3, QPointF(200, 200), 3, 0, 40))
canvas.shapes.append(TextShape(QColor("#ffffff"), 2, QPointF(50, 200), "步骤一", 22))
canvas.shapes.append(MosaicShape(QColor("#000000"), 4, QRectF(200, 100, 60, 40)))

tabs = win.session_tabs()
check("导出标签内容", len(tabs) == 1 and len(tabs[0]["shapes"]) == 8,
      f"{len(tabs)} 个标签 / {len(tabs[0]['shapes'])} 个图形")

check("保存会话成功", session.save_session(tabs) is True)
check("缓存目录里确有文件", (session.SESSION_DIR / "session.json").exists())
check("底图存成 PNG", (session.SESSION_DIR / "tab0.png").exists())
check("has_session() 正确", session.has_session() is True)

loaded = session.load_session()
check("读回一个标签", len(loaded) == 1, str(len(loaded)))
check("底图尺寸保住", loaded[0]["pixmap"].width() == 400
      and loaded[0]["pixmap"].height() == 300)
check("标注数量保住", len(loaded[0]["shapes"]) == 8,
      str([type(s).__name__ for s in loaded[0]["shapes"]]))
names = [type(s).__name__ for s in loaded[0]["shapes"]]
for want in ("RectShape", "EllipseShape", "LineShape", "ArrowShape",
             "PenShape", "StepShape", "TextShape", "MosaicShape"):
    check(f"恢复了 {want}", want in names, str(names))

# 细节也要对
rect = [s for s in loaded[0]["shapes"] if type(s).__name__ == "RectShape"][0]
check("矩形位置/颜色/线宽都对",
      abs(rect.rect.x() - 20) < 0.01 and abs(rect.rect.width() - 100) < 0.01
      and rect.color.name() == "#e53935" and int(rect.width) == 4,
      f"{rect.rect} {rect.color.name()} {rect.width}")
txt = [s for s in loaded[0]["shapes"] if type(s).__name__ == "TextShape"][0]
check("文字内容与字号对", txt.text == "步骤一" and int(txt.font_size) == 22,
      f"{txt.text!r} {txt.font_size}")
step = [s for s in loaded[0]["shapes"] if type(s).__name__ == "StepShape"][0]
check("序号数字与直径对", int(step.number) == 3 and abs(step.diameter - 40) < 0.1,
      f"{step.number} {step.diameter}")
pen = [s for s in loaded[0]["shapes"] if type(s).__name__ == "PenShape"][0]
check("画笔点数对", len(pen.points) == 3, str(len(pen.points)))

# ---------- 2) 恢复进新编辑器（模拟重启）----------
win2 = EditorWindow()
win2.restore_session(loaded)
check("恢复后有一个标签", win2.tabs.count() == 1, str(win2.tabs.count()))
check("恢复后有画布", win2.canvas is not None)
check("恢复的标注数量对", len(win2.canvas.shapes) == 8,
      str(len(win2.canvas.shapes)))
check("恢复后不再显示空状态", win2.stack.currentWidget() is win2.tabs)
check("恢复后能继续编辑（导出结果可渲染）",
      win2.canvas.render_result().width() > 0)

# ---------- 3) 只保留最后一次会话 ----------
win3 = make_editor()
session.save_session(win3.session_tabs())
files = sorted(p.name for p in session.SESSION_DIR.iterdir())
check("再次保存后只有一份会话", files.count("session.json") == 1, str(files))
check("旧标签文件被清掉（没越积越多）",
      not (session.SESSION_DIR / "tab1.png").exists(), str(files))
check("读回的仍是 1 个标签", len(session.load_session()) == 1)

# ---------- 4) 空内容 → 清掉会话 ----------
session.save_session([])
check("没有标签时清掉会话", not session.has_session())
check("清掉后读回为空", session.load_session() == [])

# ---------- 5) 开关与清除 ----------
check("默认开启恢复", session.session_enabled() is True)
session.set_session_enabled(False)
check("可以关掉恢复", session.session_enabled() is False)
session.set_session_enabled(True)
check("可以再打开", session.session_enabled() is True)

win4 = make_editor()
session.save_session(win4.session_tabs())
check("清除前有会话", session.has_session() is True)
session.clear_session()
check("清除后没有会话", session.has_session() is False)

# ---------- 6) 坏文件不影响启动 ----------
session.SESSION_DIR.mkdir(parents=True, exist_ok=True)
(session.SESSION_DIR / "session.json").write_text("{ 坏掉的 json", encoding="utf-8")
check("会话文件损坏时安全返回空", session.load_session() == [])
(session.SESSION_DIR / "session.json").write_text(
    json.dumps({"version": 1, "tabs": [{"file": "不存在.png", "shapes": []}]}),
    encoding="utf-8")
check("底图丢失时跳过该标签", session.load_session() == [])

# ---------- 7) 缓存目录默认在用户目录下，不是工作目录 ----------
# 运行时代码在项目根（测试在 tests/ 下），所以用 HERE 而不是 __file__ 的目录
_src = (pathlib.Path(HERE) / "session.py").read_text(encoding="utf-8")
check("默认缓存在 ~/.pyshot/session（不会污染当前目录）",
      'Path.home() / ".pyshot" / "session"' in _src, "session.py 默认路径")

session.SESSION_DIR, session.SESSION_SETTINGS_PATH = orig_dir, orig_settings
shutil.rmtree(tmp_root, ignore_errors=True)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("会话缓存测试通过 ✔")
