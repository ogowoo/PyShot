# -*- coding: utf-8 -*-
"""启动不能被界面初始化卡住（本机实测过 21 秒空白）。

背景（用户日志 + 本机复现）：
  `环境·屏幕`(231ms) 之后空白 21.6 秒才出现 `预热·开始`。根因是 main() 在
  app.exec() **之前**同步做 restore_session() —— 那要建编辑器窗口，而进程内
  "第一次用 Qt 界面"有几笔一次性开销：
    · 第一次量文字（字体库 + 中文回退族扫描）   本机 1.7~7.8 s
    · 第一次建编辑器标签页（标签+关闭按钮+画布） 本机 3.3~4.4 s
  这些开销落在 exec() 之前，就把托盘图标和全局热键**一起**卡住了。

现在的约定（本文件锁住它们）：
  1) 正常启动只到"托盘/热键就绪"就进事件循环，恢复会话延后（schedule_boot）
  2) 全局字体用 app.setFont()，不再用 QSS 的 `* { font-family: ... }`
     （后者让中文只能走回退扫描，实测 7.8s → 1.9s）
  3) _warm_ui() 预热时建的隐藏编辑器**不能**留在 editors 列表里
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 注意：语言要用 set_language() 现切，所以**不能**设 PYSHOT_LANG
# （它的优先级高于 set_language，会把这里的两条断言都钉死）
os.environ.pop("PYSHOT_LANG", None)
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

# 会话与设置都隔离到临时目录，不碰用户数据
_tmp = Path(tempfile.mkdtemp(prefix="pyshot_startup_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

import main as m
import style

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 字体策略：不再用 QSS 的 `*` 规则设字体 ----------
star_font = [ln for ln in style.APP_QSS.splitlines()
             if ln.strip().startswith("*") and "font" in ln]
check("**QSS 里不再有 `* { font-family... }`**（那是 7.8s 的元凶）",
      not star_font, str(star_font))

i18n.set_language("zh_CN", persist=False)
style.apply_font(app)
check("中文界面用中文字体（避免回退扫描）",
      app.font().family() == "Microsoft YaHei UI", app.font().family())
i18n.set_language("en", persist=False)
style.apply_font(app)
check("英文界面用 Segoe UI", app.font().family() == "Segoe UI",
      app.font().family())
check("字号仍是 13px", app.font().pixelSize() == 13, app.font().pixelSize())
i18n.set_language("zh_CN", persist=False)
style.apply_font(app)


# ---------- 2) 启动顺序：托盘先就绪，恢复会话延后 ----------
class FakeScreen:
    def name(self):
        return "s"

    def geometry(self):
        return QRect(0, 0, 1920, 1080)

    def devicePixelRatio(self):
        return 1.0

    def grabWindow(self, w=0):
        p = QPixmap(20, 20)
        p.fill(QColor("white"))
        return p


class FakeGui:
    def screens(self):
        return [FakeScreen()]

    primaryScreen = screenAt = lambda self, *a: self.screens()[0]


class FakeTray:
    activated = type("S", (), {"connect": lambda self, f: None})()

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, t):
        pass

    def show(self):
        pass

    def showMessage(self, *a):
        pass


class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self.snipper = None
        self.scroller = None
        self.editors = []
        self._overlays = []
        m.QGuiApplication = FakeGui()
        self._build_tray_menu()


p = Probe()
called = []
p.restore_session = lambda: (called.append(1), 0)[1]

p.schedule_boot(delay_ms=100)
check("**schedule_boot 之后没有同步建编辑器**（启动不被卡住）",
      not called and not p.editors, f"called={called} editors={p.editors}")
QTest.qWait(400)
app.processEvents()
check("事件循环跑起来之后才恢复会话", len(called) == 1, f"called={len(called)}")


# ---------- 3) 预热：付掉一次性开销，但不留下多余窗口 ----------
p2 = Probe()
before = len(p2.editors)
t_ok = True
try:
    p2._warm_ui()
except Exception as e:                                     # noqa: BLE001
    t_ok = False
    print("   _warm_ui 异常:", e)
check("_warm_ui() 能跑通", t_ok)
check("**预热建的隐藏编辑器不会留在 editors 里**",
      len(p2.editors) == before, f"{before} → {len(p2.editors)}")

# 预热之后建编辑器应该很快（这里只断言"能建出来且不报错"，不断言绝对耗时）
p3 = Probe()
p3._warm_ui()
from editor import EditorWindow

pix = QPixmap(80, 60)
pix.fill()
ed = EditorWindow()
ed.add_canvas(pix, "t")
check("预热后建编辑器 + 加画布正常", ed.tabs.count() == 1, str(ed.tabs.count()))
ed.close()

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("启动顺序与字体策略测试通过 ✔")
