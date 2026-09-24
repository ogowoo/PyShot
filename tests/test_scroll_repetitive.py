# -*- coding: utf-8 -*-
"""验证"行高度重复"假设：文件列表这类内容，行与行太像 → 真位移挤不进候选。

用户实测：本机 Explorer 手动慢慢滚，137 帧只有 1 帧匹配上，
`s=0` 时 diff 仅 8~17（白底为主，滚动只让文字行产生差异）——
这与"滚了一小段但位置算错"吻合，而不是"没滚动"。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

from scroller import Frame, _frame_keys, _row_key, find_scroll

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


W, H = 900, 700
SIDEBAR_W = 240
ROW_H = 22                      # 每行 22 像素（Explorer 行高）
PERIOD = 8                      # **关键**：列表内容每 8 行重复一次（行长得太像）
TEXT_W = 300


def make_doc(n=3000):
    """像 Explorer 文件列表：白底 + 每行一小块文字（按 PERIOD 重复）。"""
    rows = []
    for y in range(n):
        logical = (y // ROW_H) % PERIOD          # 重复模式
        base = bytearray([250, 250, 250] * W)
        if (y % ROW_H) in (6, 7, 8):             # 文字只占行中间几像素
            for x in range(300, 300 + TEXT_W):
                phase = (x // 6 + logical * 3) % 7
                if phase < 4:
                    for k in range(3):
                        base[x * 3 + k] = 30
        # 侧栏（静态）
        for x in range(SIDEBAR_W):
            for k in range(3):
                base[x * 3 + k] = 235
        rows.append(bytes(base))
    return rows


DOC = make_doc()


def frame_at(top: int) -> Frame:
    return Frame([DOC[top + i] for i in range(H)], W, H)


# ---------- 先确认这份合成数据确实是"高度重复"的 ----------
keys = _frame_keys(frame_at(0))
uniq = len(set(keys))
check("合成数据确实是高度重复的（行签名种类远少于行数）", uniq < H // 2,
      f"{uniq} 种签名 / {H} 行")

# ---------- 关键：重复内容上的位移能不能算对 ----------
for step in (22, 44, 66, 132):
    s, diff = find_scroll(frame_at(0), frame_at(step))
    check(f"重复行内容上位移 {step}px 能算对", s == step,
          f"得到 {s}（diff={diff:.1f}）")

# ---------- 没滚动仍要判 0 ----------
s0, _ = find_scroll(frame_at(0), frame_at(0))
check("重复内容上没滚动仍判 0", s0 == 0, f"得到 {s0}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("重复行内容测试通过 ✔")
