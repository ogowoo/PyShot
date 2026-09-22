# -*- coding: utf-8 -*-
"""验证单文件版 PyShot.py：导入、核心功能、依赖自举逻辑。"""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PYSHOT_SKIP_DEPS"] = "1"          # 测试时不真的去装依赖
HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "PyShot.py")

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


# --- 以模块方式加载单文件 ---
spec = importlib.util.spec_from_file_location("PyShot_single", TARGET)
mod = importlib.util.module_from_spec(spec)
sys.modules["PyShot_single"] = mod
spec.loader.exec_module(mod)
check("单文件可导入", mod is not None)

# --- 依赖自举逻辑（用假 runner 验证降级尝试链） ---
calls = []
ok = mod.pip_install(["FakePkg"], runner=lambda cmd: (calls.append(cmd), 1)[1])
check("安装失败会依次尝试多种方式", not ok and len(calls) == 4)
check("第一次是直接安装", calls[0][-1] == "FakePkg" and "--user" not in calls[0])
check("包含 --user 降级", any("--user" in c for c in calls))
check("包含镜像源降级", any("-i" in c for c in calls))
calls.clear()
ok2 = mod.pip_install(["FakePkg"], runner=lambda cmd: (calls.append(cmd), 0)[1])
check("安装成功即返回", ok2 and len(calls) == 1)
check("缺失检测正常", mod.missing_packages([("PySide6", "PySide6")]) == [])
check("缺失检测能发现不存在的库",
      mod.missing_packages([("no_such_module_xyz", "no_such_module_xyz")])
      == ["no_such_module_xyz"])
check("依赖报告可读", "PySide6" in mod.deps_report()
      and "内嵌依赖目录" in mod.deps_report())
check("只依赖 PySide6（numpy 已剥离）",
      [p for _, p in mod.REQUIRED_PACKAGES] == ["PySide6"])
check("跳过自举开关有效", mod.ensure_deps() is True)

# --- 核心功能：画布 / 序号 / 撤销 ---
app = mod.QApplication([])
pix = mod.QPixmap(400, 300)
pix.fill(mod.QColor("#ddeeff"))
canvas = mod.Canvas(pix)
canvas.step_diameter = 80
canvas.shapes.append(mod.StepShape(mod.QColor("red"), 2,
                                   mod.QPointF(50, 50), 1, 20, 80))
check("单文件序号尺寸可调", abs(canvas.shapes[0].diameter - 80) < 0.1)
out = canvas.render_result()
check("单文件可渲染输出", out.width() == 400 and out.height() == 300)

# --- 核心功能：滚动拼接算法 ---
import numpy as np
rng = np.random.default_rng(7)
doc = rng.integers(0, 255, (900, 300, 3), dtype=np.uint8)
s, _ = mod.find_scroll(doc[0:300], doc[111:411])
check("单文件滚动拼接算法正确", s == 111)

# --- 核心功能：编辑器标签页 ---
win = mod.EditorWindow(mod.QPixmap(200, 150))
win.add_canvas(mod.QPixmap(300, 200))
check("单文件编辑器标签可用", win.tabs.count() == 2 and win.canvas is not None)

# --- 单文件不应残留本地 import ---
src = open(TARGET, encoding="utf-8").read()
check("无残留本地 import",
      not any(l.strip().startswith(("from shapes", "from style", "from snipper",
                                    "from editor", "from scroller",
                                    "from bootstrap", "from pinboard",
                                    "from capture_utils", "from watermark"))
              for l in src.splitlines()))
check("内嵌了抓屏回退工具", "def grab_region_printwindow" in src
      and "def looks_like_missing_content" in src)
check("内嵌了水印功能", "def draw_watermark" in src and "class WatermarkDialog" in src)
check("内嵌了依赖自举", "def ensure_deps" in src and "REQUIRED_PACKAGES" in src)
check("入口支持 --check-deps", "--check-deps" in src)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("单文件版全部通过 ✔")
