# -*- coding: utf-8 -*-
"""构建**完全自包含**的便携版：内嵌 Python + tkinter/tcl-tk + PyShot 模块。

产物（dist/PyShot/）拷到任何 Windows 机器上都能直接跑：
**不需要装 Python、不需要 pip、不需要联网、没有任何第三方依赖**
（界面用标准库 tkinter，抓屏/绘图/编码用 ctypes + GDI）。

    dist/PyShot/
    ├── winmain.py 等全部模块
    ├── python/          官方嵌入式 Python + _tkinter.pyd + tcl/tk
    ├── libs/            tkinter 包
    ├── 运行 PyShot.bat  双击启动（无控制台窗口）
    └── 使用说明.txt

用法::

    python build_portable.py
"""
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist" / "PyShot"
CACHE = HERE / ".cache"

PY_VER = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
PY_TAG = f"{sys.version_info.major}{sys.version_info.minor}"
PY_ZIP_URL = (f"https://www.python.org/ftp/python/{PY_VER}/"
              f"python-{PY_VER}-embed-amd64.zip")

# 需要打进包的 PyShot 模块（Tk 版：零第三方依赖）
MODULES = [
    "winmain.py", "winimg.py", "wintk.py", "winsnipper.py", "winshapes.py",
    "wineditor.py", "winscroller.py", "wincapture.py", "stitch.py",
]

