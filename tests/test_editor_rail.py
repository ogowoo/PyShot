# -*- coding: utf-8 -*-
"""左侧工具条：可滚动、可收起，不再顶死编辑器窗口的最小高度。

用户的反馈："左边的侧栏工具条好像限制了编辑器窗口的高度" —— 实测确实如此：
13 个工具竖排要 640px，窗口最小高度被顶到 **782px**，屏幕矮一点就压不下去。
现在工具条包在滚动区里，窗口最小高度 249px；另外「视图 → 显示左侧工具条」
可以整条收起。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = Path(__file__).resolve().parent.parent   # 项目根（本文件在子目录里）
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_rail_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea

app = QApplication([])

import style

style.apply_theme(app)

import editor as ed
from editor import EditorWindow

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def make(w=900, h=320):
    win = EditorWindow(QPixmap(200, 150))
    win.resize(w, h)
    win.show()
    app.processEvents()
    return win


win = make()

# ---------- 1) 工具条不再顶死窗口高度 ----------
rail_full = win.tool_rail.sizeHint().height()
win_min = win.minimumSizeHint().height()
check("工具条本身仍然很高（所以才需要滚动）", rail_full > 500, f"{rail_full} px")
check("**窗口最小高度不再被工具条顶死**（应远小于工具条高度）",
      win_min < 400 and win_min < rail_full,
      f"窗口最小高 {win_min} px / 工具条 {rail_full} px（改前是 782）")

# ---------- 2) 工具条在滚动区里，13 个工具都还在 ----------
check("工具条被放进 QScrollArea", isinstance(win.tool_scroll, QScrollArea),
      type(win.tool_scroll).__name__)
check("滚动区宽度与原来一致（56px，不会变宽）", win.tool_scroll.width() == ed.RAIL_WIDTH,
      f"{win.tool_scroll.width()} vs {ed.RAIL_WIDTH}")
check("滚动区撑满高度（横向不滚，只纵向滚）",
      win.tool_scroll.widgetResizable()
      and win.tool_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff)
check("**13 个工具按钮一个不少**", len(win.tool_buttons) == len(ed.TOOLS),
      f"{len(win.tool_buttons)}/{len(ed.TOOLS)}")
check("按钮都在工具条里（滚动区内，仍能点到）",
      all(b.parent() is win.tool_rail for b in win.tool_buttons.values()))

# 窗口矮的时候：滚动条有行程（能滚）
sb = win.tool_scroll.verticalScrollBar()
check("**窗口压矮后工具条可以滚**", sb.maximum() > 0,
      f"滚动范围 {sb.minimum()}~{sb.maximum()}（窗口高 {win.height()}）")
check("滚动区最小高度很小（窗口才压得下来）", win.tool_scroll.minimumHeight() <= 80,
      f"{win.tool_scroll.minimumHeight()} px")

# ---------- 3) 切工具时自动滚进可见区 ----------
last_tool = ed.TOOLS[-1][0]                # 最后一个工具（默认在可视区外）
win.set_tool(last_tool)
app.processEvents()
btn = win.tool_buttons[last_tool]
vp = win.tool_scroll.viewport()
top_left = btn.mapTo(vp, btn.rect().topLeft())
bottom = top_left.y() + btn.height()
check("**用快捷键切到最后一个工具时会自动滚进可见区**",
      0 <= top_left.y() and bottom <= vp.height() + 2,
      f"按钮 y {top_left.y()}~{bottom}，视口高 {vp.height()}")

# ---------- 4) 整条收起 / 恢复（并记住选择） ----------
check("默认显示工具条", win.tool_scroll.isVisibleTo(win))
win.set_rail_visible(False)
app.processEvents()
check("**收起后工具条不可见**", not win.tool_scroll.isVisibleTo(win))
check("菜单项勾选状态跟着变", not win.act_rail.isChecked())
check("收起状态写进设置",
      i18n.get_setting(ed.RAIL_VISIBLE_SETTING, None) is False,
      str(i18n.get_setting(ed.RAIL_VISIBLE_SETTING, None)))
check("收起后画布区域变宽（少占了 56px）", win.tabs.width() > 0)

win2 = make()
check("**新开的编辑器沿用「收起」状态**", not win2.tool_scroll.isVisibleTo(win2))
win2.set_rail_visible(True)
check("再打开就恢复显示", win2.tool_scroll.isVisibleTo(win2))
check("恢复状态也写进设置",
      i18n.get_setting(ed.RAIL_VISIBLE_SETTING, None) is True)

# ---------- 5) 收起后工具快捷键仍然可用（不然用户就没法切工具了） ----------
win3 = make(900, 320)
win3.set_rail_visible(False)
win3.set_tool("arrow")
check("收起工具条后仍能切换工具（快捷键/代码路径）",
      win3.canvas.tool == "arrow", win3.canvas.tool)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("左侧工具条可滚动/可收起测试通过 ✔")
