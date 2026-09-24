# -*- coding: utf-8 -*-
"""跑 tests/ 下的所有测试。

用法::

    python tools/run_tests.py                # 离线套件（默认；跳过需要真实桌面的）
    python tools/run_tests.py --live         # 连需要"桌面已解锁/真实窗口"的也一起跑
    python tools/run_tests.py --list         # 只列出会跑哪些
    python tools/run_tests.py test_help      # 只跑名字匹配这几个的
    python tools/run_tests.py -v             # 失败时把完整输出也打出来

约定：测试都在 `tests/`，自己把**项目根**加进 sys.path，所以随便从哪个目录调用都能跑。
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# 需要"真实桌面已解锁 / 真实窗口"的套件：默认跳过（无人值守时会假失败）
LIVE = {
    "test_scroll_live.py",          # 需要真实可滚窗口
    "test_drag_scroll_live.py",     # 需要真实滚动条
    "test_printwindow_live.py",     # 需要真实窗口
    "test_point_passthrough_live.py",
    "test_fullscreen_live.py",      # 真的全屏抓一遍
    "test_first_capture_latency.py",   # 量的是真实抓屏延迟
    "test_tray_mask.py",            # 从托盘真截一次图
}


def collect(patterns: list) -> list:
    files = sorted(TESTS.glob("test_*.py"))
    if patterns:
        files = [f for f in files
                 if any(p in f.stem for p in patterns)]
    return files


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("patterns", nargs="*", help="只跑名字匹配这些的测试")
    ap.add_argument("--live", action="store_true", help="连 live 套件一起跑")
    ap.add_argument("--list", action="store_true", help="只列出将要跑的测试")
    ap.add_argument("-v", "--verbose", action="store_true", help="失败时打印完整输出")
    args = ap.parse_args()

    files = collect(args.patterns)
    skipped = [] if args.live else [f for f in files if f.name in LIVE]
    todo = [f for f in files if args.live or f.name not in LIVE]

    if args.list:
        for f in todo:
            print("  会跑:", f.name)
        for f in skipped:
            print("  跳过（--live 可跑）:", f.name)
        return 0

    print(f"PyShot 测试：{len(todo)} 个套件"
          + (f"（另有 {len(skipped)} 个需要真实桌面，加 --live 才跑）" if skipped else ""))
    print("=" * 72)

    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # 注意：**不要**在这里设 PYSHOT_SKIP_DEPS —— 各测试自己按需设（有的测试
    # 专门要验证"不跳过、真去装"，在外部设了会把它的子进程一起带偏）。
    env.pop("PYSHOT_SKIP_DEPS", None)

    failed, passed = [], []
    t0 = time.perf_counter()
    for f in todo:
        t = time.perf_counter()
        try:
            p = subprocess.run([sys.executable, str(f)], cwd=str(ROOT), env=env,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired:
            code, out = 124, "超时（>900s）"
        dt = (time.perf_counter() - t) * 1000
        lines = [ln for ln in out.splitlines() if ln.strip()]
        tail = lines[-1] if lines else "(无输出)"
        marks = [ln for ln in lines if ln.startswith("FAIL")]
        if code == 0:
            passed.append(f.name)
            print(f"  ✓ {f.name:<34} {dt:6.0f} ms  {tail[:60]}")
        else:
            failed.append((f, out))
            print(f"  ✗ {f.name:<34} {dt:6.0f} ms  {tail[:60]}")
            for m in marks[:3]:
                print(f"      {m[:100]}")

    print("=" * 72)
    print(f"通过 {len(passed)} / {len(todo)}"
          f"，总耗时 {(time.perf_counter() - t0):.1f} s")
    if skipped:
        print(f"跳过 {len(skipped)} 个需要真实桌面的套件："
              + ", ".join(f.name for f in skipped))
    if failed:
        print("\n失败详情：")
        for f, out in failed:
            print(f"--- {f.name} ---")
            body = out.splitlines()
            print("\n".join(body if args.verbose else body[-12:]))
        return 1
    print("全部通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
