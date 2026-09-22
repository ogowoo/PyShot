# -*- coding: utf-8 -*-
"""stitch.py —— 纯 Python 滚动拼接核心（零依赖，Qt 版与 Tk 版共用）。

一帧 = 每行 RGB 字节的列表。用"行哈希投票"找位移候选，再用"行级精确比较"
定胜负 —— 对静态界面截图比逐像素差值法又准又快（1~2ms/帧）。
"""
import ctypes
import ctypes.wintypes


class Frame:
    __slots__ = ("rows", "w", "h", "dpr")

    def __init__(self, rows, w: int, h: int, dpr: float = 1.0):
        self.rows = rows            # [bytes, ...]，每行 w*3 字节
        self.w = w
        self.h = h
        self.dpr = dpr

    @classmethod
    def from_array(cls, arr) -> "Frame":
        """测试用：从 numpy 数组构造。"""
        h, w = int(arr.shape[0]), int(arr.shape[1])
        return cls([arr[y].tobytes() for y in range(h)], w, h, 1.0)

    def copy(self) -> "Frame":
        return Frame(list(self.rows), self.w, self.h, self.dpr)


def _as_frame(x) -> Frame:
    """接受 Frame 或（测试用的）numpy 数组。"""
    if isinstance(x, Frame):
        return x
    if hasattr(x, "shape") and hasattr(x, "__getitem__"):
        return Frame.from_array(x)
    raise TypeError(f"需要 Frame 或数组，收到 {type(x).__name__}")


