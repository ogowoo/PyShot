# -*- coding: utf-8 -*-
"""延迟截图：用来截右键菜单 / 下拉框。

用户反馈："现在的快捷键在截一些快捷菜单的时候会截不到。"

原因：弹出菜单在所属窗口**失去激活**的瞬间就关了。旧顺序是
"按热键 → 一直到抓屏前才最小化编辑器"，这一最小化就把菜单关掉，
抓到的图里自然没有菜单。

修好的顺序（本文件重点锁这个）：
    按热键 → ①先把窗口收好 → ②等 N 秒（用户重新打开菜单）→ ③到点只抓屏
其中 ③ 阶段**不能**再有任何窗口操作 —— 这是能否截到菜单的分水岭。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_delay_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

import style

style.apply_theme(app)

import editor as ed_mod
import main as m

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


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


class FakeOverlay:
    """假装是全屏覆盖层：只记录被启动过。"""

    def __init__(self, events):
        self.events = events
        self._active = True

    def start(self, mode):
        self.events.append("overlay.start")

    def bg_report(self):
        return "fake"

    def set_point_hole(self, region):
        pass


class Probe(m.PyShotApp):
    """只测"触发 → 延迟 → 抓屏"这条链路，不碰真实覆盖层。"""

    def __init__(self):
        self.app = app
        self.tray_available = True
        self.hotkey_text = "Ctrl+Alt+X"
        self.full_hotkey_text = "Ctrl+Alt+F"
        self.tray = FakeTray()
        self.editors = []
        self.snipper = None
        self._overlays = []
        self._scroll_mode = None
        self.events = []          # 记录顺序：prep / snipper / grab
        m.QGuiApplication = FakeGui()

    # --- 记录窗口操作 ---
    def _prepare_capture(self):
        self.events.append("prep")

    def _finish_capture_session(self):
        self.events.append("finish")

    def _ensure_overlays(self):
        self.events.append("overlays")
        ov = FakeOverlay(self.events)
        self._overlays = [ov]
        return [ov]

    def _notify(self, *a):
        self.events.append("notify")

    def _cap_log(self, *a):
        pass

    def _on_snip_done(self):
        pass

    def keep_editor_on_capture(self):
        return True          # 测试里不真去动窗口


scheduled = []
_real_single_shot = m.QTimer.singleShot


def fake_single_shot(ms, fn):
    """记下延迟时长，先不执行（由测试手动触发），避免真的等 3 秒。"""
    scheduled.append((ms, fn))


m.QTimer.singleShot = staticmethod(fake_single_shot)

# ---------- 1) 默认不延迟：立即走原路径 ----------
core = Probe()
scheduled.clear()
m.capture_delay_seconds.__globals__  # noqa: B018  (仅确保可访问)
i18n.set_setting(ed_mod.CAPTURE_DELAY_SETTING, 0)
core.capture_region()
check("不延迟时立即开始截图（没有排定时器）", not scheduled,
      str([ms for ms, _ in scheduled]))
check("不延迟时走的是原始路径（overlays 已起）",
      "overlays" in core.events, str(core.events))

# ---------- 2) 延迟 3 秒：先 prep，再排队，不立即抓屏 ----------
core2 = Probe()
scheduled.clear()
i18n.set_setting(ed_mod.CAPTURE_DELAY_SETTING, 3)
core2.capture_region()
check("**延迟时先做窗口处理（prep 在倒计时之前）**",
      core2.events[:1] == ["prep"], str(core2.events))
check("延迟时不会立刻抓屏", "overlays" not in core2.events, str(core2.events))
check("排定的延迟就是设置的秒数（3000ms）",
      [ms for ms, _ in scheduled] == [3000], str(scheduled))
check("延迟期间给了提示（让用户去打开菜单）", "notify" in core2.events,
      str(core2.events))

# ---------- 3) 到点执行：那一刻不再有任何窗口操作 ----------
prep_before = core2.events.count("prep")
ms, fn = scheduled.pop()
core2.events.clear()
fn()                      # 模拟倒计时到点
check("**到点后不再调用 _prepare_capture（否则又把菜单关了）**",
      core2.events.count("prep") == 0 and prep_before == 1,
      f"到点后事件: {core2.events}")
check("到点确实开始抓屏了", "overlays" in core2.events, str(core2.events))

# ---------- 4) 全屏截图也支持延迟 ----------
core3 = Probe()
scheduled.clear()
core3.capture_fullscreen()
check("全屏截图同样先 prep 再排队",
      core3.events[:1] == ["prep"] and [ms for ms, _ in scheduled] == [3000],
      f"{core3.events} {scheduled}")

# ---------- 5) 取色也支持延迟（菜单里的颜色要先把菜单打开） ----------
core4 = Probe()
scheduled.clear()
core4.pick_color()
check("屏幕取色同样支持延迟",
      [ms for ms, _ in scheduled] == [3000], str(scheduled))

# ---------- 6) _prepare_capture 可重复调用（延迟路径会调用两次，见 main） ----------
from editor import EditorWindow

win = EditorWindow(QPixmap(200, 150))
core5 = Probe()
core5.editors = [win]
core5.keep_editor_on_capture = lambda: False
core5._minimized_by_capture = []
# 用真实的 _prepare_capture
core5._prepare_capture = m.PyShotApp._prepare_capture.__get__(core5)
core5._prepare_capture()
first = list(core5._minimized_by_capture)
core5._prepare_capture()          # 第二次不许把第一次的记录抹掉
check("**重复 prep 不丢待恢复窗口（累加而非覆盖）**",
      core5._minimized_by_capture == first, str(core5._minimized_by_capture))

# ---------- 7) 托盘菜单 / 选项菜单 ----------
core6 = Probe()
core6._build_tray_menu()
delay_menu = [a.menu() for a in core6.menu.actions()
              if a.menu() is not None and a.text() == "延迟截图"]
check("托盘菜单里有「延迟截图」子菜单", len(delay_menu) == 1)
if delay_menu:
    labels = [a.text() for a in delay_menu[0].actions()]
    check("子菜单含关闭与各档位（2/3/5/10 秒）",
          labels == ["不延迟（立即截图）", "2 秒后抓屏", "3 秒后抓屏",
                     "5 秒后抓屏", "10 秒后抓屏"], str(labels))
    check("当前档位被勾选", [a.isChecked() for a in delay_menu[0].actions()]
          == [False, False, True, False, False],
          str([a.isChecked() for a in delay_menu[0].actions()]))

core6._set_capture_delay(5, quiet=True)
check("从托盘改档位会写进设置",
      ed_mod.capture_delay_seconds() == 5, str(ed_mod.capture_delay_seconds()))
check("改档位后勾选跟着走",
      [a.isChecked() for a in delay_menu[0].actions()]
      == [False, False, False, True, False],
      str([a.isChecked() for a in delay_menu[0].actions()]))

win2 = EditorWindow(QPixmap(120, 90))
check("编辑器选项里勾选状态跟着设置（当前 5 秒 = 开）", win2.act_delay.isChecked())
win2.act_delay.setChecked(False)
check("选项里取消勾选 → 设为不延迟", ed_mod.capture_delay_seconds() == 0,
      str(ed_mod.capture_delay_seconds()))
win2.act_delay.setChecked(True)
check("选项里勾上 → 用默认 3 秒", ed_mod.capture_delay_seconds() == 3,
      str(ed_mod.capture_delay_seconds()))

m.QTimer.singleShot = _real_single_shot

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("延迟截图测试通过 ✔")
