# -*- coding: utf-8 -*-
"""版本号**只在这里定义**（其他地方一律 import，别再各写一份）。

以前 `editor.py` 里写死 `APP_VERSION = "2.6"`，而 git 里程碑标签已经到
`v2.15-qt` —— 两处各写一份，就必然会飘。现在统一从这里取，
`build_single.py` 生成单文件时也读它写进文件头。

命名：`MAJOR.MINOR[.PATCH]`，git 标签为 `v<版本>-qt`（`-qt` 表示根目录这套
PySide6 实现，`tk_version/` 是独立的 Tkinter 版）。
"""
APP_VERSION = "2.18.1"

# 这版的一句话主题（写进单文件头与「关于」对话框，便于用户确认自己拿的是哪版）
VERSION_TITLE = "标注作者信息"

# 版本日期（本地日期，供日志/文档使用）
VERSION_DATE = "2026-09-24"

# 作者（唯一来源：关于对话框、README、单文件头、帮助里都从这里取，
# 别再各处各写一份邮箱 —— 改一次就全对上）
AUTHOR = "Walt Liang"
AUTHOR_EMAIL = "Wat.L@outlook.com"

__version__ = APP_VERSION      # 兼容 `mod.__version__` 这种取法
