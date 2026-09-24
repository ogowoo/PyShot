# -*- coding: utf-8 -*-
"""真实窗口结构下的滚动匹配（用**真实帧**做回归）。

背景（本机 A/B 实测出来的 bug）：
真实选区里混着**大块静止外壳** —— 标题栏、功能区、面包屑、左侧导航树、滚动条。
它们每帧完全一致，会全票投给偏移 0，把真正的滚动压过去。

证据链（同一台机器）：
1) diag_scroll_ab.py（真窗口 + 真滚轮，只换选区）
      只框列表   679x578   → s=[227,252,252] ✓
      框整个窗口 1131x830  → s=[0,0,0]       ✗ → 修复后 [252,252,252] ✓
2) 本文件：拿真实帧造"只有列表区域平移"（真实模型）
      修复前：22/44/66/132/264 → -1,-1,-1,-1,0   ✗ 全错
      修复后：22/44/66/132/264 → 22,44,66,132,264 ✓ 全对

没有真实帧时（比如别的机器）本条会打印 NOTE 跳过，不会误报失败。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import Frame, find_scroll, pixmap_to_frame

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


DBG = Path.home() / ".pyshot" / "scroll_debug"
CANDIDATES = ["frame_000.png", "ab_B.png", "ab_A.png", "live_a0.png", "live_b1.png"]
src = None
for name in CANDIDATES:
    if (DBG / name).exists():
        src = DBG / name
        break

if src is None:
    print(f"NOTE 没有真实帧（{DBG}），跳过本项检查")
    print("\n真实窗口结构滚动匹配测试：跳过")
    sys.exit(0)

base = pixmap_to_frame(QPixmap(str(src)))
W, H = base.w, base.h
print(f"真实帧: {src.name} {W}x{H}")

# Explorer 窗口布局（从真实帧上量的）：列头以上 + 左侧导航不随内容滚动
LIST_X0 = 200
LIST_Y0 = 180


def shifted(shift: int, list_only: bool) -> Frame:
    """造"滚动后"的帧。list_only=True 时只有列表区域跟着动（真实模型）。"""
    rows = []
    for y in range(H):
        if list_only and y < LIST_Y0:
            rows.append(base.rows[y])
            continue
        src_y = y + shift
        row = base.rows[src_y] if src_y < H else base.rows[H - 1]
        if list_only:
            row = base.rows[y][:LIST_X0 * 3] + row[LIST_X0 * 3:]
        rows.append(row)
    return Frame(rows, W, H)


# ---------- (a) 整帧平移：基线，本来就该对 ----------
for step in (22, 132):
    s, _ = find_scroll(base, shifted(step, list_only=False))
    check(f"整帧平移 {step}px 能算对", s == step, f"得到 {s}")

# ---------- (b) 只有列表区域平移：**这条以前全错** ----------
for step in (22, 44, 66, 132, 264):
    s, _ = find_scroll(base, shifted(step, list_only=True))
    check(f"**只有列表滚动 {step}px 也要算对**（修复前是 -1/0）", s == step,
          f"得到 {s}")

# ---------- 没滚动 → 0 ----------
s0, _ = find_scroll(base, shifted(0, list_only=True))
check("没滚动时判 0", s0 == 0, f"得到 {s0}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("真实窗口结构滚动匹配测试通过 ✔")
