# -*- coding: utf-8 -*-
"""版本号维护：只有一个地方定义，各入口显示的是同一个值。

背景：`editor.py` 里曾经写死 `APP_VERSION = "2.6"`，而 git 里程碑标签已经到
`v2.15-qt` —— 「关于」对话框跟实际发布版本对不上，用户报版本号时没法核对。
现在版本号只在 `version.py` 定义，本文件盯着这件事不许再飘。
"""
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_tmp = Path(tempfile.mkdtemp(prefix="pyshot_ver_"))
os.environ["PYSHOT_SESSION_DIR"] = str(_tmp / "session")

import i18n

i18n.SETTINGS_PATH = _tmp / "settings.json"
i18n.reset_cache()

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from version import APP_VERSION, VERSION_TITLE

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 版本号格式 ----------
check("版本号形如 MAJOR.MINOR[.PATCH]",
      bool(re.fullmatch(r"\d+\.\d+(\.\d+)?", APP_VERSION)), APP_VERSION)
check("本版主题不为空（便于用户确认拿到的是哪版）",
      bool(VERSION_TITLE.strip()), VERSION_TITLE)

# ---------- 2) 只有 version.py 定义它 ----------
SOURCES = [p for p in HERE.glob("*.py")
           if p.name not in ("version.py", "PyShot.py")   # PyShot.py 是生成物
           and not p.name.startswith("tk_")]
others = []
for p in SOURCES:
    text = p.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r'^\s*APP_VERSION\s*=\s*["\']', line):
            others.append(f"{p.name}:{i}")
check("**版本号只在 version.py 定义**（别处不许再写死）",
      not others, str(others))

# ---------- 3) 各入口显示的就是这个版本 ----------
import editor as ed_mod
import main as m

check("editor.APP_VERSION 来自 version.py", ed_mod.APP_VERSION == APP_VERSION,
      ed_mod.APP_VERSION)
check("编辑器「关于」文案里带版本号",
      APP_VERSION in i18n.tr(
          "PyShot {} — {}\n仿 FastStone Capture 的截图与标注工具\n\n"
          "托盘右键：区域截图 / 全屏截图 / 滚动长截图 / 屏幕取色 / 贴图\n"
          "编辑器：多标签标注 · 粘贴拼图 · 水印 · 加边框（含手撕纸）· 三语界面",
          APP_VERSION, VERSION_TITLE))

# 真正打开「关于」对话框，确认它带出版本号（打桩 QMessageBox.about）
shown = {}
_real_about = ed_mod.QMessageBox.about
ed_mod.QMessageBox.about = lambda parent, title, text: shown.update(
    title=title, text=text)
try:
    win = ed_mod.EditorWindow(QPixmap(120, 90))
    win.show_about()
finally:
    ed_mod.QMessageBox.about = _real_about
check("**「关于」对话框里显示当前版本**",
      APP_VERSION in shown.get("text", ""), shown.get("text", "")[:40])
check("「关于」对话框标题正常", "PyShot" in shown.get("title", ""),
      shown.get("title", ""))

# --check-deps 的报告也带版本号（用户贴日志时能一眼看出是哪版）
import bootstrap

check("--check-deps 报告里带版本号", APP_VERSION in bootstrap.deps_report(),
      bootstrap.deps_report().splitlines()[0])

# ---------- 4) 单文件版与源码同版本 ----------
single = HERE / "PyShot.py"
if single.exists():
    head = single.read_text(encoding="utf-8").splitlines()[:12]
    head_text = "\n".join(head)
    check("**单文件版文件头写着同一个版本**",
          f"PyShot {APP_VERSION}" in head_text,
          [ln for ln in head if "PyShot" in ln][:1])
    check("单文件版文件头带本版主题",
          VERSION_TITLE in head_text,
          [ln for ln in head if "主题" in ln][:1])
    # 单文件里的 APP_VERSION 赋值也必须与 version.py 一致
    m2 = re.search(r'^APP_VERSION = "([^"]+)"', single.read_text(encoding="utf-8"),
                   re.M)
    check("单文件里内嵌的版本号一致",
          bool(m2) and m2.group(1) == APP_VERSION,
          m2.group(1) if m2 else "没找到")
else:
    print("NOTE 还没有生成 PyShot.py，跳过单文件检查")

# ---------- 5) 版本相关字符串三语齐全 ----------
for _key in ("浮动粘贴 + 编辑增强 + 启动提速",):
    row = i18n.TABLE.get(_key)
    check(f"版本主题已翻译：{_key}", bool(row and row[0] and row[1]), str(row))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("版本号一致性测试通过 ✔")
