# -*- coding: utf-8 -*-
"""用 AST 精确地把"用户可见文案"包进 tr()（开发工具）。

为什么用 AST 而不是正则：只有出现在 UI 位置（setText/setToolTip/QAction(...)
这类调用实参）里的字符串才该翻译；正则会把注释、比较、字典键一起改坏。

用法：python _wrap_tr.py [--dry]
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["main.py", "snipper.py", "editor.py", "border.py", "watermark.py",
         "scroller.py", "pinboard.py", "bootstrap.py"]
CJK = re.compile(r"[\u4e00-\u9fff]")

# 这些函数/构造器的**字符串实参**是用户可见文案
UI_CALLS = {
    # 控件构造
    "QAction", "QLabel", "QPushButton", "QCheckBox", "QRadioButton",
    "QGroupBox", "QMenu", "QToolButton", "QDialogButtonBox",
    # 文案设置
    "setText", "setToolTip", "setWindowTitle", "setPlaceholderText",
    "setStatusTip", "setWhatsThis", "setTitle", "setToolTipText",
    "addItem", "addItems", "addButton", "addRow", "addTab",
    # 消息 / 对话框
    "getOpenFileName", "getSaveFileName", "getExistingDirectory",
    "information", "warning", "critical", "question", "showMessage",
    "setFilter", "setNameFilter", "setNameFilters", "setLabelText",
    # 本项目自己的提示函数
    "_notify", "notify", "set_title", "set_progress_text", "set_hint",
    "_hint_text", "set_placeholder",
    # 信号发射 / 画布文本（错误消息与覆盖层提示都走这两个）
    "emit", "itemconfigure",
}

# 不该翻译的（内部/调试/资源路径/样式）
SKIP_PREFIX = ("[PyShot]", "/*", "background", "border", "QWidget", "QMenu {",
               ".png", "file://", "rgba(", "#")


def should_wrap(text: str) -> bool:
    s = text.strip()
    if len(s) < 2 or not CJK.search(s):
        return False
    if s.startswith(SKIP_PREFIX):
        return False
    return True


def is_joined_str(node) -> bool:
    return isinstance(node, ast.JoinedStr)


class Collector(ast.NodeVisitor):
    """收集需要包裹的字符串字面量位置。"""

    def __init__(self):
        self.targets = []

    def visit_Call(self, node):
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in UI_CALLS:
            for arg in node.args:
                self._mark(arg)
            for kw in node.keywords:
                self._mark(kw.value)
        self.generic_visit(node)

    def _mark(self, node):
        """只包裹**直接的字符串实参**。

        刻意不碰字符串拼接（`"A" + x + "B"`）与 f-string：
        拼接里混着 join 分隔符、片段之间还会互相错位——手工改成
        `tr("…{}…").format(…)` 才安全（第一版就是在这里把文件改坏的）。
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and should_wrap(node.value):
            self.targets.append(node)


def wrap_file(path: str, dry: bool = False) -> int:
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    col = Collector()
    col.visit(tree)

    # 已经在 tr(...) 里的不要再包一层
    wrapped = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "tr":
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    wrapped.add(id(arg))

    targets = [t for t in col.targets if id(t) not in wrapped]
    # 去重（同一个节点可能被外层与内层调用各标记一次）
    seen, uniq = set(), []
    for t in targets:
        if id(t) not in seen:
            seen.add(id(t))
            uniq.append(t)
    targets = uniq
    if not targets:
        return 0

    lines = src.splitlines(keepends=True)
    # 从后往前改，避免偏移失效
    targets.sort(key=lambda n: (n.lineno, n.col_offset), reverse=True)
    for node in targets:
        end_lineno = getattr(node, "end_lineno", node.lineno)
        end_col = getattr(node, "end_col_offset", node.col_offset)
        if node.lineno != end_lineno:            # 跨行字符串不动
            continue
        li = node.lineno - 1
        # 注意：AST 的 col_offset 是 **UTF-8 字节偏移**，不是字符偏移。
        # 行内有中文时按字符切片会错位（第一版就因此把文件改坏过），
        # 所以这里统一用 bytes 切片再解码。
        raw = lines[li].encode("utf-8")
        seg = raw[node.col_offset:end_col].decode("utf-8")
        if not (seg.startswith(('"', "'", 'f"', "f'"))):
            continue
        new = raw[:node.col_offset] + f"tr({seg})".encode("utf-8") + raw[end_col:]
        lines[li] = new.decode("utf-8")

    out = "".join(lines)
    if not dry:
        open(path, "w", encoding="utf-8", newline="\n").write(out)
    return len(targets)


def ensure_import(path: str):
    """确保文件顶部有 `from i18n import tr`。"""
    src = open(path, encoding="utf-8").read()
    if re.search(r"^from i18n import", src, re.M):
        return
    lines = src.splitlines(keepends=True)
    # 插到最后一个顶层 import 之后
    tree = ast.parse(src)
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node.end_lineno
    lines.insert(last, "from i18n import tr\n")
    open(path, "w", encoding="utf-8", newline="\n").write("".join(lines))


def main():
    dry = "--dry" in sys.argv
    total = 0
    for name in FILES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        n = wrap_file(path, dry=dry)
        if n and not dry:
            ensure_import(path)
        print(f"  {name:18} 包裹 {n} 处")
        total += n
    print(f"  合计 {total} 处" + ("（dry run，未写盘）" if dry else ""))


if __name__ == "__main__":
    main()
