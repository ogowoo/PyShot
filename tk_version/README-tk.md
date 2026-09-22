# PyShot —— 截图 + 标注工具（零依赖）

> 版本控制与提交历史见 [VERSIONING.md](VERSIONING.md)

FSCapture 风格的 Windows 截图与标注工具，专为**做操作指引/步骤说明**优化。
**不依赖任何第三方库**：界面用 Python 标准库 `tkinter`，抓屏/绘图/编码/输入模拟
全部用 `ctypes` 直接调 Windows API（GDI / GDI+ / Win32）。

---

## 运行

### 便携版（推荐分发，零安装）

```powershell
python build_portable.py        # 生成 dist/PyShot/
```

产物 `dist/PyShot/`（约 **31 MB**）内嵌了 Python 解释器和 tkinter，
拷到任何 Windows 机器上双击「运行 PyShot.bat」即可 ——
**不需要装 Python、不需要 pip install、不需要联网、没有任何第三方依赖**：

```
dist/PyShot/
├── winmain.py 等模块   程序本体
├── python/             官方嵌入式 Python + _tkinter.pyd + tcl/tk
├── libs/               tkinter 包
├── 运行 PyShot.bat     双击启动（无控制台窗口）
└── 使用说明.txt
```

构建脚本会自动下载官方 `python-3.12.x-embed-amd64.zip`（约 11 MB，之后走缓存），
内嵌 tcl/tk（约 5 MB），最后用内嵌解释器做三项校验：
tkinter 能否加载、PyShot 全链路自检（抓屏→绘制→编码→拼接→编辑器）、依赖检查入口。

### 源码直接运行

```powershell
python winmain.py              # 驻留托盘，按 Ctrl+Alt+X 开始截图
python winmain.py 图片.png     # 直接编辑已有图片
python winmain.py --check-deps # 只检查环境
python test_tk_app.py          # 端到端自测（27 项）
```

只要装了 Python 3.10+（带 tkinter 的标准发行版）就能跑，**无需 pip install 任何东西**。

---

## 功能

### 截图
- **全局热键** `Ctrl+Alt+X`（被占用时自动换 `Ctrl+Shift+X` / `Ctrl+Alt+F9` /
  `Ctrl+Shift+F9`），或**双击托盘图标**
- 全屏冻结遮罩：选区**高亮**显示、尺寸标签、对齐参考线、跟随放大镜（带色值）
- 支持 **Esc / 右键取消**；拖拽时底部有操作提示
- **屏幕取色**：单击即把 `#RRGGBB` 复制到剪贴板

### 标注编辑器（多标签页）
- **标签页**：多次截图累积在同一个编辑器里，可切换、单独关闭、`＋` 再截一张
- 工具：选择/移动 · 矩形 · 椭圆 · 直线 · 箭头 · 画笔 · **序号**（自动递增编号）·
  文字 · 高亮 · 马赛克 · 取色 · 裁剪
- 颜色 9 色调色板 + 自定义取色；线宽 / 字号 / **序号圆大小**可调
- 选中图形可**拖动**、8 点缩放句柄调整；**撤销/重做**（每标签独立）
- 缩放：`−`/`＋`/`100%`/`适应`，Ctrl+滚轮
- 导出：**复制到剪贴板**、保存 **PNG / JPG / BMP**、**贴图**钉在屏幕最上层

### 滚动长截图
四种模式（托盘菜单）：

| 模式 | 适用 |
|---|---|
| 自动滚轮 | 普通网页/文档 |
| **拖拽滚动条** | 远程桌面、Citrix 等不吃滚轮的应用 |
| 按键翻页 | 没有滚动条的应用 |
| 手动滚动 | 特殊场景，你自己滚，软件只负责拼接 |

- **拖拽模式的两种实现**：能读到系统滚动条状态时直接用 `SetScrollInfo`
  程序化滚动（不动鼠标、绝对精准）；读不到才真拖滑块，并**逐步试探校准**步长，
  锚点跟着滑块走，滚太多时自动减半步长重试
- 拼接算法：**行哈希投票**定位移 + **行级精确比较**定胜负，1~2 ms/帧；
  自动识别并裁掉固定不动的边缘（标题栏、底部明细面板），
  检测到"多块独立滚动区域"时给出明确提示
- 抓到的画面是空白/纯色（硬件加速或内容保护窗口）时**明确报错并给建议**，
  并自动尝试 `PrintWindow` 回退

### 其他
- 托盘常驻，启动**不自动截图**；托盘菜单可随时「打开编辑器」
- 截图期间编辑器自动最小化，截完/取消都会恢复

---

## 代码结构

