# -*- coding: utf-8 -*-
"""帮助窗口：左侧小节列表 + 搜索框，右侧正文（可滚动、可复制）。

内容来自 `help_text.py`（只写简体），显示时逐条走 `tr()`，所以和界面一样是三语的；
语言切换后重新打开（或按 `retranslate()`）就是新语言。
"""
import html
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from help_text import HELP_INTRO, HELP_TITLE, SECTIONS
from i18n import tr


def _escape(text: str) -> str:
    """转义 HTML，并把 `**加粗**` 变成 <b>（帮助正文里会用到）。"""
    safe = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)


def _line_to_html(raw: str) -> str:
    """把一行的前缀约定转成 HTML：`- ` 条目、`## ` 小标题、其余段落。"""
    text = raw.strip()
    if text.startswith("## "):
        return f"<h4>{_escape(text[3:])}</h4>"
    if text.startswith("- "):
        return f"<li>{_escape(text[2:])}</li>"
    return f"<p>{_escape(text)}</p>"


def section_html(index: int, hotkey: str = "", fullhotkey: str = "") -> str:
    """第 index 小节的 HTML（含热键替换）。抽成函数便于测试与复用。"""
    title, lines = SECTIONS[index]
    body = []
    open_list = False
    for raw in lines:
        # 先翻译再替换热键占位符（译文里同样用 {hotkey}/{fullhotkey}）
        text = tr(raw)
        text = text.replace("{hotkey}", hotkey or "Ctrl+Alt+X")
        text = text.replace("{fullhotkey}", fullhotkey or "Ctrl+Alt+F")
        if text.strip().startswith("- "):
            if not open_list:
                body.append("<ul>")
                open_list = True
            body.append(_line_to_html(text))
        else:
            if open_list:
                body.append("</ul>")
                open_list = False
            body.append(_line_to_html(text))
    if open_list:
        body.append("</ul>")
    return (f"<h3>{_escape(tr(title))}</h3>" + "".join(body))


class HelpDialog(QDialog):
    """非模态帮助窗口：可以一边看一边照着操作。"""

    def __init__(self, parent=None, hotkey: str = "", fullhotkey: str = "",
                 shortcuts: list | None = None):
        super().__init__(parent)
        self.hotkey = hotkey
        self.fullhotkey = fullhotkey
        self.extra_shortcuts = list(shortcuts or [])
        self.setObjectName("helpwin")
        self.setWindowTitle(tr(HELP_TITLE))
        self.resize(760, 560)
        self.setSizeGripEnabled(True)

        root = QVBoxLayout(self)
        head = QLabel(tr(HELP_INTRO))
        head.setObjectName("helpintro")
        head.setWordWrap(True)
        root.addWidget(head)

        # 搜索框：过滤左侧小节（标题或正文命中都算）
        self.search = QLineEdit()
        self.search.setObjectName("helpsearch")
        self.search.setPlaceholderText(tr("搜索帮助内容…（例如：拼图、滚动、快捷键）"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        split = QSplitter(Qt.Horizontal)
        self.topics = QListWidget()
        self.topics.setObjectName("helptopics")
        self.topics.setMinimumWidth(150)
        self.topics.currentRowChanged.connect(self._show_current)
        split.addWidget(self.topics)

        self.view = QTextBrowser()
        self.view.setObjectName("helptext")
        self.view.setOpenExternalLinks(False)
        split.addWidget(self.view)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([180, 560])
        root.addWidget(split, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        buttons.button(QDialogButtonBox.Close).setText(tr("关闭"))
        root.addWidget(buttons)

        self._fill_topics()
        self.topics.setCurrentRow(0)
        self.search.setFocus()

    # ---------- 内部 ----------
    def _fill_topics(self):
        """填小节列表；最后一节是"快捷键一览"（从菜单实时收集，不会过期）。"""
        self.topics.clear()
        for i, (title, _lines) in enumerate(SECTIONS):
            item = QListWidgetItem(tr(title))
            item.setData(Qt.UserRole, i)
            self.topics.addItem(item)
        if self.extra_shortcuts:
            item = QListWidgetItem(tr("快捷键一览"))
            item.setData(Qt.UserRole, len(SECTIONS))       # 虚拟小节
            self.topics.addItem(item)

    def _show_current(self, row: int):
        item = self.topics.item(row)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx == len(SECTIONS):
            self.view.setHtml(self._shortcuts_html())
        else:
            self.view.setHtml(section_html(idx, self.hotkey, self.fullhotkey))
        self.view.verticalScrollBar().setValue(0)

    def _shortcuts_html(self) -> str:
        rows = "".join(
            f"<tr><td>{_escape(tr(label))}</td>"
            f"<td><code>{_escape(seq)}</code></td></tr>"
            for label, seq in self.extra_shortcuts)
        return (f"<h3>{_escape(tr('快捷键一览'))}</h3>"
                + f"<p>{_escape(tr('下面这些是当前生效的快捷键（菜单里改不了的就写在这里）。'))}</p>"
                + f"<table cellspacing='0' cellpadding='4'>{rows}</table>")

    def _apply_filter(self, text: str):
        """按关键字过滤小节：标题命中或正文命中都保留。"""
        key = (text or "").strip().lower()
        for i in range(self.topics.count()):
            item = self.topics.item(i)
            idx = item.data(Qt.UserRole)
            if not key:
                item.setHidden(False)
                continue
            if idx == len(SECTIONS):
                blob = tr("快捷键一览") + " 快捷键 " + " ".join(
                    f"{tr(l)} {s}" for l, s in self.extra_shortcuts)
            else:
                title, lines = SECTIONS[idx]
                # 译文和简体原文都搜：英文界面下用中文关键词也找得到
                blob = " ".join([tr(title), title]
                                + [tr(x) for x in lines] + list(lines))
                blob += " " + blob.replace(" ", "")      # 中文没空格，去空格再匹配一次
            item.setHidden(key not in blob.lower())
        # 过滤后如果当前项被隐藏，自动选第一个可见的
        cur = self.topics.currentItem()
        if cur is not None and cur.isHidden():
            for i in range(self.topics.count()):
                if not self.topics.item(i).isHidden():
                    self.topics.setCurrentRow(i)
                    break

    def retranslate(self):
        """语言切换后刷新（标题、按钮、列表、正文）。"""
        self.setWindowTitle(tr(HELP_TITLE))
        self.search.setPlaceholderText(tr("搜索帮助内容…（例如：拼图、滚动、快捷键）"))
        row = self.topics.currentRow()
        self._fill_topics()
        self.topics.setCurrentRow(max(0, row))
        self._apply_filter(self.search.text())


def open_help(parent=None, hotkey: str = "", fullhotkey: str = "",
              shortcuts: list | None = None) -> HelpDialog:
    """打开（或复用）帮助窗口；非模态，方便照着做。"""
    dlg = getattr(parent, "_help_dialog", None)
    if dlg is None:
        dlg = HelpDialog(parent, hotkey, fullhotkey, shortcuts)
        if parent is not None:
            parent._help_dialog = dlg          # 持有引用，别被回收
    else:
        dlg.hotkey, dlg.fullhotkey = hotkey, fullhotkey
        dlg.extra_shortcuts = list(shortcuts or [])
        row = dlg.topics.currentRow()
        dlg._fill_topics()
        dlg.topics.setCurrentRow(max(0, row))
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
