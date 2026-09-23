# -*- coding: utf-8 -*-
"""选区里混着大块静止外壳时，必须按"会滚的那条带"算位移。

真机证据（本机 Citrix Workspace / 远程 OneDrive 文件列表，选区 660x380）：
  上方 171 行是静止的 ribbon + 列头（占 45%），下方 209 行才是会滚的列表；
  一次 1 格滚轮 ≈ 55/63px，远程画面还有"半像素错位 + 重编码"造成的噪声。
  修复前，请求 171px → 一次发 2 格（≈126px）时：
    · 真位移的精确占比被静止行稀释，逐像素差又到 19.7（阈值 12）
    · 全局/签名投票则被粗签名饱和，d=0 反而拿到 0.74 的高分
    → 判成"没滚动"，端到端输出还是 380px 高，拼不出长图
  修复后：真值 126 稳定命中（占比 0.74）。

本文件用确定性合成帧复现同一形状，并额外断言"把静止边缘裁掉这一步去掉
就会退回坏行为"，保证这条测试真的能抓住回归。
真机帧回放：~/.pyshot/scroll_debug/citrix3_*.png（本文件 (f) 段直接回放）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication

app = QApplication([])

import scroller
from scroller import Frame, find_scroll

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


W = 200
H = 600
CHROME = 270                  # 静止外壳占 45%（与真机 171/380 一致，也正是可裁的上限）
SHIFT = 126                   # 真机"一次发 2 格"量出来的真实位移（重叠 204 行，足够拼）


def _mix(k: int, i: int) -> int:
    """确定性伪随机 0..255：让每一行内容唯一、没有周期（否则匹配会撞上重复）。"""
    v = (k * 2654435761 + i * 40503 + 12345) & 0xFFFFFFFF
    v ^= v >> 13
    v = (v * 1274126177) & 0xFFFFFFFF
    return (v >> 7) & 0xFF


def chrome_row(y: int) -> bytes:
    """静止外壳（ribbon/列头）：内容只跟行号有关，两帧完全一致，且逐行不同。"""
    dark = {_mix(9000 + y, s) % W for s in range(6)}
    out = bytearray()
    for x in range(W):
        v = 40 if x in dark else 210 + (y * 3) % 40
        out += bytes((v, v, v))
    return bytes(out)


def list_row(k: int, jitter: int = 0) -> bytes:
    """文件列表的一行：白底 + 若干暗块，位置随 k 唯一变化。"""
    segs = set()
    for s in range(4):
        x0 = _mix(k, s) % (W - 12)
        segs.update(range(x0, x0 + 3 + _mix(k, s + 9) % 12))
    out = bytearray()
    for x in range(W):
        v = 40 if x in segs else 248
        out += bytes((max(0, min(255, v + jitter)),) * 3)
    return bytes(out)


def build_pair(shift: int, noisy: bool = False):
    """prev/cur：外壳不变，列表整体上移 shift 行。

    noisy=True 时给约 1/3 的列表行加 ±45 的编码噪声（精确占比掉到 0.9 以下、
    逐像素差升到 12 以上），只有"明显胜过 d=0"的判据才能救回来。
    """
    prev_rows = [chrome_row(y) for y in range(CHROME)]
    prev_rows += [list_row(k) for k in range(CHROME, H)]
    cur_rows = [chrome_row(y) for y in range(CHROME)]
    for k in range(CHROME, H):
        j = 45 if (noisy and k % 3 == 0) else 0
        cur_rows.append(list_row(k + shift, j))
    return Frame(prev_rows, W, H, 1.0), Frame(cur_rows, W, H, 1.0)


def without_crop(fn):
    """模拟"没裁静止边缘"的修复前行为。"""
    orig = scroller.static_strips
    scroller.static_strips = lambda *a, **k: (0, 0)
    try:
        return fn()
    finally:
        scroller.static_strips = orig


# ---------- (a) 静止外壳占 45%：也要算对 ----------
prev, cur = build_pair(SHIFT)
s, _ = find_scroll(prev, cur)
check(f"静止外壳占 45% 时，平移 {SHIFT}px 也要算对", s == SHIFT, f"得到 s={s}")

# ---------- (b) 噪声版：真位移占比 < 0.9 且逐像素差 > 12，仍要算对 ----------
pn, cn = build_pair(SHIFT, noisy=True)
sn, dn = find_scroll(pn, cn)
check(f"有编码噪声时 {SHIFT}px 也要算对（占比不足 0.9、像素差超阈值）",
      sn == SHIFT, f"得到 s={sn} diff={dn:.1f}")

# ---------- (c) 其他位移也对 ----------
for step in (24, 63, 96, 168):
    p2, c2 = build_pair(step)
    s2, _ = find_scroll(p2, c2)
    check(f"平移 {step}px 算对", s2 == step, f"得到 {s2}")

# ---------- (d) 没滚动 → 0，而不是硬报错 ----------
p0, c0 = build_pair(0)
s0, _ = find_scroll(p0, c0)
check("没滚动时判 0", s0 == 0, f"得到 {s0}")

# ---------- (e) 机制回归：不裁静止边缘就算不出真位移 ----------
# 真机上的原话是 find_scroll 返回 0（"没滚动"），端到端于是输出 380px 高；
# 噪声版在裁与不裁之间差异明显，这条断言就锁住了这次修复。
s_bad = without_crop(lambda: find_scroll(prev, cur)[0])
print(f"NOTE 无噪声时不裁也能算对（得到 {s_bad}）："
      f"真机那次失败是噪声 + 粗签名饱和共同造成的，所以下面这条才是关键")
s_bad_n = without_crop(lambda: find_scroll(pn, cn)[0])
check("**不裁静止边缘时（有编码噪声）算不出真位移** —— 这次修复的关键",
      s_bad_n != SHIFT, f"得到 s={s_bad_n}")

# 裁掉之后又必须变回正确（真机帧上也一样：citrix3_s2→s3 由 0 变 126）
s_good, _ = find_scroll(prev, cur)
check("裁掉静止边缘后恢复正确", s_good == SHIFT, f"得到 {s_good}")

# ---------- (f) 真机帧回放（本机存了 Citrix 帧时才跑，别的机器自动跳过） ----------
from pathlib import Path

from PySide6.QtGui import QPixmap

from scroller import pixmap_to_frame

DBG = Path.home() / ".pyshot" / "scroll_debug"
REAL = [
    ("citrix3_s0.png", "citrix3_s1.png", 55),        # 1 格滚轮（那次是 55px）
    ("citrix3_s1.png", "citrix3_s2.png", 63),        # 1 格滚轮
    ("citrix3_s2.png", "citrix3_s3.png", 126),       # 一次发 2 格 -240（修复前判 0）
    ("citrix3_raw2.png", "citrix3_raw3.png", 63),    # 直发 1 格
]
if all((DBG / a).exists() and (DBG / b).exists() for a, b, _ in REAL):
    for a, b, want in REAL:
        pa = pixmap_to_frame(QPixmap(str(DBG / a)))
        pb = pixmap_to_frame(QPixmap(str(DBG / b)))
        sr, _ = find_scroll(pa, pb)
        check(f"真机 Citrix 帧 {a} → {b} 位移 {want}px", sr == want, f"得到 {sr}")
else:
    print("NOTE 没有真机 Citrix 帧（~/.pyshot/scroll_debug），跳过回放")

# ---------- (g) 步长按"会滚的条带高"算，而不是整个选区 ----------
from PySide6.QtCore import QRect

from scroller import ScrollCapture


class _StubDriver:
    mode = "wheel"

    def __init__(self):
        self.steps = []

    def __call__(self, step):
        self.steps.append(step)


stub = _StubDriver()
cap = ScrollCapture(QRect(0, 0, 660, 380), grab_fn=lambda: QPixmap(1, 1),
                    driver=stub, interval_ms=1)
cap._prev = Frame([bytes(660 * 3)] * 380, 660, 380, 1.0)
cap._dpr = 1.0

cap._do_scroll()
first = stub.steps[-1]
check("首次滚动用小步试探（还没量出条带高）", first <= 60, f"得到 {first}")

cap._band_h = 208.0                      # 真机量出来的"会滚"高度（选区高 380）
cap._do_scroll()
second = stub.steps[-1]
check("量出条带高后按条带算步长（≤ 0.55×208）", 100 <= second <= 115,
      f"得到 {second}")

cap._band_h = 4000.0                     # 整屏都在滚
cap._do_scroll()
third = stub.steps[-1]
check("条带很高时不超过选区高度的 45%", third <= 380 * 0.45 + 1, f"得到 {third}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("静止外壳 + 滚动条带匹配测试通过 ✔")