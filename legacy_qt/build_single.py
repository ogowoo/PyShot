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
    "bootstrap.py",
    "watermark.py",
    "shapes.py",
    "style.py",
    "capture_utils.py",
    "pinboard.py",
    "snipper.py",
    "scroller.py",
    "editor.py",
    "main.py",
]

LOCAL_MODULES = ("bootstrap", "watermark", "shapes", "style", "capture_utils",
                 "pinboard", "snipper", "scroller", "editor", "main")

# 匹配模块间的本地导入（含函数内延迟导入与多行括号写法），不碰 PySide6 等第三方导入
LOCAL_IMPORT_RE = re.compile(
    r"^[ \t]*(?:from[ \t]+(?:" + "|".join(LOCAL_MODULES) + r")[ \t]+import"
    r"|import[ \t]+(?:" + "|".join(LOCAL_MODULES) + r"))\b"
    r"(?:[ \t]*\([^)]*\)[^\n]*|[^\n]*)",
    re.MULTILINE)

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
    """读入模块源码，去掉本地 import、__main__ 入口和重复的依赖检查。"""
    with open(path, encoding="utf-8-sig") as f:   # utf-8-sig：兼容带 BOM 的源文件
        src = f.read()
    src = src.lstrip("﻿")                          # 双保险：去掉残留的 BOM
    src = LOCAL_IMPORT_RE.sub("", src)
    src = BOOTSTRAP_CALL_RE.sub("", src)
    # 去掉 __main__ 入口（单文件自己提供）
    src = re.sub(r"\nif __name__ == [\"']__main__[\"']:\n    main\(\)\s*$", "\n", src)
    return src


def build(out_path: str) -> str:
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
