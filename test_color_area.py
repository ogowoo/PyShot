# -*- coding: utf-8 -*-
"""颜色区测试：当前颜色 + 色板拼盘。"""
# 测试不碰用户真实的会话缓存（新建编辑器会自动恢复历史，读到真实数据会让
# 断言全乱）。必须在导入 main/session 之前设置。
import tempfile as _tf, os as _os
_os.environ.setdefault("PYSHOT_SESSION_DIR",
                       _tf.mkdtemp(prefix="pyshot_test_session_"))
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from editor import PALETTE, EditorWindow

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


win = EditorWindow(QPixmap(300, 200))
win.resize(900, 600)
win.show()
app.processEvents()

# ---------- 色板拼盘 ----------
check("色板有 20 色（两行拼盘）", len(PALETTE) == 20, str(len(PALETTE)))
check("色板按钮数量与色表一致", len(win.color_buttons) == len(PALETTE),
      f"{len(win.color_buttons)}")
check("色板颜色都是合法色值",
      all(QColor(h).isValid() for h in PALETTE), str(PALETTE[:4]))
check("色板没有重复色", len(set(PALETTE)) == len(PALETTE))

# 点第 5 个色块 → 当前颜色跟着变
target = PALETTE[4]
win.color_buttons[4].click()
app.processEvents()
check("点色板能设置当前颜色",
      win._shared["color"].name().lower() == QColor(target).name().lower(),
      f"{win._shared['color'].name()} vs {target}")
check("当前颜色按钮背景同步",
      QColor(target).name() in win.current_color_btn.styleSheet(),
      win.current_color_btn.styleSheet()[:60])

# ---------- 当前颜色 ----------
check("有当前颜色按钮", hasattr(win, "current_color_btn"))
check("当前颜色按钮可点击（点了会开取色对话框）",
      win.current_color_btn.isEnabled())

# 模拟"拾色器吸到颜色"：set_color 是拾色器走的同一个入口
picked = QColor("#00e676")
win.set_color(picked)
app.processEvents()
check("拾色器取到的颜色会显示在「当前颜色」上",
      QColor("#00e676").name() in win.current_color_btn.styleSheet(),
      win.current_color_btn.toolTip())
check("提示里带上了色值",
      QColor("#00e676").name().lower() in win.current_color_btn.toolTip().lower(),
      win.current_color_btn.toolTip())

# 画布也拿到这个颜色（新画的图形用当前色）
canvas = win.canvas
win.set_tool("rect")
check("画布的当前颜色同步", canvas.color.name().lower()
      == QColor("#00e676").name().lower(), canvas.color.name())

# 切换标签后仍保持（跨标签共享）
win.add_canvas(QPixmap(200, 150))
app.processEvents()
check("新标签沿用当前颜色", win.canvas.color.name().lower()
      == QColor("#00e676").name().lower(), win.canvas.color.name())

# 每个色板按钮的提示就是色值（方便对照）
check("色板按钮提示是色值",
      win.color_buttons[0].toolTip().lower() == PALETTE[0].lower(),
      win.color_buttons[0].toolTip())

# ---------- 4) 大调色板（系统拾色盘风格）----------
from editor import ColorPaletteDialog, palette_colors

big = palette_colors()
check("大调色板色数 >= 80（够用）", len(big) >= 80, str(len(big)))
check("大调色板没有重复色", len(set(big)) == len(big),
      f"{len(big)} vs {len(set(big))}")
check("大调色板颜色都合法", all(QColor(c).isValid() for c in big))
check("大调色板含黑白灰阶",
      "#000000" in big and "#ffffff" in big,
      str([c for c in big if c in ("#000000", "#ffffff")]))

pdlg = ColorPaletteDialog(None, QColor("#e53935"))
check("弹窗列出全部颜色", len(pdlg.buttons) == len(big),
      f"{len(pdlg.buttons)} 个色块")
check("弹窗有「自定义…」（可开系统拾色器）",
      pdlg.btn_custom.text().startswith("自定义"), pdlg.btn_custom.text())
target2 = big[40]
pdlg.buttons[40].click()
check("点弹窗色块即选中并关闭",
      pdlg.result() == 1
      and pdlg.selected().name().lower() == QColor(target2).name().lower(),
      f"{pdlg.selected().name()} vs {target2}")
pdlg.deleteLater()

check("顶栏有「更多颜色」入口（打开大调色板）",
      any("更多颜色" in b.toolTip()
          for b in win.findChildren(type(win.color_buttons[0]))), "")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("颜色区测试通过 ✔")
