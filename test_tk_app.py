# -*- coding: utf-8 -*-
"""端到端测试：Tk 版 PyShot（托盘、热键、截图、编辑器、滚动拼接、贴图）。"""
import os
import sys
import time

os.environ.setdefault("PYSHOT_SKIP_DEPS", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tkinter as tk

import winimg as wi

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


def pump(root, ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        try:
            root.update()
        except tk.TclError:
            return
        time.sleep(0.01)


def screen_locked() -> bool:
    u32 = ctypes.windll.user32
    u32.OpenInputDesktop.restype = ctypes.c_void_p
    return not u32.OpenInputDesktop(0, False, 0x0100)


import ctypes

# ---------- 1. 图像核心 ----------
img = wi.grab_region(0, 0, 300, 200)
check("GDI 抓屏（尺寸正确）", img.w == 300 and img.h == 200)
check("抓屏返回 BGRA 缓冲", len(img.data) == 300 * 200 * 4)

# 用合成图做内容相关检查（锁屏时抓屏只能是黑的）
content = wi.Image(300, 200)
r = content.renderer()
r.rect(0, 0, 300, 200, (240, 240, 245), 0, fill=True)
r.rect(10, 10, 100, 60, (230, 57, 53), 3)
r.text(10, 90, "测试文字", (30, 30, 30), size_px=16, bold=True)
r.close()
r = content.renderer()
r.rect(10, 10, 100, 60, (230, 57, 53), 3)
r.text(10, 90, "测试文字", (30, 30, 30), size_px=16, bold=True)
r.close()
check("PNG 编码", content.to_png()[:8] == b"\x89PNG\r\n\x1a\n")
check("PPM 编码", content.to_ppm()[:2] == b"P6")
check("JPEG 保存", content.save_jpeg(os.path.join(HERE, "_t.jpg"), 85))
check("剪贴板", content.copy_to_clipboard())
check("压暗", content.darken_overlay().w == content.w)
check("通道顺序正确（BGRA→RGB）",
      content.rgb_bytes()[:3] == bytes([240, 240, 245]))

# ---------- 2. 采集工具 ----------
import wincapture as wc
st = wc.image_gray_stats(content)
check("灰度统计", st is not None and st[1] > 0)
blank = wi.Image(64, 64)
check("空白检测：黑图判定为空白", wc.image_is_blank(blank))
check("空白检测：有内容不误报", not wc.image_is_blank(content))
check("窗口查询", isinstance(wc.window_at(100, 100), int))
if screen_locked():
    print("NOTE 检测到桌面已锁定：真实抓屏内容相关检查已跳过")

# ---------- 3. 拼接算法 ----------
from stitch import Frame, find_scroll, static_strips
doc = wi.Image(400, 1600)
r = doc.renderer()
for y in range(0, 1600, 40):
    r.rect(0, y, 400, 40, (200 + (y // 40) % 50, 120, 90), 0, fill=True)
    r.text(10, y + 8, f"LINE {y:04d}", (20, 20, 20), size_px=14)
r.close()
f1 = doc.crop(0, 0, 400, 400).to_frame()
f2 = doc.crop(0, 137, 400, 400).to_frame()
s, diff = find_scroll(f1, f2)
check("拼接偏移识别", s == 137, f"s={s}")
check("静止条带", static_strips(f1, f1) == (180, 180))

# 完整滚动流程（模拟滚动）
import winscroller
root = tk.Tk()
root.withdraw()
state = {"pos": 0}


def fake_grab():
    p = state["pos"]
    sub = doc.crop(0, p, 400, 400)
    return sub.to_frame()


class FakeDriver:
    mode = "wheel"
    moved_ever = False
    used_fallback = None

    def prepare(self):
        pass

    def __call__(self, step):
        state["pos"] = min(state["pos"] + 150, 1200)

    def recovery_after_jump(self):
        return False

    def observe(self, s):
        pass

    def describe(self):
        return "模拟"


done = []


def on_done(image, note):
    done.append((image, note))


def on_err(msg):
    done.append(("ERR", msg))


cap = winscroller.ScrollCaptureTk(root, (0, 0, 400, 400), mode="wheel",
                                  on_done=on_done, on_error=on_err,
                                  interval_ms=1, max_frames=12)
cap.driver = FakeDriver()
cap._grab = fake_grab
cap._grab_settled = fake_grab
cap.start()
end = time.time() + 8
while not done and time.time() < end:
    pump(root, 50)
check("滚动截图流程完成", bool(done), str(done[:1])[:80])
if done and not isinstance(done[0], tuple) or (done and done[0][0] != "ERR"):
    res = done[0][0]
    check("拼出长图", hasattr(res, "h") and res.h >= 1500,
          f"{res.w}x{res.h}" if hasattr(res, 'h') else str(res))

# ---------- 4. 编辑器 ----------
import wineditor
base = doc.crop(0, 0, 400, 320)
ed = wineditor.Editor(base)
pump(root, 400)
check("编辑器打开", ed.image.w == 400)
ed.set_tool("rect")
from winshapes import RectShape, StepShape, TextShape
ed.shapes.append(RectShape((230, 57, 53), 3, (20, 20, 150, 60)))
ed.shapes.append(StepShape((230, 57, 53), 2, (200, 60), 1, 30, 20))
ed.shapes.append(TextShape((230, 57, 53), 2, (20, 120), "步骤说明", 18))
ed._render_all()
pump(root, 200)
flat = ed.flatten()
check("导出渲染（图形已合成）",
      flat.w == base.w and flat.data != base.data)
out_png = os.path.join(HERE, "_t_flat.png")
flat.save_png(out_png)
check("导出文件有效", os.path.getsize(out_png) > 1000)
# 撤销
ed._push_undo()
ed.shapes.clear()
ed._render_all()
ed._undo()
check("撤销恢复图形", len(ed.shapes) == 3, str(len(ed.shapes)))

# 标签页（FSCapture 式：多次截图累积在一个编辑器）
ed.add_document(base)
pump(root, 200)
check("新增标签页", len(ed.docs) == 2, f"{len(ed.docs)} 个")
check("新标签是独立文档", len(ed.shapes) == 0)
tab_texts = [w.cget("text") for h in ed.tabbar.winfo_children()
             for w in h.winfo_children() if isinstance(w, tk.Label)]
check("标签栏显示出标签", "截图 1" in tab_texts and "截图 2" in tab_texts,
      str(tab_texts))
ed._switch_document(0)
pump(root, 150)
check("切回标签 1 图形还在", len(ed.shapes) == 3, str(len(ed.shapes)))
ed.close_document(1)
pump(root, 150)
check("关闭标签页", len(ed.docs) == 1)
ed.close()
pump(root, 200)

# ---------- 5. 贴图 ----------
import winmain
pin = winmain.PinWindow(root, base)
pump(root, 200)
check("贴图窗口", pin.win.winfo_exists() == 1)
pin.close()
pump(root, 100)

# ---------- 6. 主程序（托盘 + 热键） ----------
app = winmain.PyShotTk()
pump(root, 600)
check("托盘已创建", app.tray.hwnd != 0)
check("全局热键已注册", app.hk is not None, str(app.hk))
check("主程序启动无异常", True)
app.quit()
pump(root, 200)

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("Tk 版端到端测试全部通过 ✔")