def _same_ratio(prev: Frame, cur: Frame, s: int, rows: int = 140) -> float:
    """重叠区域中"逐字节完全相同的行"占比（只做 bytes 比较，极快）。"""
    span = prev.h - s
    if span <= 0:
        return 0.0
    step = max(1, span // rows)
    same = total = 0
    for y in range(0, span, step):
        total += 1
        if prev.rows[s + y] == cur.rows[y]:
            same += 1
    return same / max(1, total)


def _overlap_diff(prev: Frame, cur: Frame, s: int,
                  row_step: int = 4, col_step: int = 6) -> float:
    """重叠区域的平均绝对差（稀疏抽样，仅作兜底判断）。"""
    total = n = 0
    for y in range(0, prev.h - s, row_step):
        a = prev.rows[s + y]
        b = cur.rows[y]
        if a == b:
            continue
        for x in range(0, len(a), col_step * 3):
            total += abs(a[x] - b[x]) + abs(a[x + 1] - b[x + 1]) \
                + abs(a[x + 2] - b[x + 2])
            n += 3
    return total / max(1, n) if n else 0.0


def _match_stats(prev: Frame, cur: Frame, s: int,
                 rows: int = 140, col_step: int = 6) -> tuple:
    """返回 (完全相同行占比, 平均像素差)。"""
    return _same_ratio(prev, cur, s, rows), _overlap_diff(prev, cur, s)


def _best_offset_and_ratio(prev: Frame, cur: Frame, min_overlap: int,
                           top_candidates: int = 6) -> tuple:
    """行哈希投票 + 精修，返回 (最佳候选位移, 相同行占比)。位移 -1 表示没候选。"""
    H = prev.h
    sig_cur = {}
    for r in range(H):
        sig_cur.setdefault(hash(cur.rows[r]), []).append(r)
    votes = {}
    for r in range(H):
        for rc in sig_cur.get(hash(prev.rows[r]), ())[:6]:
            s = r - rc
            if 0 <= s <= H - min_overlap:
                votes[s] = votes.get(s, 0) + 1
    if not votes:
        return -1, 0.0
    candidates = [s for s, _ in
                  sorted(votes.items(), key=lambda kv: -kv[1])[:top_candidates]]
    if 0 not in candidates:
        candidates.append(0)

    def best_of(cands):
        ratios = [(s, _same_ratio(prev, cur, s)) for s in cands]
        top = max(r for _, r in ratios)
        tied = [s for s, r in ratios if r >= top - 1e-9]
        if len(tied) > 1:      # 打平时用像素差细分（最多 3 个，避免慢路径）
            scored = [(s, _overlap_diff(prev, cur, s)) for s in tied[:3]]
            return min(scored, key=lambda kv: kv[1])[0], top
        return tied[0], top

    best_s, best_same = best_of(candidates)
    if best_s > 0:             # 精修 ±4，消除"行内容重复"带来的偏差
        cands = list(range(max(1, best_s - 4),
                           min(H - min_overlap, best_s + 4) + 1))
        s2, same2 = best_of(cands)
        if same2 > best_same + 1e-9:
            best_s, best_same = s2, same2
    return best_s, best_same


def best_candidate_offset(prev, cur, min_overlap: int = 60) -> int:
    """不管置信度，返回匹配最好的候选位移（诊断"多块独立滚动区域"用）。"""
    prev, cur = _as_frame(prev), _as_frame(cur)
    if cur.h != prev.h or cur.w != prev.w:
        return -1
    return _best_offset_and_ratio(prev, cur, min_overlap)[0]


def find_scroll(prev, cur, min_overlap: int = 60, thresh: float = 3.0,
                loose_thresh: float = 12.0, top_candidates: int = 6,
                min_same_ratio: float = 0.9) -> tuple:
    """在 cur 中找 prev 向下滚动的像素数 s：prev[s:] 应与 cur[:H-s] 一致。

    返回 (s, 差异值)。s == 0 表示没变化（到底了）；s == -1 表示匹配失败。
    """
    prev, cur = _as_frame(prev), _as_frame(cur)
    H = prev.h
    if cur.h != H or cur.w != prev.w:
        return -1, float("inf")
    if prev.rows == cur.rows:            # 整帧相同 → 没滚动
        return 0, 0.0

    best_s, best_same = _best_offset_and_ratio(prev, cur, min_overlap,
                                               top_candidates)
    if best_s < 0:
        return -1, float("inf")
    if best_s == 0:
        diff = _overlap_diff(prev, cur, 0)
        return (0, diff) if diff < thresh else (-1, diff)
    if best_same >= min_same_ratio:
        return best_s, 0.0
    diff = _overlap_diff(prev, cur, best_s)
    if diff < loose_thresh:
        return best_s, diff
    return -1, diff


def static_strips(prev, cur, thresh: float = 3.0,
                  max_ratio: float = 0.45) -> tuple:
    """检测两帧间静止的上/下边缘行数（窗口边框、固定工具栏、明细面板）。"""
    prev, cur = _as_frame(prev), _as_frame(cur)
    H = prev.h
    limit = max(1, int(H * max_ratio))

    def same(r: int) -> bool:
        a, b = prev.rows[r], cur.rows[r]
        if a == b:
            return True
        total = n = 0
        for x in range(0, len(a), 12):
            total += abs(a[x] - b[x]) + abs(a[x + 1] - b[x + 1]) \
                + abs(a[x + 2] - b[x + 2])
            n += 3
        return total / max(1, n) < thresh

    top = 0
    while top < limit and same(top):
        top += 1
    bottom = 0
    while bottom < limit and same(H - 1 - bottom):
        bottom += 1
    return top, bottom


def content_band_residuals(prev, cur, s: int, top: int, bottom: int,
                           bands: int = 3) -> list:
    """检查内容区各带在位移 s 下是否一致（识别多块独立滚动区域）。"""
    prev, cur = _as_frame(prev), _as_frame(cur)
    out = []
    if bottom - top < 90 or s <= 0 or bands < 2:
        return out
    bands = min(bands, max(2, int((bottom - top) / (s * 1.3))))
    if (bottom - top) / bands <= s:
        return []
    step = max(1, (bottom - top) // bands)
    for i in range(bands):
        y0 = top + i * step
        y1 = bottom if i == bands - 1 else y0 + step
        if y1 - s <= y0:
            out.append(None)
            continue
        total = n = 0
        for y in range(y0, y1 - s, 4):
            a, b = prev.rows[y + s], cur.rows[y]
            if a == b:
                continue
            for x in range(0, len(a), 12):
                total += abs(a[x] - b[x]) + abs(a[x + 1] - b[x + 1]) \
                    + abs(a[x + 2] - b[x + 2])
                n += 3
        out.append(total / max(1, n) if n else 0.0)
    return out


def frame_diff(a: Frame, b: Frame, row_step: int = 4,
               col_step: int = 4) -> float:
    """两帧的平均绝对差（抽样），用于判断画面是否稳定。"""
    if a.h != b.h or a.w != b.w:
        return float("inf")
    total = n = 0
    for y in range(0, a.h, row_step):
        ra, rb = a.rows[y], b.rows[y]
        for x in range(0, a.w * 3, col_step * 3):
            total += abs(ra[x] - rb[x]) + abs(ra[x + 1] - rb[x + 1]) \
                + abs(ra[x + 2] - rb[x + 2])
            n += 3
    return total / max(1, n)
