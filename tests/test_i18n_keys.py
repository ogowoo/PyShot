# -*- coding: utf-8 -*-
"""静态检查：源码里出现的每个 tr("…") 键，三语必须齐全。

为什么需要它：test_i18n_ui.py 是"扫描已创建控件的文案"，只能覆盖当前真的
创建出来的界面。像「关于」这种点了才弹的内容、以及只在特定分支里用到的文案，
它一个都碰不到 —— 于是出现过"键在词表里、英文却是空的"这种漏译。
这里改成直接扫源码：只要写了 tr("…")，就必须有译文。
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)
os.environ.setdefault("PYSHOT_LANG", "zh_CN")

import i18n

FILES = ["main.py", "editor.py", "border.py", "watermark.py", "scroller.py",
         "snipper.py", "pinboard.py", "bootstrap.py", "style.py"]
CJK = re.compile(r"[\u4e00-\u9fff]")

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def tr_keys_in(path: str) -> set:
    """收集源码里 tr(...) 的第一个字符串实参。"""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "tr"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.add(arg.value)
    return out


all_keys = {}
for name in FILES:
    path = os.path.join(HERE, name)
    if os.path.exists(path):
        for k in tr_keys_in(path):
            all_keys.setdefault(k, []).append(name)

# 只关心"含中文"的键：纯占位符模板（如 "{} — {}"）本来就不需要译文
cjk_keys = {k: v for k, v in all_keys.items() if CJK.search(k)}
print(f"源码里 tr(...) 共 {len(all_keys)} 个键，其中含中文的 {len(cjk_keys)} 个")

missing = {k: v for k, v in cjk_keys.items() if k not in i18n.TABLE}
if missing:
    print("  ✗ 不在词表里：")
    for k, files in sorted(missing.items()):
        print(f"     {files} {k[:60]!r}")

no_en = {k: v for k, v in cjk_keys.items()
         if k in i18n.TABLE and not i18n.TABLE[k][1]}
if no_en:
    print("  ✗ 缺英文：")
    for k, files in sorted(no_en.items()):
        print(f"     {files} {k[:60]!r}")

no_tw = {k: v for k, v in cjk_keys.items()
         if k in i18n.TABLE and not i18n.TABLE[k][0]}
if no_tw:
    print("  ✗ 缺繁体：")
    for k, files in sorted(no_tw.items()):
        print(f"     {files} {k[:60]!r}")

check("所有 tr() 键都在词表里", not missing, f"{len(missing)} 个缺失")
check("所有 tr() 键都有英文", not no_en, f"{len(no_en)} 个缺英文")
check("所有 tr() 键都有繁体", not no_tw, f"{len(no_tw)} 个缺繁体")

# 英文不能残留中文（个别专有名词除外）
ALLOW = ("PyShot", "FastStone", "Citrix", "Windows", "PYSHOT")
leftover = {}
for k in cjk_keys:
    en = i18n.TABLE.get(k, (None, ""))[1]
    if not en:
        continue
    bad = CJK.search(re.sub("|".join(ALLOW), "", en))
    if bad:
        leftover[k] = en
if leftover:
    print("  ✗ 英文里还残留中文（说明没真翻译）：")
    for k, en in sorted(leftover.items()):
        print(f"     {en[:70]!r}")
check("英文译文里没有残留中文", not leftover, f"{len(leftover)} 条")

# 繁体不能残留常见简体字
# gen_i18n 是开发工具，现在在 tools/ 下（测试在 tests/），要把它加进搜索路径
sys.path.insert(0, os.path.join(HERE, "tools"))
from gen_i18n import S2T_CHARS
still_simp = {}
for k in cjk_keys:
    tw = i18n.TABLE.get(k, ("", ""))[0]
    if not tw:
        continue
    # 只看"在映射表里指明了繁体写法"的字，避免误判繁简同形字
    for ch in tw:
        if ch in S2T_CHARS and S2T_CHARS[ch] != ch:
            still_simp[k] = tw
            break
if still_simp:
    print("  ✗ 繁体里还有该转没转的字：")
    for k, tw in sorted(still_simp.items()):
        print(f"     {tw[:70]!r}")
check("繁体译文里没有漏转的字", not still_simp, f"{len(still_simp)} 条")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("tr() 键三语完整性检查通过 ✔")
