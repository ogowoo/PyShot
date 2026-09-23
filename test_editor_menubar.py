# -*- coding: utf-8 -*-
"""编辑器菜单栏 + 空白编辑器 测试。

重点：
- 托盘「显示编辑器」在没有任何窗口时，**直接开一个空白编辑器**，
  不再弹"打开图片"文件对话框
- 空白编辑器可用：空状态提示 + 依赖图片的菜单项置灰
- 菜单栏结构完整，关键菜单项真的接了对应动作
- 从「文件 → 打开图片」能加标签，随后菜单项恢复可用
"""
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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

app = QApplication([])

import main as m
from editor import EditorWindow

# 会话缓存要隔离到临时目录：show_editor 现在会恢复上次的截图，
# 否则测试会去读用户真实的缓存、断言全乱（而且不该动用户的文件）
import tempfile as _tempfile
from pathlib import Path as _Path
import session as _session
_tmp = _Path(_tempfile.mkdtemp(prefix="pyshot_menubar_"))
_session.SESSION_DIR = _tmp / "session"
_session.SESSION_SETTINGS_PATH = _tmp / "settings.json"
_session.clear_session()

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 显示编辑器：直接开空白窗口，不弹文件对话框 ----------
class Probe(m.PyShotApp):
    def __init__(self):
        self.app = app
        self.editors = []
        self.hotkey_text = "Ctrl+Alt+X"
        self._asked_for_file = 0
        self.pinned = []

    # 记录是否弹了文件对话框
    def open_image(self):
        self._asked_for_file += 1

    def pin_pixmap(self, pix, pos=None):
        self.pinned.append(pix)


p = Probe()
p.show_editor()
check("没有窗口时也建出了编辑器", len(p.editors) == 1, f"{len(p.editors)} 个")
check("显示编辑器**没有**弹文件对话框", p._asked_for_file == 0,
      f"{p._asked_for_file} 次")
ed = p.editors[0]
check("编辑器窗口可见", ed.isVisible())
check("编辑器里没有标签页（就是空白的）", ed.tabs.count() == 0)
check("空白时显示空状态提示页", ed.stack.currentWidget() is ed.empty_page)

# 再次调用：复用已有窗口，不再新建
p.show_editor()
check("再次显示复用同一个窗口", len(p.editors) == 1, f"{len(p.editors)} 个")

# 空白时依赖图片的菜单项应置灰
disabled = [a.text() for a in ed._needs_canvas if not a.isEnabled()]
check("空白时依赖图片的菜单项都置灰",
      len(disabled) == len(ed._needs_canvas), str(disabled[:4]))

# ---------- 2) 菜单栏结构 ----------
titles = [a.text() for a in ed.menuBar().actions()]
check("菜单栏有六个顶层菜单",
      titles == ["文件", "编辑", "视图", "特效", "选项", "帮助"], str(titles))


