# -*- coding: utf-8 -*-
"""diag.py —— 全链路诊断日志（默认关闭，排查问题时才开）。

开启方式（任选其一，等价）::

    set PYSHOT_DEBUG=1
    set PYSHOT_CAPTURE_DEBUG=1     # 旧名字，兼容

输出到**控制台**和 ``~/.pyshot/debug.log``（超过 512KB 自动截断保留后半段）。
每行都带**墙钟时间 + 毫秒 + 相对启动的毫秒**，还有每段操作的**耗时**，
所以"双击之后到底慢在哪一步"能直接从日志看出来。

用法::

    from diag import log, timed, exc, dump_env
    log("截图", "触发")
    with timed("抓屏"):            # 退出时自动记一行"耗时 xx ms"
        frame = grab()
    exc("打开编辑器失败")
"""
import os
import time
import traceback
from pathlib import Path

LOG_PATH = Path(os.environ.get("PYSHOT_DEBUG_LOG")
                or (Path.home() / ".pyshot" / "debug.log"))
DIAG_MAX_BYTES = 512 * 1024
_T0 = time.perf_counter()


def enabled() -> bool:
    """是否开启诊断日志。"""
    return bool(os.environ.get("PYSHOT_DEBUG")
                or os.environ.get("PYSHOT_CAPTURE_DEBUG"))


def _stamp() -> str:
    now = time.time()
    return (f"{time.strftime('%H:%M:%S', time.localtime(now))}"
            f".{int(now * 1000) % 1000:03d}"
            f" (+{(time.perf_counter() - _T0) * 1000:8.1f}ms)")


def log(tag: str, *parts):
    """记一行诊断日志（未开启时零开销返回）。"""
    if not enabled():
        return
    line = f"{_stamp()} {tag}: " + " ".join(str(p) for p in parts)
    try:
        print(line, flush=True)
    except Exception:                              # noqa: BLE001
        pass
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # 轮转：只留最后一半，避免日志无限长大
        if LOG_PATH.stat().st_size > DIAG_MAX_BYTES:
            data = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            LOG_PATH.write_text("……（日志过长，已截断前段）……\n"
                                + data[-(DIAG_MAX_BYTES // 2):], encoding="utf-8")
    except Exception:                              # noqa: BLE001
        pass


class timed:
    """上下文管理器：记下这段操作的耗时。

    用法::

        with timed("抓屏", "屏0"):   # 进入/退出各记一行，退出带耗时
            ...
    """

    def __init__(self, tag: str, *extra):
        self.tag = tag
        self.extra = extra
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.perf_counter()
        if enabled():
            log(f"{self.tag}·开始", *self.extra)
        return self

    def __exit__(self, *exc_info):
        if enabled():
            cost = (time.perf_counter() - self.t0) * 1000
            tail = ("异常=" + repr(exc_info[1])) if exc_info and exc_info[0] \
                else "OK"
            log(f"{self.tag}·结束", f"耗时 {cost:.1f} ms", tail, *self.extra)
        return False


def exc(tag: str, err=None):
    """记一条异常（带完整堆栈）。"""
    if not enabled():
        return
    if err is None:
        log(tag, "异常:\n" + traceback.format_exc())
    else:
        log(tag, f"异常 {type(err).__name__}: {err}")


def dump_env(extra: str = ""):
    """开一次环境快照：录屏/多屏/缩放问题经常就差这些信息。"""
    if not enabled():
        return
    try:
        import PySide6
        qt = PySide6.__version__
    except Exception:                              # noqa: BLE001
        qt = "?"
    log("环境", f"pid={os.getpid()} python={os.sys.version.split()[0]} "
                f"Qt={qt} platform={os.environ.get('QT_QPA_PLATFORM') or '默认'} "
                f"cwd={os.getcwd()} {extra}")
    try:
        from PySide6.QtGui import QGuiApplication
        for i, scr in enumerate(QGuiApplication.screens()):
            g = scr.geometry()
            log("环境·屏幕", f"#{i} {scr.name()} geo=({g.x()},{g.y()},"
                             f"{g.width()}x{g.height()}) dpr={scr.devicePixelRatio()}"
                             f" primary={scr is QGuiApplication.primaryScreen()}")
    except Exception as e:                         # noqa: BLE001
        log("环境·屏幕", f"枚举失败: {e}")


def install_excepthook():
    """把未捕获异常也写进日志（托盘常驻进程崩了只有它留得下证据）。"""
    if not enabled():
        return
    import sys

    def _hook(etype, value, tb):
        try:
            log("未捕获异常", "".join(traceback.format_exception(etype, value, tb)))
        except Exception:                          # noqa: BLE001
            pass
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = _hook
