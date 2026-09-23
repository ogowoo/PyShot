# -*- coding: utf-8 -*-
"""有损画面的滚动匹配测试（Citrix HDX / 远程桌面 / 硬件解码）。

真实用户症状：滚动截屏总是报"画面内容变化过快，无法对齐拼接"。
原因：HDX 送的是**有损视频流**，同一行每帧都被重新编码，字节不可能完全相同；
而原来的匹配是"整行字节哈希投票"，于是一行都对不上、连候选都提不出来。

这里用**加了噪声的合成帧**模拟有损源：位移必须照样能找出来；
同时验证"内容真的变了"仍要判失败（不能为了容忍噪声而胡乱匹配）。
"""
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYSHOT_LANG", "zh_CN")
os.environ["PYSHOT_SKIP_DEPS"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from scroller import Frame, find_scroll

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


WIDTH = 280


def make_frame(rows_bytes):
    return Frame(rows_bytes, WIDTH, len(rows_bytes))


def synth_tall(width=280, height=1400, seed=7):
    """造一张"有文字行"的合成长图：每行内容都不同，便于验证匹配唯一性。"""
    rnd = random.Random(seed)
    rows = []
    for y in range(height):
        row = bytearray()
        # 左侧"文字"块 + 右侧背景，行与行之间图案不同
        band = (y // 3) % 9
        for x in range(width):
            if 20 < x < 20 + 12 * ((y * 7) % 11 + 1) and band != 0:
                v = 40 + (y * 13) % 120
            else:
                v = 245 if band != 4 else 200
            row += bytes((v, v, v))
        rows.append(bytes(row))
    return rows


def window(rows, start, h):
    return make_frame(rows[start:start + h])


def add_noise(frame, amp=9, seed=11):
    """模拟有损编码：每像素加 ±amp 的噪声（同一位移下内容仍然"差不多"）。"""
    rnd = random.Random(seed)
    out = []
    for row in frame.rows:
        b = bytearray(row)
        for i in range(len(b)):
            v = b[i] + rnd.randint(-amp, amp)
            b[i] = 0 if v < 0 else (255 if v > 255 else v)
        out.append(bytes(b))
    return Frame(out, WIDTH, len(out))


rows = synth_tall()
H = 500
S = 137

clean_prev = window(rows, 0, H)
clean_cur = window(rows, S, H)

# ---------- 1) 干净画面：本来就能对上（基线）----------
s_clean, _ = find_scroll(clean_prev, clean_cur)
check("干净画面能匹配", s_clean == S, f"得到 {s_clean}，期望 {S}")

# ---------- 2) 有损画面（加噪声）：必须照样能匹配 ----------
noisy_cur = add_noise(clean_cur, amp=9)
# 先确认"噪声版本"确实用精确哈希对不上了（否则这条测试没意义）
same_rows = sum(1 for a, b in zip(clean_prev.rows[S:], noisy_cur.rows[:H - S])
                if a == b)
check("噪声帧确实没有完全相同的行（复现有损源特征）", same_rows == 0,
      f"{same_rows} 行完全相同")

t0 = time.perf_counter()
s_noisy, diff = find_scroll(clean_prev, noisy_cur)
cost = (time.perf_counter() - t0) * 1000
check("**有损画面也能匹配**（Citrix 场景的关键）", s_noisy == S,
      f"得到 {s_noisy}，期望 {S}；像素差 {diff:.1f}；耗时 {cost:.0f} ms")
check("抗噪匹配耗时可接受（< 2s）", cost < 2000, f"{cost:.0f} ms")

# 更强噪声也要能撑住
for amp in (14, 20):
    s_n, _ = find_scroll(clean_prev, add_noise(clean_cur, amp=amp, seed=amp))
    check(f"噪声 ±{amp} 仍能匹配", s_n == S, f"得到 {s_n}")

# ---------- 3) 没滚动：相同帧 → 0 ----------
s_same, _ = find_scroll(clean_prev, clean_prev)
check("完全相同的帧判为没滚动", s_same == 0, f"得到 {s_same}")
s_same_n, _ = find_scroll(clean_prev, add_noise(clean_prev, amp=9))
check("静止但有噪声的帧也判为没滚动（不误报滚动）", s_same_n in (0, -1),
      f"得到 {s_same_n}")

# ---------- 4) 内容真的变了 → 必须判失败（不能乱匹配）----------
other = window(rows, 700, H)
other = make_frame([bytes((255 - b if i % 3 == 0 else b)
                          for i, b in enumerate(r)) for r in other.rows])
s_bad, _ = find_scroll(clean_prev, other)
check("内容完全不同时判失败（不胡乱匹配）", s_bad == -1, f"得到 {s_bad}")

# ---------- 5) 位移 0 与边界 ----------
s_tiny, _ = find_scroll(clean_prev, window(rows, 1, H))
check("位移 1 像素也能识别", s_tiny == 1, f"得到 {s_tiny}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("有损画面滚动匹配测试通过 ✔")