```
pyshot/
├── winmain.py       # 主程序：托盘、全局热键、截图/滚动/取色/贴图流程
├── winimg.py        # ★ 图像核心：GDI 抓屏、DIB 绘制、文字、PNG/BMP/JPEG、剪贴板
├── wintk.py         # ★ Tk 界面框架：主题令牌、矢量图标、托盘图标(Shell_NotifyIcon)
├── winsnipper.py    # 全屏截图覆盖层（选区高亮/放大镜/取色/选点）
├── wineditor.py     # 标注编辑器（多标签页、画布交互、导出）
├── winshapes.py     # 标注图形对象（GDI 导出渲染 + Tk 交互渲染）
├── winscroller.py   # 滚动长截图（四种驱动 + 控制条）
├── wincapture.py    # 抓屏工具（空白检测、PrintWindow 回退、原生滚动条 API）
├── stitch.py        # 纯 Python 滚动拼接算法（零依赖，可离屏单测）
├── build_portable.py# 构建零安装便携版
├── test_tk_app.py  # 端到端测试（27 项）
├── test_mainloop.py # 真实 mainloop + Win32 消息投递（防 ctypes 回调致命崩溃）
├── test_e2e_process.py # 另起子进程从外部投递消息，验证真实运行场景
└── legacy_qt/       # 早期 PySide6 实现（已弃用，仅供查阅）
```

## 实现要点

**为什么不用第三方库**：界面用标准库 `tkinter`；抓屏用 `BitBlt`/`PrintWindow`；
绘图与文字用 GDI（文字是原生 ClearType，中文清晰）；图像编码
PNG 用 `zlib` 手写编码器、JPEG 走 GDI+、BMP 手写；剪贴板用 CF_DIB；
托盘用 `Shell_NotifyIcon`；热键用 `RegisterHotKey`；滚动条用
`GetScrollBarInfo`/`GetScrollInfo`/`SetScrollInfo`。

**性能**：
- `BGRA→RGB` 通道重排用切片交错赋值（C 速度），全屏编解码 **~8 ms**
- 遮罩压暗用 GDI `AlphaBlend`，全屏 **~29 ms**
- 拼接用"行哈希投票"，**1~2 ms/帧**（比早期逐像素差值法快一个数量级）
- Tk 显示用 PPM（免压缩）喂 `PhotoImage`，避免 PNG 编码开销

**踩过的坑**（都已在代码里处理）：
- **ctypes 回调不能放在 Tk 主线程**：Tk 的 `mainloop` 泵消息时会释放 GIL，
  此时 Windows 把消息派发给我们用 ctypes 建的窗口过程，ctypes 恢复线程状态会
  直接触发致命错误 `PyEval_RestoreThread: ... the current Python thread state
  is NULL`，整个进程死掉（Python 层抓不住）。所以托盘图标与全局热键放在
  **独立线程**里跑自己的消息循环（`wintk.Win32Pump`），回调只往队列塞数据，
  Tk 主线程用 `after()` 轮询 —— 跨线程只传数据，绝不碰 Tk 对象
- **`tk.PhotoImage` 必须指定 `master`**：默认绑到"默认解释器"，多 Tk 窗口时
  会报 `image "pyimage1" doesn't exist`
- 模态菜单（`tk_popup`）会开嵌套事件循环，回调里要防止重复弹出
- ctypes 默认按 32 位返回，x64 下会截断 64 位句柄 → 所有返回句柄/指针的函数
  以及带句柄参数的函数都显式声明了 `restype`/`argtypes`
- `COLORREF` 是 `0x00BBGGRR`（低位是红），不是 RGB 顺序
- `AlphaBlend` 在 `Msimg32.dll`，不在 `gdi32.dll`
- `DrawTextW` 在 `user32.dll`，`TextOutW` 在 `gdi32.dll`
- `NOTIFYICONDATAW` 少了 `guidItem`/`hBalloonIcon` 字段会导致结构体过小 → 访问越界崩溃
- Tk 画布需要 `#RRGGBB` 字符串，图形模型里存的是 `(r,g,b)` 元组

**测试为什么分三层**：上面第一条是**进程级致命错误**，单元测试抓不住
（它会连测试进程一起杀掉）。所以除了常规单元/集成测试，还有
`test_mainloop.py`（真实 `mainloop` + 真实 Win32 消息投递）和
`test_e2e_process.py`（另起 `winmain.py` 子进程，从外部投递消息，检查输出里
有没有 `Fatal Python error`）。早期只用 `root.update()` 手动泵消息的测试漏掉了
这个 bug，教训记在这里。

## 环境

- Windows 10/11（用到 DWM 相关的 `PrintWindow` 与每显示器 DPI）
- Python 3.10+（便携版已内嵌，无需自备）
