# 版本控制说明

本目录是 git 仓库（分支 `main`），仓库只放**源码**，构建产物不入库。

## 提交历史

```
25373ed style: 统一换行为 LF
da1e792 chore(legacy): 归档早期 PySide6 实现
1d65dbf test+build: 端到端测试与零安装便携版构建
086a84d feat(main): 主程序（托盘、全局热键、截图流程）
37d2fcf feat(scroll): 滚动长截图（四种驱动模式）
94c2609 feat(editor): 多标签页标注编辑器
f3aaec7 feat(snipper): 全屏截图覆盖层
5b815f4 feat(ui): Tk 界面框架与标注图形模型
2e65fba feat(winimg): ctypes 图像核心与抓屏工具
4d0fe3c feat(stitch): 纯 Python 滚动拼接核心（零依赖）
83f17bb chore: 初始化仓库，加入 .gitignore / .gitattributes
```

## 里程碑标签

| 标签 | 内容 |
|---|---|
| `v2.0-tk` | 当前主线：零第三方依赖（tkinter + ctypes），便携版 31MB |
| `v1.0-qt` | 早期 PySide6 版（代码在 `legacy_qt/`，含水印对话框、贴图板） |

取回旧版代码：

```powershell
git worktree add ../pyshot-tk v2.0.3-tk    # 检出 Tkinter 版（另开目录，避免互相影响）
# 或直接在仓库里看：tk_version/
`

主线（根目录）是 PySide6 版；	k_version/ 是零依赖 Tkinter 版，两者独立、
互不干扰（模块名不冲突：主线的 main.py/editor.py vs Tk 版的 winmain.py/wineditor.py）。``

## 仓库约定

- **不入库**：`dist/`（内嵌 Python + tcl/tk，约 31MB，用 `python build_portable.py` 重建）、
  `.cache/`（下载的嵌入式 Python 压缩包）、`__pycache__/`、测试临时图片
- **换行**：`.gitattributes` 声明 `eol=lf`；`*.bat` 保持 CRLF
- **身份**：本仓库使用本地身份 `PyShot <pyshot@localhost>`（未改全局配置）。
  需要换成你自己的：
  ```powershell
  git config user.name  "你的名字"
  git config user.email "你的邮箱"
  ```

## 常用操作

```powershell
git status                 # 看改动
git log --oneline --graph  # 看历史
git diff                   # 看未暂存改动
git add -A; git commit -m "..."   # 提交
```

## 提交信息风格

`<type>(<scope>): <摘要>`，类型用 `feat` / `fix` / `refactor` / `test` / `chore` / `style` / `docs`。
正文写清**为什么**改，而不只是改了什么（例如上面几条提交里记了性能数字与踩过的坑）。

## 尚未做

- 没有配置远程仓库（`git remote`）——需要的话：
  ```powershell
  git remote add origin <仓库地址>
  git push -u origin main --tags
  ```
- 没有 LICENSE 文件。若要开源，建议补一个（MIT 最省事）。
