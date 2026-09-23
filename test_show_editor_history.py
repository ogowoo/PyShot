# -*- coding: utf-8 -*-
"""「显示编辑器」不能把历史弄丢。

用户反馈：点「显示编辑器」时，旧的（历史）截图不见了。
原因：编辑器窗口关掉后 editors 就空了，再点「显示编辑器」会新建一个**空**窗口，
而会话缓存里的截图没有被放回来。
"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
sys.path.insert(0, r"C:\Explorer\pyshot")

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import session
from shapes import RectShape

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


root = Path(tempfile.mkdtemp())
session.SESSION_DIR = root / "session"
session.SESSION_SETTINGS_PATH = root / "settings.json"

import main as m


class P(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.editors = []
        self.hotkey_text = "Ctrl+Alt+X"


def pix(w=300, h=200, color="#3366cc"):
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


# ---------- 1) 关掉窗口后再点「显示编辑器」，历史要回来 ----------
p = P()
p.open_editor(pix())
p.editors[0].canvas.shapes.append(RectShape(QColor("red"), 3, QRectF(5, 5, 40, 40)))
p.open_editor(pix(400, 300))
check("先有 2 个标签", p.editors[0].tabs.count() == 2)
p.save_session_now()
check("会话已存盘", session.has_session() is True)

p.editors[0].close()                       # 用户关掉编辑器窗口
app.processEvents()
check("关掉窗口后没有编辑器窗口了", len(p.editors) == 0)
check("关窗口不会把会话缓存清掉", session.has_session() is True)

p.show_editor()
app.processEvents()
check("点显示编辑器又开出一个窗口", len(p.editors) == 1)
check("**历史被放回来了**（不是空白窗口）", p.editors[0].tabs.count() == 2,
      f"{p.editors[0].tabs.count()} 个标签")
check("恢复的标注也在",
      len(p.editors[0].tabs.widget(0).widget().shapes) == 1)

# ---------- 2) 关窗口那一刻立刻存盘（不等防抖）----------
p2 = P()
p2.open_editor(pix(320, 240, "#cc3333"))
p2.editors[0].canvas.shapes.append(
    RectShape(QColor("blue"), 3, QRectF(9, 9, 30, 30)))
p2.editors[0].close()                      # 刚截完就关窗口（防抖还没触发）
app.processEvents()
loaded = session.load_session()
check("刚截完就关窗口，也会立刻存下来（不等 1.5 秒防抖）",
      len(loaded) >= 1, f"{len(loaded)} 个标签")
check("存下来的标注也在",
      any(len(t["shapes"]) >= 1 for t in loaded), str([len(t["shapes"]) for t in loaded]))

# ---------- 3) 多个窗口时，优先显示有内容的那个 ----------
p3 = P()
p3.open_editor(pix())                      # 有内容
p3.show_editor()                           # 再点一次（复用它）
# 新建编辑器现在会**自动恢复**历史（关窗口后再截图也不会丢），
# 所以这里改为验证"新窗口也会带出历史"
p3._create_editor()
app.processEvents()
check("新窗口也会带出历史（不会得到空窗口）",
      p3.editors[-1].tabs.count() > 0, f"{p3.editors[-1].tabs.count()} 个标签")
with_tabs = [e for e in p3.editors if e.tabs.count() > 0]
p3.show_editor()
app.processEvents()
check("有内容的窗口优先被选中（不会显示到空窗口）",
      p3._last_shown_editor is with_tabs[-1],
      f"选中的标签数 = {p3._last_shown_editor.tabs.count()}")

# ---------- 4) 用户关光所有标签（窗口还在）→ 缓存应当清掉 ----------
p4 = P()
p4.open_editor(pix())
p4.save_session_now()
check("先有会话", session.has_session() is True)
while p4.editors[0].tabs.count() > 0:      # 关光所有标签（窗口还在）
    p4.editors[0].close_tab(0)
app.processEvents()
p4.save_session_now()
check("关光标签后缓存被清掉（窗口还在 → 是真的清空）",
      session.has_session() is False)

# ---------- 5) 没有会话时点显示编辑器：给空白窗口，不报错 ----------
session.clear_session()
p5 = P()
p5.show_editor()
app.processEvents()
check("没有会话时给一个空白编辑器", len(p5.editors) == 1
      and p5.editors[0].tabs.count() == 0)

session.SESSION_DIR = session.SESSION_DIR  # 还原由外层负责
shutil.rmtree(root, ignore_errors=True)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("显示编辑器 历史保留 测试通过 ✔")
