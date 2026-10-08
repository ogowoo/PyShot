# -*- coding: utf-8 -*-
"""自动隐藏黑色控制台（bootstrap.hide_own_console）。

用户要的功能：双击 PyShot.py 启动时，Python 会自带一个黑色终端窗口，
GUI 起来之后它还挂在任务栏里 —— 现在自动藏掉。

规则（都要测）：
  · 控制台是本进程自己的（双击/快捷方式启动）→ 藏（SW_HIDE）
  · 从 pwsh/cmd 里启动 → 控制台是共享的 → **不藏**（藏了会把用户的终端一起藏起来）
  · pythonw.exe / 没有控制台 → 不动
  · PYSHOT_CONSOLE=1 → 保留（排障用）
  · 出任何异常都不许让启动失败
  · main() 里确实调用了它，且在 --check-deps 之后（命令行输出不能被藏掉）
"""
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
sys.path.insert(0, HERE)

import bootstrap

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


class FakeK32:
    def __init__(self, hwnd=1234, procs=1):
        self.hwnd = hwnd
        self.procs = procs

    def GetConsoleWindow(self):
        return self.hwnd

    def GetConsoleProcessList(self, buf, n):
        for i in range(min(self.procs, n)):
            buf[i] = 1000 + i
        return self.procs


class FakeU32:
    def __init__(self):
        self.calls = []

    def ShowWindow(self, hwnd, cmd):
        self.calls.append((hwnd, cmd))
        return True


def run_with(k32, u32, env_console=None):
    """打桩跑一次 hide_own_console，返回 (状态, ShowWindow 调用记录)。"""
    orig_api = bootstrap._get_console_api
    bootstrap._get_console_api = lambda: (k32, u32)
    old = os.environ.get("PYSHOT_CONSOLE")
    try:
        if env_console is None:
            os.environ.pop("PYSHOT_CONSOLE", None)
        else:
            os.environ["PYSHOT_CONSOLE"] = env_console
        return bootstrap.hide_own_console(), u32.calls
    finally:
        bootstrap._get_console_api = orig_api
        if old is None:
            os.environ.pop("PYSHOT_CONSOLE", None)
        else:
            os.environ["PYSHOT_CONSOLE"] = old


# ---------- 1) 双击启动（独占控制台）→ 藏 ----------
st, calls = run_with(FakeK32(hwnd=4321, procs=1), FakeU32())
check("独占控制台 → 返回 hidden", st == "hidden", st)
check("藏窗口时传的是 SW_HIDE(0)，且目标是本控制台",
      calls == [(4321, 0)], str(calls))

# ---------- 2) 终端里启动（共享控制台）→ 不藏 ----------
u32 = FakeU32()
st, calls = run_with(FakeK32(hwnd=4321, procs=3), u32)
check("**共享控制台 → 返回 shared 且完全不碰窗口**",
      st == "shared" and calls == [], f"{st} {calls}")

# ---------- 3) 没有控制台（pythonw）→ none，不报错 ----------
u32 = FakeU32()
st, calls = run_with(FakeK32(hwnd=0, procs=0), u32)
check("无控制台 → none 且不调用 ShowWindow", st == "none" and calls == [],
      f"{st} {calls}")

# ---------- 4) PYSHOT_CONSOLE=1 → 保留 ----------
u32 = FakeU32()
st, calls = run_with(FakeK32(hwnd=4321, procs=1), u32, env_console="1")
check("PYSHOT_CONSOLE=1 → kept 且不动窗口", st == "kept" and calls == [],
      f"{st} {calls}")

# ---------- 5) 异常不能炸启动 ----------
class BoomK32:
    def GetConsoleWindow(self):
        raise RuntimeError("boom")

    def GetConsoleProcessList(self, buf, n):
        return 0

st, _ = run_with(BoomK32(), FakeU32())
check("API 抛异常 → 返回 error，不抛出", st == "error", st)

# ---------- 6) 真实环境冒烟：返回合法状态串；且绝不误藏共享控制台 ----------
st = bootstrap.hide_own_console()
check("真实环境返回合法状态",
      st in ("hidden", "shared", "none", "kept", "n/a", "error"), st)
# 本测试是从终端/运行器启动的，控制台必然是共享的 —— 不许返回 hidden
check("**在共享控制台里运行时不许藏**（保护用户的终端窗口）",
      st != "hidden" or os.environ.get("PYSHOT_CONSOLE") == "1", st)

# ---------- 7) main() 确实调用了，而且在 --check-deps 之后 ----------
src = Path(HERE, "main.py").read_text(encoding="utf-8")
i_call = src.index("hide_own_console()")
i_deps = src.index('"--check-deps" in sys.argv')
check("main() 里调用了 hide_own_console()", i_call > 0)
check("调用点在 --check-deps 分支之后（命令行输出不会被藏掉）",
      i_call > i_deps, f"{i_call} > {i_deps}")

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("控制台自动隐藏测试通过 ✔")
