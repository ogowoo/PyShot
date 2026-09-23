# -*- coding: utf-8 -*-
"""滚动长截图：选区后自动向下滚动，逐帧截取并按重叠像素拼接。

工作流程
========
1. 用户在覆盖层框选一个可滚动区域（如浏览器页面）
2. ScrollCapture 启动：抓取首帧 → 发送滚轮滚动 → 等待渲染 → 再抓帧
3. 每帧与上一帧做重叠匹配，算出本次滚动的像素数 s，把新帧底部 s 行拼上去
4. 连续几帧没有新内容（滚到底）或用户点"停止"时结束，交给编辑器

拼接核心是纯函数 find_scroll()，可离屏单测。
"""
import ctypes
import ctypes.wintypes
import os
from pathlib import Path

from PySide6.QtCore import (QEventLoop, QObject, QPoint, QRect, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from i18n import tr

MOUSEEVENTF_WHEEL = 0x0800
user32 = ctypes.windll.user32          # 提到模块级，便于测试打桩


def _sleep_ms(ms: int):
    """等待若干毫秒，同时保持界面响应（处理事件）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ---------------------------------------------------------------- 图像帧
# 不依赖 numpy：一帧 = "每行 RGB 字节"的列表。纯 Python 足够快，
# 而且"行哈希投票"找重叠对静态界面截图比逐像素差值更准。

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


def pixmap_to_frame(pix: QPixmap) -> Frame:
    """QPixmap → Frame（只做一次拷贝）。"""
    img = pix.toImage().convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    data = bytes(img.constBits())
    rows = [data[y * bpl: y * bpl + w * 3] for y in range(h)]
    return Frame(rows, w, h, float(pix.devicePixelRatio() or 1.0))


def frame_to_pixmap(frame: Frame, dpr: float | None = None) -> QPixmap:
    """Frame → QPixmap。"""
    data = b"".join(frame.rows)
    img = QImage(data, frame.w, frame.h, frame.w * 3,
                 QImage.Format_RGB888).copy()
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(frame.dpr if dpr is None else dpr)
    return pix


def frame_diff(a: Frame, b: Frame, row_step: int = 4, col_step: int = 4) -> float:
    """两帧的平均绝对差（抽样），用于判断画面是否已稳定。"""
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


# ---- 兼容旧测试/诊断的 numpy 辅助（延迟导入，运行期完全不碰 numpy） ----

def pixmap_to_array(pix: QPixmap):
    """仅供测试/诊断：转成 numpy 数组（应用本身不使用）。"""
    import numpy as np
    img = pix.toImage().convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, img.sizeInBytes())
    return arr.reshape(h, img.bytesPerLine())[:, : w * 3].reshape(h, w, 3).copy()


def array_to_pixmap(arr, dpr: float = 1.0) -> QPixmap:
    """仅供测试/诊断：numpy 数组转 QPixmap。"""
    import numpy as np
    arr = np.ascontiguousarray(arr)
    h, w, _ = arr.shape
    img = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888).copy()
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(dpr)
    return pix


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


def _match_stats(prev: Frame, cur: Frame, s: int,
                 rows: int = 140, col_step: int = 6) -> tuple:
    """返回 (完全相同行占比, 平均像素差)。只有需要时才调用（较慢）。"""
    return _same_ratio(prev, cur, s, rows), _overlap_diff(prev, cur, s)


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
    """不管置信度，返回匹配最好的候选位移（用于诊断"多块独立滚动区域"等场景）。"""
    prev, cur = _as_frame(prev), _as_frame(cur)
    if cur.h != prev.h or cur.w != prev.w:
        return -1
    return _best_offset_and_ratio(prev, cur, min_overlap)[0]


def find_scroll(prev, cur, min_overlap: int = 60, thresh: float = 3.0,
                loose_thresh: float = 12.0, top_candidates: int = 6,
                min_same_ratio: float = 0.9) -> tuple[int, float]:
    """在 cur 中找 prev 向下滚动的像素数 s：prev[s:] 应与 cur[:H-s] 一致。

    算法：**行哈希投票定候选 + 行级精确比较定胜负**。
    - 相同行占比最高者为胜（静态界面截图能到 1.0），比逐像素差值更准
    - 再在胜者 ±4 内精修，消除"行内容重复"带来的偏差
    - 成本与图幅无关（固定抽样行数），比逐像素扫描快一个量级

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
                  max_ratio: float = 0.45) -> tuple[int, int]:
    """检测两帧间静止的上/下边缘行数。

    用户框选的区域可能包含不随内容滚动的部分（窗口边框、固定工具栏、
    底部明细面板）。这类"静止条带"必须排除，否则每一帧都会把它们当新内容拼进去。
    max_ratio 放到 0.45：复杂业务界面（主列表 + 固定明细面板）里固定区域往往很高。
    """
    prev, cur = _as_frame(prev), _as_frame(cur)
    H = prev.h
    limit = max(1, int(H * max_ratio))

    def same(r: int) -> bool:
        a, b = prev.rows[r], cur.rows[r]
        if a == b:
            return True
        # 每 4 个像素比较一次（三通道都算），与原 numpy 版严格程度一致
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


