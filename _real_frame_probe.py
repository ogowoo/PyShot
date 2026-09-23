# -*- coding: utf-8 -*-
"""用**用户的真实帧**做实验：真实 Explorer 画面平移后，匹配能不能算出来。

拿到真实数据后就不该再猜了。这里读 scroll_debug/frame_000.png（用户机器上的
真实截图），按两种模型造出"滚动后"的帧：
  (a) 整帧平移（理想模型）
  (b) 只有列表区域平移、标题栏/工具栏/侧栏保持不动（真实模型）
然后看 find_scroll 是否算得对。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication([])

from scroller import (Frame, _overlap_diff, _same_ratio, find_scroll,
                      pixmap_to_frame)

PNG = Path.home() / ".pyshot" / "scroll_debug" / "frame_000.png"
if not PNG.exists():
    print("找不到真实帧:", PNG)
    sys.exit(0)

pix = QPixmap(str(PNG))
base = pixmap_to_frame(pix)
W, H = base.w, base.h
print(f"真实帧: {W}x{H}（来自用户机器）")

# 估计"静态部分"：比较相邻两行的差异，静态的行（标题栏/工具栏）差异很小
def row_diff(a: bytes, b: bytes) -> float:
    n = len(a)
    step = max(1, n // 200)
    tot = cnt = 0
    for i in range(0, n, step * 3):
        tot += abs(a[i] - b[i])
        cnt += 1
    return tot / max(1, cnt)


print("\n前 220 行的相邻行差异（用来找静态带）：")
marks = []
for y in range(0, min(220, H - 1)):
    d = row_diff(base.rows[y], base.rows[y + 1])
    marks.append((y, d))
static_rows = [y for y, d in marks if d < 3.0]
print(f"  行差异 <3 的行数: {len(static_rows)} / 220"
      f"（这些多半是标题栏/工具栏/空白）")

LIST_X0 = 200        # 左侧导航栏宽度（从帧上看约 200px）
LIST_Y0 = 180        # 列头以下才是列表


def shift_frame(shift: int, list_only: bool) -> Frame:
    """造"滚动后"的帧：shift>0 表示内容向上移动（视口向下看）。"""
    rows = []
    for y in range(H):
        if list_only and (y < LIST_Y0):
            rows.append(base.rows[y])               # 列头以上不动
            continue
        src = y + shift
        if src < H:
            row = base.rows[src]
        else:
            row = base.rows[H - 1]
        if list_only:
            # 只让列表区域跟着动，左侧导航栏保持原样
            row = base.rows[y][:LIST_X0 * 3] + row[LIST_X0 * 3:]
        rows.append(row)
    return Frame(rows, W, H)


print("\n=== (a) 整帧平移（理想模型）===")
for shift in (22, 44, 66, 132, 264):
    cur = shift_frame(shift, list_only=False)
    s, diff = find_scroll(base, cur)
    d0 = _overlap_diff(base, cur, 0)
    r0 = _same_ratio(base, cur, 0)
    ok = "✓" if s == shift else "✗"
    print(f"  真实位移 {shift:4d} → 算出 {s:5d} {ok}   "
          f"(偏移0处 diff={d0:5.1f} same={r0:.2f})")

print("\n=== (b) 只有列表区域平移（真实模型）===")
for shift in (22, 44, 66, 132, 264):
    cur = shift_frame(shift, list_only=True)
    s, diff = find_scroll(base, cur)
    d0 = _overlap_diff(base, cur, 0)
    r0 = _same_ratio(base, cur, 0)
    ok = "✓" if s == shift else "✗"
    print(f"  真实位移 {shift:4d} → 算出 {s:5d} {ok}   "
          f"(偏移0处 diff={d0:5.1f} same={r0:.2f})")

print("\n对照日志：用户实测 s=0 时 diff=4.0~9.9")
