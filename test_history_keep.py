# -*- coding: utf-8 -*-
"""历史标签的保留：截多次 → 关掉编辑器窗口 → 再截 → 历史必须还在。

用户的实际路径：Ctrl+Alt+X 连截几次（标签都在）→ 手动点编辑器右上角关闭按钮
→ 再截图，之前的标签就没了。要求：主进程退出前一直保留，退出后下次打开也还在。

根因：open_editor()（截图后打开编辑器）从不恢复历史，只有「显示编辑器」会；
更糟的是新编辑器只带 1 个标签，随后的保存会把缓存也冲成 1 张，连重启都找不回。
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

from PySide6.QtCore import QRectF
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


root = Path(tempfile.mkdtemp(prefix="pyshot_hist_"))
session.SESSION_DIR = root / "session"
session.SESSION_SETTINGS_PATH = root / "settings.json"

import main as m


class P(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.editors = []
        self.hotkey_text = "Ctrl+Alt+X"


def pix(w, h, color):
    p = QPixmap(w, h)
    p.fill(QColor(color))
    return p


# ---------- 1) 连截三次 ----------
p = P()
for i, c in enumerate(("#3355cc", "#33cc55", "#cc3355")):
    p.open_editor(pix(300 + i * 10, 200 + i * 10, c))
ed = p.editors[0]
ed.canvas.shapes.append(RectShape(QColor("red"), 3, QRectF(5, 5, 40, 40)))
check("连截三次有 3 个标签", ed.tabs.count() == 3, str(ed.tabs.count()))
p.save_session_now()
check("缓存里也有 3 个", len(session.load_session()) == 3,
      str(len(session.load_session())))

# ---------- 2) 手动关闭编辑器窗口后再截图：历史必须还在 ----------
ed.close()
app.processEvents()
check("关掉窗口后没有编辑器窗口", len(p.editors) == 0)
check("关窗口不会清掉缓存", len(session.load_session()) == 3,
      str(len(session.load_session())))

p.open_editor(pix(360, 230, "#cccc33"))
ed2 = p.editors[0]
check("再截一张后 = 历史 3 + 新 1 = 4 个标签", ed2.tabs.count() == 4,
      str(ed2.tabs.count()))
_shape_counts = [len(ed2.tabs.widget(i).widget().shapes) for i in range(ed2.tabs.count())]
check("历史里的标注也还在（在第 3 个标签上）",
      _shape_counts[2] == 1, str(_shape_counts))
p.save_session_now()
check("缓存没有被冲成 1 个", len(session.load_session()) == 4,
      str(len(session.load_session())))

# ---------- 3) 主进程退出后再打开：上次的标签还在 ----------
p.save_session_now()                      # 模拟退出时的保存
p2 = P()
n = p2.restore_session()
check("重启后恢复 4 张", n == 4, str(n))
check("重启后的标签数正确", p2.editors[0].tabs.count() == 4,
      str(p2.editors[0].tabs.count()))
check("重启后标注也在",
      any(len(p2.editors[0].tabs.widget(i).widget().shapes) == 1
          for i in range(4)))

# ---------- 4) 再关一次窗口 + 再截，仍然累积 ----------
p2.editors[0].close()
app.processEvents()
p2.open_editor(pix(380, 240, "#33cccc"))
check("第二次关窗口后再截 = 5 个标签", p2.editors[0].tabs.count() == 5,
      str(p2.editors[0].tabs.count()))

# ---------- 5) 用户主动关标签：这时允许缓存减少 ----------
p2.editors[0].close_tab(0)
app.processEvents()
p2.save_session_now()
check("用户主动关标签后缓存相应减少", len(session.load_session()) == 4,
      str(len(session.load_session())))

# ---------- 6) 「显示编辑器」路径同样保留历史 ----------
p3 = P()
p3.open_editor(pix(300, 200, "#888888"))
p3.save_session_now()
p3.editors[0].close()
app.processEvents()
p3.show_editor()
check("关窗口后点显示编辑器，历史也在", p3.editors[0].tabs.count() >= 5,
      str(p3.editors[0].tabs.count()))

session.clear_session()
shutil.rmtree(root, ignore_errors=True)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("历史标签保留测试通过 ✔")
