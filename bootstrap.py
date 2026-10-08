# -*- coding: utf-8 -*-
"""依赖自举：启动时检查并自动安装缺失的第三方库（PySide6 / numpy）。

设计要点
========
- 只用标准库，保证在"什么都还没装"的环境里也能跑起来
- 安装按顺序降级尝试：直接装 → --user → 国内镜像 → 镜像 + --user
- Windows 上先尝试打开长路径支持（PySide6 的深层路径会因此安装失败）
- 全部失败时给出可复制的手动命令，并弹系统对话框提示
- 环境变量 PYSHOT_SKIP_DEPS=1 可跳过检查（测试用）
- PYSHOT_PIP_MIRROR 可自定义镜像源
"""
import os
import subprocess
import sys
from pathlib import Path

from i18n import tr
# 版本号：必须**模块顶层**导入。写成函数内的 `from version import ...` 会被
# 单文件合并删掉，只剩一个空 try 块 → 构建出语法错误（这个坑踩过一次）。
from version import APP_VERSION

# (导入名, pip 安装名)
# 只依赖 PySide6：拼接/图像统计都用纯 Python 实现了，不再需要 numpy。
REQUIRED_PACKAGES = [
    ("PySide6", "PySide6"),
]

# 国内镜像（默认仅在直连失败时使用）
DEFAULT_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def bundled_libs() -> Path | None:
    """程序旁边的内嵌依赖目录（便携版/内嵌版用，存在就不需要 pip）。"""
    here = Path(getattr(sys, "frozen", None) and sys.executable or __file__).resolve()
    libs = here.parent / "libs"
    return libs if libs.is_dir() else None


def _use_bundled_libs() -> bool:
    """有内嵌依赖就优先用它（不联网、不装包）。"""
    libs = bundled_libs()
    if libs is None:
        return False
    p = str(libs)
    if p not in sys.path:
        sys.path.insert(0, p)
    return True


def missing_packages(requirements=None) -> list:
    """返回缺失的 pip 包名列表。"""
    import importlib
    reqs = REQUIRED_PACKAGES if requirements is None else requirements
    missing = []
    for module_name, pip_name in reqs:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(pip_name)
    return missing


def enable_windows_long_paths() -> bool:
    """Windows 未开启长路径支持时，pip 安装 PySide6 会因路径过长失败。"""
    if os.name != "nt":
        return False
    try:
        import winreg
        path = r"SYSTEM\CurrentControlSet\Control\FileSystem"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                             winreg.KEY_READ | winreg.KEY_SET_VALUE)
        try:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
        except FileNotFoundError:
            value = 0
        if value == 1:
            return True
        winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
        print("[PyShot] 已开启 Windows 长路径支持（解决 PySide6 安装失败）")
        return True
    except Exception:
        # 没有管理员权限就算了，安装时若失败会给出提示
        return False


def pip_install(packages, mirror: str | None = None, runner=None,
                extra_args=()) -> bool:
    """按 直装 → --user → 镜像 → 镜像 + --user 的顺序尝试安装。

    runner(cmd) -> int 可注入，便于测试；默认真正执行 pip。
    """
    mirror = mirror if mirror is not None else os.environ.get(
        "PYSHOT_PIP_MIRROR", DEFAULT_MIRROR)
    base = [sys.executable, "-m", "pip", "install", *extra_args]
    attempts = [base + list(packages)]
    if "--user" not in extra_args:
        attempts.append(base + ["--user"] + list(packages))
    if mirror:
        attempts.append(base + ["-i", mirror] + list(packages))
        if "--user" not in extra_args:
            attempts.append(base + ["--user", "-i", mirror] + list(packages))
    run = runner or (lambda cmd: subprocess.call(cmd))
    for cmd in attempts:
        try:
            if run(cmd) == 0:
                return True
        except Exception as ex:  # noqa: BLE001
            print(f"[PyShot] pip 执行失败：{ex}")
    return False


def alert(title: str, message: str):
    """无 GUI 可用时的提示：Windows 弹系统对话框，其他平台打印。

    自动化测试/无人值守场景设 PYSHOT_NO_ALERT=1 就只打印 —— 否则这个模态框
    会把测试挂在那里等人点确定。
    """
    print(f"[PyShot] {title}：{message}")
    if os.name == "nt" and os.environ.get("PYSHOT_NO_ALERT") != "1":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)
        except Exception:
            pass


