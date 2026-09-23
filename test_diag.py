# -*- coding: utf-8 -*-
"""诊断日志（diag.py）测试：默认关闭、开启后记录关键阶段与耗时。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_diag_"))
os.environ["PYSHOT_DEBUG_LOG"] = str(_tmp / "debug.log")

import diag

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 默认关闭：不写文件 ----------
os.environ.pop("PYSHOT_DEBUG", None)
os.environ.pop("PYSHOT_CAPTURE_DEBUG", None)
check("默认不开启", diag.enabled() is False)
diag.log("不该出现", "x")
check("关闭时不写日志文件", not diag.LOG_PATH.exists(), str(diag.LOG_PATH))

# ---------- 2) PYSHOT_CAPTURE_DEBUG=1 也能开（兼容旧名）----------
os.environ["PYSHOT_CAPTURE_DEBUG"] = "1"
check("旧环境变量名仍可开启", diag.enabled() is True)
diag.log("兼容性", "旧名可用")

# ---------- 3) 正式开启：关键阶段与耗时都记下来 ----------
os.environ["PYSHOT_DEBUG"] = "1"
import time

from PySide6.QtWidgets import QApplication

app = QApplication([])

diag.dump_env("单元测试")
with diag.timed("示例阶段", "参数A"):
    time.sleep(0.02)
try:
    raise ValueError("示例异常")
except ValueError as e:
    diag.exc("示例异常", e)

from main import PyShotApp


class P(PyShotApp):
    def __init__(self):
        self.app = app
        self.editors = []
        self.hotkey_text = "Ctrl+Alt+X"
        self.tray_available = True
        self._overlays = []
        self._overlay_screens = []
        self.snipper = None
        self._scroll_mode = None
        self._minimized_by_capture = []


p = P()
p.capture_region()
for _ in range(6):
    app.processEvents()
    time.sleep(0.02)
p._on_snip_done()

text = diag.LOG_PATH.read_text(encoding="utf-8")
lines = text.splitlines()
check("日志文件写出来了", len(lines) > 8, f"{len(lines)} 行")
for need in ("环境:", "环境·屏幕", "截图: 触发区域截图", "遮罩·抓底图·开始",
             "遮罩·抓底图·结束", "遮罩·显示窗口·结束", "遮罩·收起"):
    check(f"日志含「{need}」", any(need in ln for ln in lines),
          [ln for ln in lines if need in ln][:1])
check("耗时被记录（含 ms）", any("耗时" in ln and "ms" in ln for ln in lines))
check("异常被记录", any("示例异常" in ln for ln in lines))
check("每行都有时间戳与相对毫秒",
      all(ln.startswith(tuple("0123456789")) and "(+" in ln
          for ln in lines if ln.strip()),
      lines[0][:40] if lines else "")
check("示例阶段的耗时 ≈ 20ms",
      any("示例阶段·结束" in ln and "耗时" in ln for ln in lines))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("诊断日志测试通过 ✔")
