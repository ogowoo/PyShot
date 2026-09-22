# -*- coding: utf-8 -*-
"""这是**早期 PySide6 版本**的完整实现，已归档保留，不再作为主线。

主线（零第三方依赖）在上一级目录：winmain.py + winimg.py + wintk.py ...

旧版仍然可以运行（需要 PySide6）：

    pip install PySide6
    python main.py            # 多文件版
    python PyShot.py          # 单文件版（缺依赖会自动 pip 安装）

相对 Tk 主线，旧版多出的功能：
  - 水印对话框（watermark.py）：文字/图片水印、九宫格/平铺、透明度、可设为默认
  - 贴图板管理（pinboard.py）
  - QScreen 的抓屏路径（主线改用了更底层的 GDI BitBlt + PrintWindow）

测试：smoke_test.py / test_multiscreen.py / test_watermark.py /
      test_scrollbar_drag.py / test_capture_fallback.py / test_notifications.py /
      test_hotkey.py / test_single_file.py / test_no_numpy.py /
      test_scroll_isolation.py / test_ui.py   —— 全部通过。
"""
