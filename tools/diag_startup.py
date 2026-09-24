# -*- coding: utf-8 -*-
"""启动计时（新版顺序）：托盘/热键先进事件循环，预热与恢复会话随后进行。

上一版的毛病：main() 在 app.exec() **之前**同步做 restore_session（建编辑器窗口
→ 触发进程内第一次文字排版，本机 2-5 秒），把托盘和全局热键一起卡住。

本脚本复刻新顺序并逐步计时。会话缓存复制到临时目录；编辑器窗口不真的显示
（show/show_raise 打桩），避免打扰正在用电脑的人。
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["PYSHOT_DEBUG"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_real = Path.home() / ".pyshot" / "session"
_tmp = Path(tempfile.mkdtemp(prefix="pyshot_startdiag_")) / "session"
if _real.exists():
    shutil.copytree(_real, _tmp)
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp)

T0 = time.perf_counter()


def mark(label, **kw):
    print(f"  +{(time.perf_counter() - T0) * 1000:8.1f} ms  {label}", flush=True)


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

mark("PySide6 导入完成")
from style import apply_theme

app = QApplication(sys.argv)
apply_theme(app)
mark("QApplication + 主题")

from main import PyShotApp

core = PyShotApp(app)
mark("PyShotApp()（托盘/热键就绪）")

from diag import dump_env

dump_env()
mark("dump_env()  ← 旧日志里从这里开始 blank 21 秒")

# 新顺序：不再同步恢复，直接进事件循环
QTimer.singleShot(0, lambda: mark("**事件循环开始跑**（此刻起托盘/热键可用）"))

_warm, _boot = core._warm_ui, core.boot_restore


def warm():
    _warm()
    mark("**预热结束**")


def boot():
    _boot()
    mark("**恢复会话 + 就绪提示结束**")
    app.quit()


core._warmup, core.boot_restore = warm, boot
QTimer.singleShot(150, core._warmup)
QTimer.singleShot(350, core.boot_restore)
# 编辑器窗口不真显示，别打扰用户
try:
    from editor import EditorWindow

    EditorWindow.show = lambda self: None
    EditorWindow.raise_ = lambda self: None
    EditorWindow.activateWindow = lambda self: None
except Exception as e:                                     # noqa: BLE001
    print("打桩失败:", e)

mark("准备进 app.exec()")
app.exec()
mark("app.exec() 返回")
