# -*- coding: utf-8 -*-
"""复现 + 验证：区域里同时有"静态侧栏"和"滚动内容"时，位移必须算在动的部分上。

用户实测（本机普通 Explorer，手动慢慢滚）：137 帧里只有 1 帧匹配上，
日志表现为大量 `s=0 diff=8~17` —— 内容确实变了，但最佳对齐被锚在 0。
原因：区域里左侧导航栏是静态的，整行哈希/签名把它的完全吻合当成了"最佳对齐"，
真正滚动的右侧列表反而被压过去了。
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

from scroller import Frame, find_scroll

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


SIDEBAR_W = 240          # 左侧静态导航栏宽度
W = 900                  # 总宽
H = 700                  # 视口高度


def sidebar_row():
    """静态侧栏的一行（每帧都一样）。"""
    return bytes([235, 236, 240] * SIDEBAR_W)


def list_row(y):
    """右侧列表的一行（随 y 变化，滚动时才会变）。"""
    band = (y // 4) % 13
    out = bytearray()
    for x in range(W - SIDEBAR_W):
        if band != 0 and (x // 7) % 3 == 0:
            v = 40 + (y * 17) % 150
        else:
            v = 250
        out += bytes((v, v, v))
    return bytes(out)


def make_scroll_doc():
    """造一份"列表文档"：按行给出 (侧栏 + 列表) 的原始内容。"""
    rows = []
    for y in range(3000):
        rows.append(sidebar_row() + list_row(y))
    return rows


DOC = make_scroll_doc()


def frame_at(top: int, seal: int = 0) -> Frame:
    """视口：侧栏每帧都一样（静态），列表随 top 滚动。"""
    rows = []
    for i in range(H):
        y = top + i
        if seal:                       # 模拟编码噪声
            rnd = random.Random(seal * 100000 + i)
            base = bytearray(DOC[y])
            for k in range(0, len(base), 11):
                v = base[k] + rnd.randint(-6, 6)
                base[k] = 0 if v < 0 else (255 if v > 255 else v)
            rows.append(bytes(base))
        else:
            rows.append(DOC[y])
    return Frame(rows, W, H)


# ---------- 1) 纯滚动内容（没有静态侧栏干扰）应当能匹配 ----------
plain_rows = [list_row(y) for y in range(3000)]
PLAIN = [r for r in plain_rows]


def plain_frame(top, h=H):
    return Frame([PLAIN[top + i] for i in range(h)], W - SIDEBAR_W, h)


s_plain, _ = find_scroll(plain_frame(0), plain_frame(45))
check("有静态侧栏干扰时：先确认纯列表能匹配（基线）", s_plain == 45,
      f"得到 {s_plain}，期望 45")

# ---------- 2) 带静态侧栏：这就是用户遇到的情况 ----------
s_mixed, diff = find_scroll(frame_at(0), frame_at(45))
check("**带静态侧栏时也能算出真实位移**（当前实现会失败）", s_mixed == 45,
      f"得到 {s_mixed}，期望 45（diff={diff:.1f}）")

# ---------- 3) 带侧栏 + 编码噪声 ----------
s_noisy, diff_n = find_scroll(frame_at(0), frame_at(45, seal=3))
check("带侧栏 + 噪声仍要算对", s_noisy == 45,
      f"得到 {s_noisy}，期望 45（diff={diff_n:.1f}）")

# ---------- 4) 大位移也要对（用户手动滚得快时）----------
for step in (120, 300, 500):
    s_big, _ = find_scroll(frame_at(0), frame_at(step))
    check(f"位移 {step}px 能算对", s_big == step, f"得到 {s_big}")

# ---------- 5) 真的没滚动时仍要判 0（不能把静态侧栏当成滚动）----------
s_still, _ = find_scroll(frame_at(0), frame_at(0))
check("没滚动时判 0", s_still == 0, f"得到 {s_still}")

# ---------- 6) 只有侧栏在变（列表没滚）→ 应当判 0 ----------
side_changed = []
for i in range(H):
    r = bytearray(DOC[i])
    r[(i * 3) % SIDEBAR_W] = 100            # 侧栏里有个闪烁的像素
    side_changed.append(bytes(r))
s_side, _ = find_scroll(frame_at(0), Frame(side_changed, W, H))
check("只有侧栏在变时仍判没滚动", s_side in (0, -1), f"得到 {s_side}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("静态侧栏干扰测试通过 ✔")