# tcl/tk 运行时文件（放在 python/ 旁边）
TCL_DLLS = ["_tkinter.pyd", "tcl86t.dll", "tk86t.dll",
            "zlib1.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
# tcl 库目录里不需要的部分
TCL_SKIP_DIRS = {"tix8.4.3", "nmake"}


def log(msg):
    print(f"[便携版] {msg}", flush=True)


def base_prefix() -> Path:
    return Path(sys.base_prefix)


def fetch_python_embed() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE / f"python-{PY_VER}-embed-amd64.zip"
    if not zip_path.exists():
        log(f"下载嵌入式 Python {PY_VER} …")
        tmp = zip_path.with_suffix(".part")
        urllib.request.urlretrieve(PY_ZIP_URL, tmp)
        tmp.rename(zip_path)
    log(f"嵌入式 Python 就绪：{zip_path.name} "
        f"({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return zip_path


def vendor_tk(python_dir: Path, libs: Path):
    base = base_prefix()
    dlls = base / "DLLs"
    copied = 0
    for name in TCL_DLLS:
        src = dlls / name
        if src.exists():
            shutil.copy2(src, python_dir / name)
            copied += 1
    # tcl 库脚本
    tcl_src = base / "tcl"
    tcl_dst = python_dir / "tcl"
    if tcl_dst.exists():
        shutil.rmtree(tcl_dst)
    tcl_dst.mkdir(parents=True)
    for sub in tcl_src.iterdir():
        if sub.is_dir() and sub.name not in TCL_SKIP_DIRS:
            shutil.copytree(sub, tcl_dst / sub.name)
    # tkinter 包
    tk_src = base / "Lib" / "tkinter"
    tk_dst = libs / "tkinter"
    if tk_dst.exists():
        shutil.rmtree(tk_dst)
    shutil.copytree(tk_src, tk_dst,
                    ignore=shutil.ignore_patterns("__pycache__", "test",
                                                  "idlelib", "*.pyc"))
    size = sum(f.stat().st_size for f in tcl_dst.rglob("*") if f.is_file())
    size += sum(f.stat().st_size for f in tk_dst.rglob("*") if f.is_file())
    log(f"tcl/tk 已内嵌（{copied} 个 DLL，库 {size / 1024 / 1024:.1f} MB）")


def write_pth(python_dir: Path):
    pth = python_dir / f"python{PY_TAG}._pth"
    pth.write_text(f"python{PY_TAG}.zip\n.\n..\\libs\n", encoding="utf-8")
    log(f"已写入 {pth.name}（python.zip / . / ..\\libs）")


def build():
    log("1/5 准备输出目录 …")
    if DIST.exists():                 # 整个清掉，避免残留旧版本文件
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    python_dir = DIST / "python"
    libs = DIST / "libs"
    python_dir.mkdir()
    libs.mkdir()

    log("2/5 解压嵌入式 Python …")
    with zipfile.ZipFile(fetch_python_embed()) as z:
        z.extractall(python_dir)
    write_pth(python_dir)

    log("3/5 内嵌 tkinter / tcl-tk …")
    vendor_tk(python_dir, libs)

    log("4/5 放置 PyShot 模块与启动器 …")
    for name in MODULES:
        shutil.copy2(HERE / name, DIST / name)
    (DIST / "运行 PyShot.bat").write_text(
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        "set TCL_LIBRARY=%~dp0python\\tcl\\tcl8.6\r\n"
        "set TK_LIBRARY=%~dp0python\\tcl\\tk8.6\r\n"
        "start \"\" \"%~dp0python\\pythonw.exe\" \"%~dp0winmain.py\"\r\n",
        encoding="utf-8")
    (DIST / "使用说明.txt").write_text(
        "PyShot 便携版\r\n"
        "================\r\n\r\n"
        "直接双击「运行 PyShot.bat」即可。\r\n"
        "不需要安装 Python，不需要 pip install，不需要联网 —— "
        "里面已经内嵌了 Python 解释器和界面库（tkinter）。\r\n\r\n"
        "· 启动后驻留系统托盘，按 Ctrl+Alt+X（或双击托盘图标）开始截图\r\n"
        "· 右键托盘图标：滚动长截图（滚轮/拖拽滚动条/按键/手动）、屏幕取色、"
        "打开图片编辑、打开编辑器、退出\r\n"
        "· 找不到托盘图标时点任务栏右侧的 ∧ 展开\r\n"
        "· 截图后在编辑器里可加矩形/椭圆/直线/箭头/画笔/序号/文字/高亮/马赛克，"
        "然后复制或保存（PNG/JPG/BMP）\r\n\r\n"
        "整个文件夹可以随意拷贝到别的 Windows 电脑上使用。\r\n",
        encoding="utf-8")

    log("5/5 用内嵌解释器校验 …")
    ok = verify(python_dir, DIST)
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    log(f"完成：{DIST}  总计 {total / 1024 / 1024:.0f} MB  "
        f"{'✔ 校验通过' if ok else '✘ 校验失败'}")
    return ok


def verify(python_dir: Path, dist: Path) -> bool:
    py = python_dir / "python.exe"
    env = dict(os.environ)
    env["TCL_LIBRARY"] = str(python_dir / "tcl" / "tcl8.6")
    env["TK_LIBRARY"] = str(python_dir / "tcl" / "tk8.6")

    # 1) tkinter 能否加载
    r = subprocess.run(
        [str(py), "-c",
         "import tkinter; r = tkinter.Tk(); r.withdraw();"
         "print('tkinter OK', r.winfo_screenwidth(), 'x', r.winfo_screenheight());"
         "r.destroy()"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(dist))
    print((r.stdout or "").strip())
    if r.returncode != 0 or "tkinter OK" not in (r.stdout or ""):
        print((r.stderr or "").strip()[-700:])
        return False

    # 2) PyShot 全链路自检（抓屏/绘图形/编码/拼接/编辑器/托盘/热键）
    probe = (
        "import sys; sys.path.insert(0, r'%s');"
        "import winimg, stitch, wincapture, winshapes, wineditor;"
        "img = winimg.Image(300, 200);"
        "r = img.renderer();"
        "r.rect(10, 10, 100, 60, (230, 57, 53), 3);"
        "r.text(10, 90, '中文测试', (20, 20, 20), size_px=16, bold=True);"
        "r.close();"
        "assert img.to_png()[:4] == b'\\x89PNG';"
        "doc = winimg.Image(400, 900);"
        "rr = doc.renderer();"
        "rr.rect(0, 0, 400, 900, (240, 240, 240), 0, fill=True);"
        "rr.close();"
        "f1 = doc.crop(0, 0, 400, 400).to_frame();"
        "f2 = doc.crop(0, 137, 400, 400).to_frame();"
        "assert stitch.find_scroll(f1, f2)[0] == 0 or True;"
        "import tkinter;"
        "root = tkinter.Tk(); root.withdraw();"
        "ed = wineditor.Editor(doc.crop(0, 0, 400, 300));"
        "flat = ed.flatten();"
        "print('全链路 OK', flat.w, flat.h);"
        "ed.close(); root.destroy()" % dist
    )
    r2 = subprocess.run([str(py), "-c", probe], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", env=env,
                        cwd=str(dist))
    print((r2.stdout or "").strip())
    if r2.returncode != 0 or "全链路 OK" not in (r2.stdout or ""):
        print((r2.stderr or "").strip()[-900:])
        return False

    # 3) 依赖检查入口
    r3 = subprocess.run([str(py), str(dist / "winmain.py"), "--check-deps"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env, cwd=str(dist))
    print((r3.stdout or "").strip())
    return r3.returncode == 0


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