def content_band_residuals(prev, cur, s: int,
                           top: int, bottom: int, bands: int = 3) -> list:
    """在"已检测到的位移 s"下，检查内容区分成几带后是否都对得上。

    对不上（残差远大于其它带）说明那一带的滚动量和整体不一致 ——
    典型情况是选区里既有主列表又有固定/独立滚动的明细面板。
    返回每带的残差（无法判定的带为 None）。
    """
    prev, cur = _as_frame(prev), _as_frame(cur)
    out = []
    if bottom - top < 90 or s <= 0 or bands < 2:
        return out
    bands = min(bands, max(2, int((bottom - top) / (s * 1.3))))
    if (bottom - top) / bands <= s:          # 位移太大，分不了带
        return []
    step = max(1, (bottom - top) // bands)
    for i in range(bands):
        y0 = top + i * step
        y1 = bottom if i == bands - 1 else y0 + step
        if y1 - s <= y0:                     # 这一带装不下这个位移，跳过
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


# ---------------------------------------------------------------- 默认抓取/滚动

def make_default_grab(region: QRect):
    """按逻辑屏幕坐标区域抓帧。

    多屏 / 混合 DPI 下必须按"区域所在的显示器"抓取并按该屏 dpr 裁剪
    （用主屏 dpr 去裁所有屏会错位）。若常规抓屏是空白/纯色（远程桌面、
    虚拟化应用常见），再回退到 PrintWindow 让目标窗口自己渲染一遍。
    """
    from capture_utils import grab_region_printwindow, pixmap_is_blank
    from snipper import grab_logical_region, region_to_screen_pixels

    # 注意：用模块级已导入的 QGuiApplication（不要再局部 import），
    # 否则会绕过测试对 QGuiApplication 的打桩。
    def grab() -> QPixmap:
        out = grab_logical_region(region)
        if pixmap_is_blank(out):
            scr = QGuiApplication.screenAt(region.center()) \
                or QGuiApplication.primaryScreen()
            dpr = float(scr.devicePixelRatio() or 1.0)
            src = region_to_screen_pixels(region, scr.geometry(), dpr)
            alt = grab_region_printwindow(src, dpr)
            if alt is not None and not pixmap_is_blank(alt):
                return alt
        return out

    return grab


def make_default_scroll(region: QRect, notches: int = 3):
    """把光标移到区域中心并发送滚轮事件（向下滚动）。"""
    user32 = ctypes.windll.user32

    def scroll():
        QCursor.setPos(region.center())
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -120 * notches, 0)

    return scroll


# ---------------------------------------------------------------- 滚动输入驱动

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_PAGEDOWN, VK_SPACE, VK_DOWN = 0x22, 0x20, 0x28

# 各模式的"每单位输入能滚动多少内容像素"的初值与合理范围（会实测校准）
_UNIT_DEFAULTS = {"wheel": 100.0, "drag": 3.0, "key": 420.0}
_UNIT_BOUNDS = {"wheel": (5.0, 1500.0), "drag": (0.2, 400.0), "key": (20.0, 30000.0)}
_PROBE_START = 4.0        # 拖拽模式首次试探的像素（长文档滑块行程短，必须从小往大试）
_DRAG_MAX = 160.0         # 单次拖拽上限，避免一次把滑块拉到底


