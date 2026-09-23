# -*- coding: utf-8 -*-
"""把 pyshot 的多文件源码合并成一个单文件 PyShot.py。

用法::

    python build_single.py            # 生成 PyShot.py
    python build_single.py -o X.py    # 指定输出文件名

合并规则
========
- 按依赖顺序拼接：bootstrap → shapes → style → pinboard → snipper → scroller → editor → main
- 删除模块之间的本地 import（合并后同处一个命名空间）
- 删除 main.py 里的 __main__ 入口，换成单文件自己的入口（支持 --check-deps）
- 头部内嵌依赖自举：缺 PySide6 / numpy 会自动 pip 安装
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    "i18n_data.py",
    "i18n.py",
    "session.py",
    "diag.py",
    "bootstrap.py",
    "watermark.py",
    "border.py",
    "shapes.py",
    "style.py",
    "capture_utils.py",
    "pinboard.py",
    "snipper.py",
    "scroller.py",
    "editor.py",
    "main.py",
]

LOCAL_MODULES = ("i18n_data", "i18n", "session", "diag", "bootstrap", "watermark", "border", "shapes", "style", "capture_utils",
                 "pinboard", "snipper", "scroller", "editor", "main")

_LOCAL_ALT = "|".join(LOCAL_MODULES)

# from X import a, b as c   （含括号多行写法）—— 合并后只保留"名字本身"，
# 但 `as` 别名要**补一条赋值**，否则别名悬空（曾因此崩过：border_load 未定义）
LOCAL_FROM_IMPORT_RE = re.compile(
    r"^([ \t]*)from[ \t]+(?:" + _LOCAL_ALT + r")[ \t]+import[ \t]+"
    r"(\([^)]*\)|[^\n]*)",
    re.MULTILINE)

# import X / import X as Y（本地模块）—— 合并后没有模块对象，无法支持，
# 必须报错让开发者改成 from X import 名字
LOCAL_MODULE_IMPORT_RE = re.compile(
    r"^[ \t]*import[ \t]+(?:" + _LOCAL_ALT + r")(?:[ \t]+as[ \t]+\w+)?[ \t]*$",
    re.MULTILINE)

# 兜底：其它形式的本地导入（如 from X import *）
LOCAL_IMPORT_RE = re.compile(
    r"^[ \t]*(?:from[ \t]+(?:" + _LOCAL_ALT + r")[ \t]+import"
    r"|import[ \t]+(?:" + _LOCAL_ALT + r"))\b"
    r"(?:[ \t]*\([^)]*\)[^\n]*|[^\n]*)",
    re.MULTILINE)


def _aliases_of(imported: str) -> list:
    """从 `a, b as c` 里取出需要补的别名赋值 [(别名, 真名), ...]。"""
    text = imported.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    out = []
    for part in text.replace("\n", " ").split(","):
        part = part.strip()
        if not part:
            continue
        if " as " in part:
            real, alias = [p.strip() for p in part.split(" as ", 1)]
            out.append((alias, real))
    return out

# main.py 里的依赖检查要挪到合并文件最顶部执行（必须在任何 PySide6 导入之前）
BOOTSTRAP_CALL_RE = re.compile(
    r"^if not ensure_deps\(\):\n[ \t]+raise SystemExit\(1\)\n", re.MULTILINE)

# 合并文件里依赖自举的执行点：紧跟 bootstrap 段之后
DEPS_CALL = '''

# 依赖自举：在任何 PySide6 导入之前完成检查与安装
if not ensure_deps():
    raise SystemExit(1)
'''

HEADER = '''# -*- coding: utf-8 -*-
"""PyShot 单文件版 —— 仿 FSCapture 的截图 + 标注编辑工具（自动安装依赖）

这是一个自动生成的单文件版本：把多文件源码合并在一起，并在启动时自动安装
缺失的第三方库（PySide6 / numpy），因此可以直接发给别人运行::

    python PyShot.py              # 启动后驻留托盘，按 PrintScreen 开始截图
    python PyShot.py 图片.png     # 直接编辑已有图片
    python PyShot.py --check-deps # 只检查依赖

