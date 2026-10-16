# -*- coding: utf-8 -*-
"""真实自动安装测试：在干净 venv 里验证"缺库 → 自动 pip 安装 → 可导入"。

用 six（几十 KB）代替 PySide6 验证安装链路，避免下载上百 MB。
**需要联网**：网络不通时会跳过/快速失败，绝不会把测试套件挂住（见下面的看门狗）。
"""
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 项目根（本文件在子目录里）
VENV = os.path.join(os.path.dirname(HERE), "psvenv")   # 短路径，避开长路径问题

# 子进程统一用 UTF-8 输出，避免中文提示在 cp1252 控制台解码失败。
# 关键：**必须**摘掉 PYSHOT_SKIP_DEPS —— 本测试就是要验证"不跳过、真去装"，
# 从外部环境（比如测试运行器）继承到这个开关会让 bootstrap 直接返回 True。
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
CHILD_ENV.pop("PYSHOT_SKIP_DEPS", None)
# 本测试要真的联网装包：网络不好时 pip 会长时间 stall，所以处处设上限。
PIP_TIMEOUT = 180
# 看门狗：subprocess 的 timeout 只能杀掉**直接**子进程，pip 是孙进程 ——
# 它仍然握着管道，communicate() 会一直等（实测挂过 900 秒）。所以再加一层
# 进程级看门狗，到点直接 os._exit，保证套件不会被挂住。
WATCHDOG = 300


def _bail(reason: str):
    print(f"FAIL {reason}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(2)


_timer = threading.Timer(
    WATCHDOG,
    lambda: _bail(f"本测试整体超过 {WATCHDOG} 秒 —— 多半是 pip 连不上 PyPI"
                  f"（网络问题，不是代码问题）"))
_timer.daemon = True
_timer.start()

RUN_KW = dict(capture_output=True, text=True, encoding="utf-8",
              errors="replace", env=CHILD_ENV)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


venv_py = os.path.join(VENV, "Scripts", "python.exe")
if not os.path.exists(venv_py):
    print("创建干净虚拟环境 …")
    r = subprocess.run([sys.executable, "-m", "venv", VENV], **RUN_KW)
    if r.returncode != 0:
        print(r.stdout[-1500:], r.stderr[-1500:])
        sys.exit("venv 创建失败")
check("venv 已就绪", os.path.exists(venv_py), venv_py)

# 保证干净起点：先把 six 卸掉，使测试可重复运行
subprocess.run([venv_py, "-m", "pip", "uninstall", "-y", "six"], **RUN_KW,
               timeout=120)
probe_missing = subprocess.run([venv_py, "-c", "import six"], **RUN_KW)
check("venv 初始没有 six", probe_missing.returncode != 0)

# 用 bootstrap 的自动安装能力把它装上
probe = (
    "import sys; sys.path.insert(0, r'%s');"
    "from bootstrap import ensure_deps, missing_packages;"
    "before = missing_packages([('six','six')]);"
    "ok = ensure_deps([('six','six')]);"
    "after = missing_packages([('six','six')]);"
    "print('BEFORE', before); print('OK', ok); print('AFTER', after)"
) % HERE
try:
    r = subprocess.run([venv_py, "-c", probe], **RUN_KW, timeout=PIP_TIMEOUT)
except subprocess.TimeoutExpired:
    print(f"FAIL 自动安装在 {PIP_TIMEOUT} 秒内没完成 —— 多半是 pip 连不上 PyPI"
          f"（网络问题，不是代码问题）")
    sys.exit(1)
print("--- 子进程输出 ---")
print((r.stdout or "").strip()[-2000:])
if r.returncode != 0:
    print((r.stderr or "").strip()[-2000:])
check("自动安装流程返回成功", "OK True" in (r.stdout or "") and "AFTER []" in (r.stdout or ""))
check("安装前确实检测到缺失", "BEFORE ['six']" in (r.stdout or ""))

# 安装后再真的导入一次
r2 = subprocess.run([venv_py, "-c", "import six; print('six', six.__version__)"],
                    **RUN_KW, timeout=60)
check("安装后可以导入 six", r2.returncode == 0 and "six" in (r2.stdout or ""),
      (r2.stdout or r2.stderr or "").strip()[-80:])

# 已装好时不重复安装（幂等）
try:
    r3 = subprocess.run([venv_py, "-c", probe], **RUN_KW, timeout=PIP_TIMEOUT)
    check("已就绪时跳过安装",
          "BEFORE []" in (r3.stdout or "") and "OK True" in (r3.stdout or ""))
except subprocess.TimeoutExpired:
    check("已就绪时跳过安装", False, "超时（网络问题）")

print()
_timer.cancel()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("自动安装能力验证通过 ✔")