def _send_vk(vk: int):
    user32.keybd_event(vk, 0, 0, 0)
    _sleep_ms(18)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _drag_scrollbar(anchor: QPoint, dy: float, steps: int = 6):
    """在滚动条滑块上按住并向下拖拽 dy 像素（远程桌面里比滚轮可靠）。"""
    QCursor.setPos(anchor)
    _sleep_ms(30)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    for i in range(1, steps + 1):
        QCursor.setPos(QPoint(anchor.x(), int(anchor.y() + dy * i / steps)))
        _sleep_ms(12)
    _sleep_ms(25)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


class ScrollDriver:
    """把"想滚动多少内容像素"翻译成实际输入，并用实测位移自我校准。

    mode:
      wheel — 滚轮（默认；把光标移到区域中心后发滚轮）
      drag  — 在滚动条滑块上按住拖拽（远程桌面/Citrix 最可靠，步长可标定）
      key   — PageDown / 空格 / ↓（没有滚动条的应用）
    """

    def __init__(self, mode: str, region: QRect, anchor: QPoint | None = None,
                 key_vk: int = VK_PAGEDOWN):
        self.mode = mode
        self.region = QRect(region)
        self.anchor = QPoint(anchor) if anchor is not None else region.center()
        self.key_vk = key_vk
        self.px_per_unit = float(_UNIT_DEFAULTS.get(mode, 100.0))
        self.last_units = 0.0
        self.observations = 0
        self.moved_ever = False
        self.probe_px = _PROBE_START      # 拖拽模式：先用极小的步长试探
        self.probing = (mode == "drag")
        self.snapped = False              # 是否用系统接口校正过滑块位置
        self.native = None                # GetScrollInfo 可用时的原生滚动状态
        self.used_fallback = None         # 拖拽失效后自动降级到的模式

    # ---------- 前置 ----------
    def prepare(self):
        """开始前的准备。

        - 按键模式：把目标窗口拉到前台，否则按键会打到我们自己窗口
        - 拖拽模式：能读到原生滚动条状态就直接用 SetScrollInfo 设滚动位置
          （完全不动鼠标，绝对精准且不会溢出轨道）；读不到才用拖拽。
        """
        if self.mode == "key":
            try:
                from capture_utils import window_at
                hwnd = window_at(self.region.center().x(), self.region.center().y())
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(ctypes.wintypes.HWND(hwnd))
                    _sleep_ms(120)
            except Exception:               # noqa: BLE001
                pass
            return
        if self.mode != "drag":
            return
        try:
            from PySide6.QtGui import QGuiApplication
            from capture_utils import get_scroll_info_at, scrollbar_thumb_at
            dpr = 1.0
            scr = QGuiApplication.screenAt(self.anchor)
            if scr is not None:
                dpr = float(scr.devicePixelRatio() or 1.0)
            ax, ay = int(self.anchor.x() * dpr), int(self.anchor.y() * dpr)
            # 先尽量找到可程序化滚动的窗口（比拖拽可靠得多）
            self.native = get_scroll_info_at(ax, ay)
            if self.native is not None:
                return
            # 退而求其次：点偏了就把锚点校正到真实滑块中心
            thumb = scrollbar_thumb_at(ax, ay)
            if thumb is not None:
                center = QPoint(int((thumb.left() + thumb.width() / 2) / dpr),
                                int((thumb.top() + thumb.height() / 2) / dpr))
                if (center - self.anchor).manhattanLength() <= 60:
                    self.anchor = center
                    self.snapped = True
        except Exception:                   # noqa: BLE001
            pass

    # ---------- 执行 ----------
    def __call__(self, step_px: float):
        units = step_px / max(0.05, self.px_per_unit)
        if self.mode == "wheel":
            notches = int(min(15, max(1, round(units))))
            self.last_units = float(notches)
            QCursor.setPos(self.region.center())
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -120 * notches, 0)
        elif self.mode == "key":
            times = int(min(5, max(1, round(units))))
            self.last_units = float(times)
            for _ in range(times):
                _send_vk(self.key_vk)
        else:                            # drag
            if self.native is not None:
                # 原生滚动条：直接设滚动位置（不动鼠标，步长 = 视口的 45% 且绝对精准）
                info = self.native
                step_pos = max(1, int(info["page"] * 0.45))
                new_pos = min(info["max"], info["pos"] + step_pos)
                self.last_units = float(max(1, new_pos - info["pos"]))
                from capture_utils import set_scroll_pos
                set_scroll_pos(info["hwnd"], new_pos)
                info["pos"] = new_pos
                return
            if self.probing:
                dy = self.probe_px
            else:
                dy = float(min(_DRAG_MAX, max(4.0, units)))
            self.last_units = dy
            _drag_scrollbar(self.anchor, dy)
            # 关键：滑块已经被拖下去 dy，锚点必须跟着走。
            # 否则下一次会在原位置按下 —— 那里已经是轨道，变成翻页而不是继续拖拽。
            self.anchor = QPoint(self.anchor.x(), int(self.anchor.y() + dy))

    def recovery_after_jump(self) -> bool:
        """匹配失败（一次滚动太多，超出可拼接范围）时把步长改小再试。

        拖拽滚动条的"每像素滚动量"完全取决于内容长度（长文档滑块行程很短），
        事先无法得知，只能从小步试探并逐步收敛。最多试 4 次。
        """
        self._recovery_count = getattr(self, "_recovery_count", 0) + 1
        if self.observations >= 2 or self._recovery_count > 4:
            return False
        if self.mode == "drag":
            self.probing = True
            self.probe_px = max(1.5, self.probe_px / 2)
            self.px_per_unit = min(_UNIT_BOUNDS["drag"][1], self.px_per_unit * 2)
            return True
        lo, hi = _UNIT_BOUNDS.get(self.mode, (0.1, 10000.0))
        self.px_per_unit = min(hi, self.px_per_unit * 2)
        return True

    def observe(self, actual_px: int):
        """用实测位移校准"每单位输入滚动多少像素"。"""
        if self.last_units <= 0 or actual_px <= 0:
            return
        measured = actual_px / self.last_units
        lo, hi = _UNIT_BOUNDS.get(self.mode, (0.1, 10000.0))
        if not (lo <= measured <= hi):
            return                       # 明显被误匹配带偏，忽略这次
        weight = 0.6 if self.observations == 0 else 0.35
        self.px_per_unit = (1 - weight) * self.px_per_unit + weight * measured
        self.observations += 1
        if self.mode == "drag":
            self.probing = False         # 试探成功，之后按目标步长来

    def describe(self) -> str:
        return {"wheel": "滚轮", "drag": "拖拽滚动条", "key": "按键"}.get(self.mode, self.mode)