def ensure_deps(requirements=None, runner=None, quiet: bool = False) -> bool:
    """确保依赖就绪：优先用内嵌依赖；缺什么装什么。返回是否可用。"""
    if os.environ.get("PYSHOT_SKIP_DEPS") == "1":
        return True
    reqs = REQUIRED_PACKAGES if requirements is None else requirements
    # 1) 程序旁边有内嵌依赖目录 → 直接用，不联网不装包
    if _use_bundled_libs():
        if not missing_packages(reqs):
            if not quiet:
                print("[PyShot] 依赖检查：使用程序旁边的内嵌依赖目录，无需安装。")
            return True
    missing = missing_packages(reqs)
    if not missing:
        # 一切正常时也报一句：以前这里完全静默，用户会以为"依赖检查没了"
        if not quiet:
            print(f"[PyShot] 依赖检查：{', '.join(p for _, p in reqs)} 已就绪。")
        return True
    if not quiet:
        print(f"[PyShot] 缺少依赖：{', '.join(missing)}，正在自动安装（首次约需 1-3 分钟）…")
    if os.name == "nt":
        enable_windows_long_paths()
    if not pip_install(missing, runner=runner):
        manual = f"{sys.executable} -m pip install " + " ".join(missing)
        alert("PyShot 依赖安装失败",
              f"请手动执行以下命令后重新运行：\n\n{manual}")
        return False
    # 安装完再验证一次，确保真的能导入
    import importlib
    importlib.invalidate_caches()
    still = missing_packages(reqs)
    if still:
        alert("PyShot 依赖仍不可用", f"以下库导入失败：{', '.join(still)}")
        return False
    if not quiet:
        print("[PyShot] 依赖安装完成。")
    return True


def deps_report() -> str:
    """依赖状态文本，供 --check-deps 使用。"""
    import importlib
    lines = [f"PyShot {APP_VERSION} 依赖检查："]
    bundled = bundled_libs()
    if bundled is not None:
        lines.append(f"  内嵌依赖目录: {bundled}")
    else:
        lines.append("  内嵌依赖目录: 无（将使用系统环境或自动安装）")
    for module_name, pip_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", None)
            if version is None and module_name == "PySide6":
                from PySide6 import __version__ as version  # type: ignore
            where = getattr(mod, "__file__", "")
            lines.append(f"  [OK]   {pip_name} {version or ''}  ({where})".rstrip())
        except Exception as ex:  # noqa: BLE001
            lines.append(f"  [缺失] {pip_name}（{type(ex).__name__}）")
    lines.append(f"  Python: {sys.version.split()[0]}  解释器: {sys.executable}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Windows 控制台窗口
# --------------------------------------------------------------------------
def _get_console_api():
    """取 Windows 控制台相关的 API（单独抽出来便于测试打桩）。"""
    import ctypes
    return ctypes.windll.kernel32, ctypes.windll.user32


def hide_own_console() -> str:
    """双击启动时把自带的黑色控制台窗口藏起来（从终端启动的不动）。

    规则：
      · PYSHOT_CONSOLE=1  保留控制台（排障/看输出时用）
      · 只有控制台是**本进程自己**的（附加进程数不超过 1，即双击/快捷方式启动）
        才藏；从 pwsh/cmd 里运行时控制台是共享的，藏了会把用户的终端一起
        藏起来 —— 不藏。
      · 依赖自举（ensure_deps）在此之前已经跑完，自动安装的进度仍然看得见。

    返回状态串（便于日志与测试）：
      "hidden" / "shared" / "none" / "kept" / "n/a" / "error"
    """
    if os.environ.get("PYSHOT_CONSOLE") == "1":
        return "kept"
    if os.name != "nt":
        return "n/a"
    try:
        k32, u32 = _get_console_api()
        hwnd = k32.GetConsoleWindow()
        if not hwnd:
            return "none"            # pythonw.exe / 已无控制台
        import ctypes
        buf = (ctypes.c_ulong * 16)()
        count = k32.GetConsoleProcessList(buf, 16)
        if count and count <= 1:
            u32.ShowWindow(hwnd, 0)  # SW_HIDE
            return "hidden"
        return "shared"              # 终端里启动的，控制台是共享的
    except Exception:                # noqa: BLE001
        return "error"
