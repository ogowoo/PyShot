# 版本控制说明

本目录是 git 仓库（分支 `main`）。仓库放源码，外加**单文件版 `PyShot.py`**
（给别人直接运行的那一份，见文末「入库与生成物」）。

## 版本号

- **唯一定义处**：[`version.py`](version.py) 里的 `APP_VERSION`
  （`editor.py` 的「关于」、启动日志、`--check-deps`、单文件版文件头都从它取）。
  以前 `editor.py` 里写死 `APP_VERSION = "2.6"` 而标签已经到 `v2.15` —— 两处各写一份
  必然会飘，所以统一了。有测试（`test_version.py`）盯着"只有一个地方定义"。
- **格式**：`MAJOR.MINOR[.PATCH]`；git 标签为 `v<版本>-qt`。
- **什么时候加位**：
  - `MINOR`：加了用户能感知的功能（例：v2.16 的浮动粘贴）
  - `PATCH`：只修问题（例：v2.14.1 补埋点）
  - `MAJOR`：不兼容的大改（至今没有）
- **改动记录**：写在 [`CHANGELOG.md`](CHANGELOG.md)——按版本倒序，每条注明"为什么改"。
- 发布动作：改 `version.py` → 重新 `python build_single.py` → 提交
  （`chore(release): vX.Y-qt`）→ `git tag vX.Y-qt`。

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
| `v2.17-qt` | 当前主线：三语帮助系统（详见 CHANGELOG.md） |
| `v2.16-qt` | 浮动粘贴拼图 + 编辑增强 + 启动提速 |
| `v2.0-tk` | 零第三方依赖版（tkinter + ctypes），便携版 31MB，代码在 `tk_version/` |
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

## 入库与生成物

- `dist/`（内嵌 Python + tcl/tk，约 31MB）、`.cache/`、`__pycache__/`、测试临时图片
  **不入库**。
- `PyShot.py`（单文件版）**是入库的** —— 它是给别人直接运行的那一份，所以每次发布
  都要 `python build_single.py` 重新生成并一起提交（它带版本号，见「版本号」一节）。
  只为跑测试而生成的中间产物不要提交。

## 尚未做

- 没有配置远程仓库（`git remote`）——需要的话：
  ```powershell
  git remote add origin <仓库地址>
  git push -u origin main --tags
  ```
- 没有 LICENSE 文件。若要开源，建议补一个（MIT 最省事）。
