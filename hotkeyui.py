# -*- coding: utf-8 -*-
"""自定义截图热键对话框：按下组合键 → 当场告诉你能不能用。

为什么要"检测"：`RegisterHotKey` **成功不等于没冲突**。大多数应用的快捷键
（Outlook 的 Ctrl+Shift+F、多数软件的 Ctrl+Shift+S…）只是本地快捷键，我们照样
注册得上，然后把它"抢走"。所以这里除了真去试注册，还查一张已知冲突表，
并把「含 Alt 会关掉右键菜单」这类坑直接在对话框里说清楚。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QKeySequenceEdit, QPushButton, QVBoxLayout)

from i18n import tr


def spec_from_sequence(seq: QKeySequence) -> str:
    """QKeySequence 的 "Ctrl+Shift+X" → 我们的 "ctrl+shift+x"。"""
    parts = [p.strip().lower() for p in seq.toString().split("+") if p.strip()]
    alias = {"ctrl": "ctrl", "control": "ctrl", "meta": "win", "shift": "shift",
             "alt": "alt", "del": "delete", "esc": "esc", "return": "enter",
             "print": "printscreen", "prtsc": "printscreen"}
    return "+".join(alias.get(p, p) for p in parts)


# Qt 对个别键的叫法和我们不同（尤其 PrintScreen 在 Qt 里叫 "Print"——
# 写成 "Ctrl+PrintScreen" 会解析成空序列，这是踩过的坑）
_QT_KEY_NAMES = {"printscreen": "Print", "prtsc": "Print",
                 "pageup": "PgUp", "pagedown": "PgDn",
                 "insert": "Ins", "delete": "Del", "esc": "Esc"}


def sequence_from_spec(spec: str) -> QKeySequence:
    """我们的 "ctrl+printscreen" → QKeySequence（能正确显示的写法）。"""
    out = []
    for raw in (spec or "").split("+"):
        p = raw.strip().lower()
        if not p:
            continue
        if p in ("ctrl", "control"):
            out.append("Ctrl")
        elif p == "shift":
            out.append("Shift")
        elif p == "alt":
            out.append("Alt")
        elif p in ("win", "meta", "super"):
            out.append("Meta")
        elif p in _QT_KEY_NAMES:
            out.append(_QT_KEY_NAMES[p])
        elif len(p) == 1:
            out.append(p.upper())
        elif p.startswith("f") and p[1:].isdigit():
            out.append("F" + p[1:])
        else:
            out.append(p.capitalize())
    return QKeySequence("+".join(out))


def pretty_spec(spec: str) -> str:
    """显示用的名字：ctrl+printscreen → Ctrl+PrtSc。"""
    from main import parse_hotkey
    parsed = parse_hotkey(spec)
    return parsed[2] if parsed else (spec or "")


class HotkeyDialog(QDialog):
    """输入一个组合键，实时显示"可用 / 有风险 / 不可用"，并给出原因。"""

    def __init__(self, parent, current: str, check, suggest: list | None = None,
                 title: str = ""):
        """
        current  当前生效的组合（形如 "ctrl+shift+x"）
        check    回调 spec -> dict（main.check_hotkey 的结果）
        suggest  推荐组合列表（第一个作为"用推荐值"按钮）
        title    窗口标题（区域 / 全屏各自不同）
        """
        super().__init__(parent)
        self._check = check
        self._suggest = list(suggest or [])
        self.setWindowTitle(title or tr("自定义截图热键"))
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("按下你想用的组合键（需要至少一个修饰键）：")))

        self.edit = QKeySequenceEdit(sequence_from_spec(current))
        # 快捷键输入控件默认会"等 1 秒确认"，这里关掉，改成每次按下就检测
        self.edit.setMaximumSequenceLength(1)
        self.edit.keySequenceChanged.connect(self._recheck)
        lay.addWidget(self.edit)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("hotkeystatus")
        lay.addWidget(self.status)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setObjectName("hotkeydetails")
        lay.addWidget(self.details)

        row = QHBoxLayout()
        self.btn_recheck = QPushButton(tr("重新检测"))
        self.btn_recheck.clicked.connect(self._recheck)
        row.addWidget(self.btn_recheck)
        if self._suggest:
            nice = pretty_spec(self._suggest[0])
            self.btn_suggest = QPushButton(tr("用推荐值 {}（最稳）", nice))
            self.btn_suggest.clicked.connect(self._use_suggestion)
            row.addWidget(self.btn_suggest)
        row.addStretch(1)
        lay.addLayout(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._accept_if_ok)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self.result_info = {"level": "bad"}
        self._recheck()

    # ---------- 内部 ----------
    def spec(self) -> str:
        return spec_from_sequence(self.edit.keySequence())

    def _use_suggestion(self):
        self.edit.setKeySequence(sequence_from_spec(self._suggest[0]))
        self._recheck()

    def _recheck(self, *args):
        info = self._check(self.spec())
        self.result_info = info
        level = info.get("level", "bad")
        if level == "ok":
            self.status.setText(tr("✓ {} 可以使用，没有检测到冲突", info["name"]))
            self.status.setStyleSheet("color:#2e7d32; font-weight:600;")
        elif level == "warn":
            self.status.setText(tr("⚠ {} 能用，但有问题要注意", info["name"]))
            self.status.setStyleSheet("color:#ef6c00; font-weight:600;")
        else:
            self.status.setText(tr("✗ {} 不能用", info["name"] or self.spec()))
            self.status.setStyleSheet("color:#c62828; font-weight:600;")
        lines = [f"· {x}" for x in info.get("errors", [])]
        lines += [f"· {x}" for x in info.get("warnings", [])]
        self.details.setText("\n".join(lines))
        # 语法错/被占用时不让点确定；"有风险"允许（用户可能就是想要那个键）
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(info.get("ok")) and level != "bad")

    def _accept_if_ok(self):
        if self.buttons.button(QDialogButtonBox.Ok).isEnabled():
            self.accept()

    def chosen_spec(self) -> str:
        return self.spec()