生成方式：python build_single.py（请勿手工修改本文件，改动请改多文件源码）
"""
'''

TAIL = '''
# ---------------------------------------------------------------------------
# 单文件版入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if "--check-deps" in sys.argv:
        print(deps_report())
    else:
        main()
'''


def strip_module(path: str) -> str:
    """读入模块源码，去掉本地 import、__main__ 入口和重复的依赖检查。

    本地 import 在合并后是多余的（名字已在同一命名空间），但**必须处理别名**：
    直接删掉 `from border import x as y` 会让 `y` 悬空（曾因此崩过）。
    这里把别名补成 `y = x`；模块导入（`import x`）无法支持，构建期报错。
    """
    with open(path, encoding="utf-8-sig") as f:   # utf-8-sig：兼容带 BOM 的源文件
        src = f.read()
    src = src.lstrip("\ufeff")                     # 双保险：去掉残留的 BOM

    bad = LOCAL_MODULE_IMPORT_RE.findall(src)
    if bad:
        raise SystemExit(
            f"{os.path.basename(path)} 里有本地模块导入（import {'; import '.join(bad)}），"
            "合并成单文件后没有模块对象可用。\n"
            "请改成 `from 模块 import 名字` 的形式。")

    def _replace(match):
        # 关键：补的赋值必须**保留原来的缩进**（导入可能在函数体内）
        indent, imported = match.group(1), match.group(2)
        aliases = _aliases_of(imported)
        if not aliases:
            return ""
        return "\n".join(f"{indent}{alias} = {real}"
                         for alias, real in aliases)

    # 先处理"带别名的本地导入"：补成 `别名 = 真名`（必须在兜底删除之前！）
    src = LOCAL_FROM_IMPORT_RE.sub(_replace, src)
    src = LOCAL_IMPORT_RE.sub("", src)             # 兜底：清掉剩余形式
    src = BOOTSTRAP_CALL_RE.sub("", src)
    # 去掉 __main__ 入口（单文件自己提供）
    src = re.sub(r"\nif __name__ == [\"']__main__[\"']:\n    main\(\)\s*$", "\n", src)
    return src


def top_level_defs(src: str) -> dict:
    """收集模块顶层定义：{名字: (种类, 行号, 源码片段)}。

    合并后所有模块共用一个命名空间，重名会**静默覆盖**——曾经因此出过 bug：
    style.py 的图标函数 _draw_text(p, c) 覆盖了 watermark.py 里同名的
    _draw_text(painter, settings, box)，于是单文件版一点水印就崩，而多文件版
    （各自独立命名空间）完全正常。所以这里必须在构建期拦下来。
    """
    out = {}
    for node in ast.parse(src).body:
        kind = ""
        text = ""
        name = ""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind, name = "def", node.name
            text = ast.unparse(node.args)
        elif isinstance(node, ast.ClassDef):
            kind, name = "class", node.name
            text = ",".join(ast.unparse(b) for b in node.bases)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            kind, name = "assign", node.targets[0].id
            text = ast.unparse(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            kind, name = "assign", node.target.id
            text = ast.unparse(node.value) if node.value else ""
        if name:
            out[name] = (kind, node.lineno, text)
    return out


def find_collisions(modules) -> list:
    """返回 [(名字, [(模块, 行号, 片段), ...]), ...]（只列真正会出问题的）。"""
    seen = {}
    dups = {}
    for name in modules:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        for ident, (kind, line, text) in top_level_defs(
                strip_module(path)).items():
            if ident in seen:
                dups.setdefault(ident, [seen[ident]]).append((name, line, kind,
                                                              text))
            else:
                seen[ident] = (name, line, kind, text)
    problems = []
    for ident, where in sorted(dups.items()):
        kinds = {w[2] for w in where}
        texts = {w[3] for w in where}
        # 同名常量/循环变量且赋值完全相同（例如各模块都写
        # user32 = ctypes.windll.user32）是无害的；其余都会互相覆盖。
        if kinds == {"assign"} and len(texts) == 1:
            continue
        problems.append((ident, [(w[0], w[1]) for w in where]))
    return problems


def build(out_path: str) -> str:
    problems = find_collisions(MODULES)
    if problems:
        lines = ["合并后这些顶层名字会互相覆盖（后加载的模块赢，前面那个静默失效）："]
        for ident, where in problems:
            lines.append(f"  {ident}: " + " / ".join(f"{m}:{l}" for m, l in where))
        lines.append("请给它们改成模块内唯一的名字（例如加 _wm_ 前缀）。")
        raise SystemExit("\n".join(lines))

    parts = [HEADER]
    for name in MODULES:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            raise SystemExit(f"缺少源文件：{path}")
        parts.append(f"\n\n# {'=' * 72}\n# 来自 {name}\n# {'=' * 72}\n")
        parts.append(strip_module(path))
        if name == "bootstrap.py":
            parts.append(DEPS_CALL)      # 自举之后立刻检查依赖
    parts.append(TAIL)
    code = "".join(parts)

    # 合并结果必须是合法 Python（先自查，避免生成坏文件）
    ast.parse(code, filename=out_path)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    return out_path


def main():
    out = "PyShot.py"
    argv = sys.argv[1:]
    if "-o" in argv:
        out = argv[argv.index("-o") + 1]
    out_path = out if os.path.isabs(out) else os.path.join(HERE, out)
    build(out_path)
    size = os.path.getsize(out_path)
    lines = sum(1 for _ in open(out_path, encoding="utf-8"))
    print(f"已生成单文件：{out_path}")
    print(f"  {lines} 行 / {size / 1024:.1f} KB")
    print(f"  运行：python \"{out_path}\"")


if __name__ == "__main__":
    main()