def items(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


check("文件菜单项齐全",
      items(ed.menus["file"]) == ["打开图片…", "打开剪贴板图片", "保存",
                                  "关闭当前标签", "退出"],
      str(items(ed.menus["file"])))
check("编辑菜单项齐全",
      items(ed.menus["edit"]) == ["撤销", "重做", "复制到剪贴板", "贴图到屏幕"],
      str(items(ed.menus["edit"])))
check("视图菜单项齐全",
      items(ed.menus["view"]) == ["放大", "缩小", "实际像素 (1:1)", "适应窗口"],
      str(items(ed.menus["view"])))
check("特效菜单项（和 FSCapture 一致：水印/边框）",
      items(ed.menus["fx"]) == ["水印…", "边框…"], str(items(ed.menus["fx"])))
check("选项菜单含语言/会话恢复/默认水印边框",
      items(ed.menus["options"]) == [
          "语言", "启动时恢复上次的截图", "清除上次的截图缓存",
          "编辑默认水印…", "编辑默认边框…"],
      str(items(ed.menus["options"])))
check("会话恢复开关可勾选", ed.act_restore.isCheckable())

# 快捷键
check("打开图片有 Ctrl+O", ed.act_open_img.shortcut().toString() == "Ctrl+O",
      ed.act_open_img.shortcut().toString())
check("保存有 Ctrl+S", ed.act_save.shortcut().toString() == "Ctrl+S")

# 语言子菜单
ed.menu_lang.aboutToShow.emit()
lang_items = items(ed.menu_lang)
check("语言子菜单有简繁英 + 跟随系统", len(lang_items) == 4, str(lang_items))
check("语言子菜单含跟随系统",
      any("跟随系统" in s for s in lang_items), str(lang_items))

# ---------- 3) 打开图片后：加标签、菜单项恢复 ----------
tmp = os.path.join(HERE, "_menu_test.png")
pix = QPixmap(120, 90)
pix.fill(QColor("#3399ff"))
pix.save(tmp)
_orig = QFileDialog.getOpenFileName
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (tmp, ""))
try:
    ed.open_image()
    check("打开图片后新增标签", ed.tabs.count() == 1)
    check("有标签后显示标签页而非空状态",
          ed.stack.currentWidget() is ed.tabs)
    check("有标签后菜单项恢复可用", ed.act_save.isEnabled())
    check("新标签的画布可用", ed.canvas is not None)
finally:
    QFileDialog.getOpenFileName = _orig
    try:
        os.remove(tmp)
    except OSError:
        pass

# 取消打开不应加标签
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
try:
    ed.open_image()
    check("取消打开图片不加标签", ed.tabs.count() == 1)
finally:
    QFileDialog.getOpenFileName = _orig

# ---------- 4) 特效菜单真的打开对话框 ----------
opened = []
_orig_exec = QDialog.exec


def fake_exec(self):
    opened.append(type(self).__name__)
    return QDialog.Rejected          # 取消，不改画布


QDialog.exec = fake_exec
try:
    ed.act_m_wm.trigger()
    ed.act_m_border.trigger()
finally:
    QDialog.exec = _orig_exec
check("特效 → 水印 打开水印对话框", "WatermarkDialog" in opened, str(opened))
check("特效 → 边框 打开边框对话框", "BorderDialog" in opened, str(opened))

# ---------- 5) 关闭最后一个标签回到空状态 ----------
ed.close_tab(0)
check("关掉最后一个标签回到空状态", ed.tabs.count() == 0
      and ed.stack.currentWidget() is ed.empty_page)
check("回到空状态后菜单项又置灰", not ed.act_save.isEnabled())


# ---------- 6) 「关于」的文案必须三语齐全（用户就是这里报的漏译）----------
import re as _re
from PySide6.QtWidgets import QMessageBox
import i18n

_captured = []
_orig_about = QMessageBox.about
QMessageBox.about = staticmethod(
    lambda parent, title, text, *a: _captured.append((title, text)))
try:
    # PYSHOT_LANG 的优先级高于 set_language（那是强制指定用的），
    # 这一段要切语言，先把它摘掉
    _env_lang = os.environ.pop("PYSHOT_LANG", None)
    CJK = _re.compile(r"[\u4e00-\u9fff]")
    for lang in ("zh_CN", "zh_TW", "en"):
        i18n.set_language(lang, persist=False)
        _captured.clear()
        ed.show_about()
        title, text = _captured[0]
        if lang == "en":
            check("英文「关于」没有中文残留", not CJK.search(text),
                  _re.sub("PyShot|FastStone", "", text)[:60])
            check("英文「关于」标题正确", title == "About PyShot", title)
        if lang == "zh_TW":
            check("繁体「关于」用繁体", "截圖" in text and "截图" not in text,
                  text[:40])
        if lang == "zh_CN":
            check("简体「关于」正常", "截图" in text, text[:40])
        check(f"「关于」含版本号（{lang}）", "2." in text, text[:40])
finally:
    QMessageBox.about = _orig_about
    i18n.set_language("zh_CN", persist=False)
    if _env_lang is not None:
        os.environ["PYSHOT_LANG"] = _env_lang

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("编辑器菜单栏测试通过 ✔")