# ---------------------------------------------------------------- 进度控制条

class ScrollControlBar(QWidget):
    """浮在选区外的小条：显示帧数/总长，提供停止按钮。"""

    stopped = Signal()

    def __init__(self, region: QRect, manual: bool = False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.manual = manual
        self.title = ""
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget { background: #2f3542; color: white; border-radius: 6px; }"
            "QPushButton { background: #e53935; border: none; padding: 4px 14px;"
            "  border-radius: 4px; color: white; }"
            "QLabel { padding: 4px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        row = QHBoxLayout()
        self.label = QLabel(tr("滚动截图准备中…"))
        row.addWidget(self.label)
        btn = QPushButton("完成 (Enter)" if manual else "停止 (Esc)")
        btn.clicked.connect(self.stopped)
        row.addWidget(btn)
        lay.addLayout(row)
        if manual:
            hint = QLabel(tr("请用鼠标滚轮或 Page Down 自己滚动页面，滚到底后点「完成」"))
            hint.setStyleSheet("color: #aeb6c2; font-size: 11px;")
            lay.addWidget(hint)
        self.adjustSize()
        # 优先放在选区上方，放不下则放下方
        screen = QGuiApplication.screenAt(region.center()) or QGuiApplication.primaryScreen()
        sg = screen.availableGeometry()
        x = min(region.left(), sg.right() - self.width())
        y = region.top() - self.height() - 8
        if y < sg.top():
            y = region.bottom() + 8
        if y + self.height() > sg.bottom():
            y = region.top() + 8  # 实在没地方，放选区内顶部（会被拍到，用户可停止重来）
        self.move(x, y)

    def set_title(self, text: str):
        self.title = text
        self.adjustSize()

    def set_progress(self, frames: int, height: int, offset: int | None = None):
        prefix = f"{self.title} · " if self.title else ""
        text = prefix + tr("{}截图中… {} 帧 / {} px",
                                   tr("手动") if self.manual else tr("滚动"),
                                   frames, height)
        if offset:
            text += tr("（本帧 +{}）", offset)
        self.label.setText(text)
        self.adjustSize()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.stopped.emit()


# ---------------------------------------------------------------- 主控制器

class ScrollCapture(QObject):
    """滚动截图状态机。grab_fn / scroll_fn 可注入，便于离屏测试。"""

    finished_ok = Signal(QPixmap)
    failed = Signal(str)

    def __init__(self, region: QRect, grab_fn=None, scroll_fn=None,
                 interval_ms: int = 650, max_frames: int = 240,
                 manual: bool = False, driver=None, parent=None):
        super().__init__(parent)
        self.region = QRect(region)
        self.manual = manual            # 手动模式：用户自己滚动，不注入滚轮
        self.grab_fn = grab_fn or make_default_grab(region)
        self.driver = None              # 自动模式下的输入驱动（带自校准）
        if manual:
            self.scroll_fn = None
            self.interval_ms = min(interval_ms, 400)   # 采样更密，抓用户的滚动
        elif driver is not None:
            self.driver = driver
            self.scroll_fn = None
            self.interval_ms = interval_ms
        elif scroll_fn is not None:
            self.scroll_fn = scroll_fn  # 兼容：外部注入的滚动函数（无校准）
            self.interval_ms = interval_ms
        else:
            self.driver = ScrollDriver("wheel", region)
            self.scroll_fn = None
            self.interval_ms = interval_ms
        self.max_frames = max_frames

        self._acc: Frame | None = None    # 累积图像（行列表）
        self._prev: Frame | None = None   # 上一帧
        self._dpr = 1.0
        self._frames = 0
        self._no_progress = 0
        self._stop_requested = False
        self._busy = False               # 抓帧内含嵌套事件循环，防重入

        self.bar = ScrollControlBar(self.region, manual=manual)
        self.bar.stopped.connect(self.stop)

        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.bar.show()
        if self.driver is not None:
            self.driver.prepare()        # 按键模式先把目标窗口拉到前台
        self._tick()                     # 首帧
        self._timer.start()

    def stop(self):
        self._stop_requested = True

    def _do_scroll(self):
        """执行一次滚动：希望滚动约半屏内容（保证足够重叠，拼接才稳）。"""
        frame_h = 0
        if self._prev is not None:
            frame_h = self._prev.h / max(0.01, self._dpr)
        step = max(60.0, frame_h * 0.45)
        if self.driver is not None:
            self.driver(step)
        elif self.scroll_fn is not None:
            self.scroll_fn()

    # ---------- 内部 ----------
    def _grab_settled(self) -> QPixmap:
        """抓一帧"稳定"的画面。

        远程桌面 / 虚拟化应用的画面重绘慢，刚滚完就抓容易拍到画了一半的中间态，
        拼接就会错位。手动模式和拖拽滚动条模式都多等一会儿再抓。
        """
        frame = self.grab_fn()
        slow = self.manual or (self.driver is not None
                               and self.driver.mode == "drag")
        if not slow:
            return frame
        prev_fr = pixmap_to_frame(frame)
        for wait_ms in (90, 180):
            _sleep_ms(wait_ms)
            again = self.grab_fn()
            if again.isNull():
                break
            fr = pixmap_to_frame(again)
            if frame_diff(prev_fr, fr) < 1.0:     # 画面稳定了
                return again
            frame, prev_fr = again, fr
        return frame

    def _debug_dump(self, fr: Frame, note: str):
        """PYSHOT_SCROLL_DEBUG=1 时把每一帧和判定结果存盘，便于排查拼接异常。"""
        if os.environ.get("PYSHOT_SCROLL_DEBUG") != "1":
            return
        try:
            folder = Path.home() / ".pyshot" / "scroll_debug"
            folder.mkdir(parents=True, exist_ok=True)
            frame_to_pixmap(fr).save(str(folder / f"frame_{self._frames:03d}.png"))
            with open(folder / "offsets.txt", "a", encoding="utf-8") as f:
                f.write(f"frame {self._frames:03d}: {note}\n")
        except Exception:                   # noqa: BLE001
            pass

    def _check_multi_pane(self, fr: Frame, s: int,
                          top: int, bottom: int) -> str | None:
        """识别"一个选区里有多块独立滚动的区域"，返回错误文案或 None。"""
        res = content_band_residuals(self._prev, fr, s, top, bottom)
        valid = [r for r in res if r is not None]
        if len(valid) < 2:
            return None
        if max(valid) > max(6.0, min(valid) * 3.0 + 4.0):
            return ("选区里似乎包含多块独立滚动的区域（例如上方列表 + 下方明细面板），"
                    "它们滚动量不同，拼不到一起。\n"
                    "请只框选其中一个面板（不含固定的明细面板/工具栏）后重试。\n"
                    "（排查用：设环境变量 PYSHOT_SCROLL_DEBUG=1 会把每帧存到 "
                    "~/.pyshot/scroll_debug）")
        return None

    def _tick(self):
        if self._busy:                   # 上一次还在抓帧（内部有事件循环），跳过这一次
            return
        self._busy = True
        try:
            self._tick_once()
        finally:
            self._busy = False

    def _tick_once(self):
        if self._stop_requested or self._frames >= self.max_frames:
            self._finish()
            return
        try:
            frame = self._grab_settled()
        except Exception as ex:
            self.failed.emit(tr("抓帧失败：") + str(ex))
            self._cleanup()
            return
        if frame.isNull() or frame.width() < 8 or frame.height() < 80:
            self.failed.emit(tr("抓帧失败：区域过小或被遮挡"))
            self._cleanup()
            return

        # 首帧就是空白/纯色：多半是硬件加速或内容保护窗口（Citrix/RDP 常见），
        # 早点说清楚原因，别让用户等一场拼不出东西的滚动。
        if self._prev is None and self._frames == 0:
            from capture_utils import pixmap_is_blank
            if pixmap_is_blank(frame, min_std=1.2, black_level=10):
                self.failed.emit(
                    tr("抓到的画面是空白/纯色，无法拼接。\n"
                       "目标窗口（Citrix / 远程桌面 / Java 应用）多半在用硬件加速或"
                       "内容保护，GDI 抓屏拿不到内容。按顺序试：\n"
                       "① Citrix Workspace：关掉「使用硬件加速进行图形处理」；"
                       "服务端策略把「视频编解码压缩」设为不使用\n"
                       "② Java 应用：启动参数加 -Dsun.java2d.d3d=false "
                       "-Dsun.java2d.opengl=false -Dsun.java2d.noddraw=true"
                       "（强制走 GDI 绘制）\n"
                       "③ 托盘菜单用「滚动长截图（手动滚动）」：你自己滚，程序只拼帧\n"
                       "④ 把窗口最大化或调整大小后重试"))
                self._cleanup()
                return

        self._dpr = frame.devicePixelRatio()
        fr = pixmap_to_frame(frame)
        s = 0                                  # 本帧检测到的位移（首帧为 0）
        if self._prev is None:
            self._acc = fr
            self._debug_dump(fr, "首帧")
        else:
            if fr.h != self._prev.h or fr.w != self._prev.w:
                self.failed.emit(tr("抓帧尺寸发生变化，已停止（请确保窗口未移动/缩放）"))
                self._cleanup()
                return
            s, diff = find_scroll(self._prev, fr)
            if s < 0:
                # 一次滚太多（超出可拼接范围）：小步试探阶段可以自动减半重试，
                # 已经校准过就不折腾了，直接如实报错。
                if self.driver is not None and self.driver.recovery_after_jump():
                    self._prev = fr           # 画面确实动了，以新帧为基准继续
                    self._frames += 1
                    self._bar_call("set_progress", self._frames,
                                          int(self._acc.h / self._dpr))
                    self._do_scroll()
                    return
                # 手动模式下用户可能正在拖动滚动条，容忍几次再继续
                if self.manual and self._frames < self.max_frames:
                    self._prev = fr
                    self._frames += 1
                    self._bar_call("set_progress", self._frames,
                                          int(self._acc.h / self._dpr))
                    return
                # 已经拼出明显长图后的个别不可匹配帧（典型是滚到底时滑块抖动），
                # 不该当成失败丢掉整张图 —— 计数几次就正常收尾。
                if (self._frames >= 3 and self._acc is not None
                        and self._acc.h > fr.h * 1.5):
                    self._no_progress += 1
                    self._prev = fr
                    self._frames += 1
                    self._bar_call("set_progress", self._frames,
                                          int(self._acc.h / self._dpr))
                    if self._no_progress >= 2:
                        self._finish()
                    return
                # 匹配失败时先做一次"多块独立滚动区域"诊断，给出更具体的建议
                from scroller import best_candidate_offset
                guess = best_candidate_offset(self._prev, fr)
                if guess > 0:
                    t2, b2 = static_strips(self._prev, fr)
                    problem = self._check_multi_pane(fr, guess, t2, fr.h - b2)
                    if problem:
                        self.failed.emit(problem)
                        self._cleanup()
                        return
                self.failed.emit(
                    "画面内容变化过快，无法对齐拼接。\n"
                    + ("拖拽滚动条模式下最常见的原因：点在了滚动条的**轨道**上而不是**滑块**上——"
                       "那样会一次翻整页，无法拼接。请重新框选并点中滑块本身。\n"
                       if self.driver is not None and self.driver.mode == "drag" else
                       "（请关闭动画/视频后重试）\n"))
                self._cleanup()
                return
            if s == 0:
                self._no_progress += 1
            else:
                H = fr.h
                top, bpad = static_strips(self._prev, fr)
                bottom = H - bpad
                # 多块独立滚动区域（上方列表 + 下方明细面板）拼不出来，早点说清楚
                problem = self._check_multi_pane(fr, s, top, bottom)
                if problem:
                    self.failed.emit(problem)
                    self._cleanup()
                    return
                if self._frames == 1:
                    # 首次拼接：裁掉首帧的静止边缘，只保留真正的滚动内容区
                    kept = self._acc.rows[top:bottom]
                    self._acc = Frame(kept, self._acc.w, len(kept), self._acc.dpr)
                start = max(top, bottom - s)
                if bottom - start > 0:
                    self._acc.rows.extend(fr.rows[start:bottom])
                    self._acc.h = len(self._acc.rows)
                self._debug_dump(fr, f"拼接 +{s}px（静止边缘 top={top} bottom={bpad}）")
                self._no_progress = 0
                if self.driver is not None:
                    self.driver.moved_ever = True
                    self.driver.observe(s)      # 用实测位移校准步长
        self._prev = fr
        self._frames += 1
        self._bar_call("set_progress", self._frames,
                              int(self._acc.h / self._dpr),
                              s if s > 0 else None)
        # 拖拽没生效会先自动降级到滚轮重试（见下方 no_progress 分支）；
        # 这里不再硬失败。
        # 自动模式：连续几帧没新内容说明滚到底了；手动模式由用户点"完成"结束
        if not self.manual and self._no_progress >= 3:
            d = self.driver
            if (d is not None and d.mode == "drag" and not d.moved_ever
                    and d.used_fallback is None):
                # 拖拽一直没用（多半没点中滑块/该应用不吃拖拽）→ 自动改滚轮再试
                d.used_fallback = "wheel"
                d.mode = "wheel"
                d.px_per_unit = _UNIT_DEFAULTS["wheel"]
                self._no_progress = 0
                self._bar_call("set_title", "拖拽没生效，改用滚轮重试")
                self._bar_call("set_progress", self._frames,
                                      int(self._acc.h / self._dpr))
                self._do_scroll()
                return
            if d is not None and not d.moved_ever and d.used_fallback == "wheel":
                self.failed.emit(
                    tr("拖拽和滚轮都没能让页面滚动。\n"
                    "可能原因：点击位置不在滚动区域，或该窗口不响应注入的输入。\n"
                    "建议改用「滚动长截图（PageDown 自动滚动）」或「手动滚动」。"))
                self._cleanup()
                return
            self._finish()
            return
        self._do_scroll()

    def _finish(self):
        self._cleanup()
        if self._acc is None:
            self.failed.emit(tr("没有抓到任何内容"))
            return
        self.finished_ok.emit(frame_to_pixmap(self._acc, self._dpr))

    def _cleanup(self):
        self._timer.stop()
        if self.bar is not None:
            # 控制条可能已经被 Qt 回收（例如父窗口先销毁）——
            # 直接调方法会抛 "Internal C++ object already deleted"，这里显式判活。
            try:
                import shiboken6
                alive = shiboken6.isValid(self.bar)
            except Exception:      # noqa: BLE001
                alive = True
            if alive:
                self.bar.hide()
                self.bar.deleteLater()
            self.bar = None       # 之后所有 set_progress/set_title 都会跳过

    def _bar_call(self, method: str, *args):
        """安全地调用控制条方法（对象已销毁时静默跳过）。"""
        bar = self.bar
        if bar is None:
            return
        try:
            import shiboken6
            if not shiboken6.isValid(bar):
                return
        except Exception:          # noqa: BLE001
            pass
        try:
            getattr(bar, method)(*args)
        except RuntimeError:       # 对象已删除
            self.bar = None
