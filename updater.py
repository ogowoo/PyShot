# -*- coding: utf-8 -*-
"""updater.py —— 检查更新 / 应用更新（纯标准库，Qt 无关，便于单独测试）。

机制
====
- 远程版本 = GitHub 仓库（见 ``REPO``）的最新 tag，形如 ``v2.25.1-qt``。
  优先走 GitHub REST API（用户机器**不需要装 git**）；API 不可达时
  回落到 ``git ls-remote --tags``。
- 本机版本 = version.py 里的 APP_VERSION（全项目唯一定义处，别另写一份）。
- 版本比较：把 "2.9.2" / "2.25.1" 拆成数字元组逐段比。
  **不能按字符串比** —— "2.9.2" > "2.25.1"（按字符串）会把旧版当成新版。
- 应用更新：
  - 本目录是 git 检出（旁边有 .git）→ ``git pull --ff-only``；
    ``--ff-only`` 保证只在能干净快进时动手，本地有改动/分叉就拒绝，
    绝不会把用户的改动搅乱。
  - 不是 git 检出（单文件版 / 手动解压的源码）→ 返回 False，
    由调用方打开仓库页面让用户自己下载覆盖。

本模块刻意**不 import Qt、不出现用户可见文案**：所有界面措辞都在
main.py 里用 tr() 写，这里只返回结构化结果。
"""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from version import APP_VERSION

REPO = "ogowoo/pyshot"
REPO_WEB_URL = f"https://github.com/{REPO}"
TAGS_API = f"https://api.github.com/repos/{REPO}/tags?per_page=100"
HTTP_TIMEOUT = 8            # 秒；检查更新不该让用户等太久

# 版本号出处：version.py 注释里说 git 标签为 v<版本>-qt / -tk
_TAG_RE = re.compile(r"^v?(\d+(?:\.\d+){0,2})(?:[-_].*)?$", re.IGNORECASE)


class UpdaterError(Exception):
    """检查/应用更新时的可预期失败（网络不通、解析不出版本等）。"""


def parse_version(text: str):
    """从 "v2.25.1-qt" / "2.9" / "v3.0-tk" 这类串里拆出版本元组。

    合法返回 tuple[int, ...]（如 (2, 25, 1)）；解析不出来返回 None。
    前导的 v、后面 -qt/-tk 之类的后缀都剥掉，只留数字段。
    """
    m = _TAG_RE.match((text or "").strip())
    if not m:
        return None
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except ValueError:                             # 理论到不了这（正则拦过）
        return None


def compare_versions(a, b) -> int:
    """比较两个版本元组/可解析串：a<b → -1，相等 → 0，a>b → +1。

    段数不同按右侧补 0 比（(2, 25) == (2, 25, 0) < (2, 25, 1)）。
    """
    ta = a if isinstance(a, tuple) else parse_version(str(a))
    tb = b if isinstance(b, tuple) else parse_version(str(b))
    if ta is None or tb is None:
        raise UpdaterError(f"无法解析的版本号: {a!r} / {b!r}")
    n = max(len(ta), len(tb))
    ta += (0,) * (n - len(ta))
    tb += (0,) * (n - len(tb))
    return (ta > tb) - (ta < tb)


# ---------------------------------------------------------------- 远程版本查询

def _fetch_tags_via_api(timeout: int = HTTP_TIMEOUT) -> list:
    """GitHub REST API 拿 tag 列表（按字母序返回，不保证版本序，后面自己比）。"""
    req = urllib.request.Request(
        TAGS_API, headers={"User-Agent": "pyshot-updater", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.URLError as exc:
        raise UpdaterError(f"GitHub API 不可达: {exc}") from exc
    if not isinstance(data, list):
        raise UpdaterError("GitHub API 返回异常（不是列表）")
    return [item.get("name", "") for item in data if isinstance(item, dict)]


def _fetch_tags_via_git(timeout: int = HTTP_TIMEOUT) -> list:
    """git ls-remote 兜底（机器上装了 git 才走得到）。"""
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--tags", REPO_WEB_URL],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdaterError(f"git 也不可用: {exc}") from exc
    if out.returncode != 0:
        raise UpdaterError(f"git ls-remote 失败: {out.stderr.strip()[:200]}")
    tags = []
    for line in out.stdout.splitlines():
        # 形如 "<sha>\trefs/tags/v2.25.1-qt^{}"（^{} 是解引用行，跳过）
        ref = line.rsplit("refs/tags/", 1)[-1] if "refs/tags/" in line else ""
        if ref and not ref.endswith("^{}"):
            tags.append(ref)
    return tags


def latest_remote(timeout: int = HTTP_TIMEOUT) -> dict:
    """查线上的最新版本。

    返回 {"version": (2, 25, 1), "tag": "v2.25.1-qt"}。
    一个 tag 都解析不出（比如仓库还没打标签）抛 UpdaterError。
    """
    try:
        tags = _fetch_tags_via_api(timeout)
    except UpdaterError:
        tags = _fetch_tags_via_git(timeout)
    best_tag, best_ver = None, None
    for tag in tags:
        ver = parse_version(tag)
        if ver is None:
            continue                              # 非版本号标签（rc/beta 等）跳过
        if best_ver is None or compare_versions(ver, best_ver) > 0:
            best_tag, best_ver = tag, ver
    if best_ver is None:
        raise UpdaterError("线上没有任何可识别的版本标签")
    return {"version": best_ver, "tag": best_tag}


def check_for_update(timeout: int = HTTP_TIMEOUT) -> dict:
    """一次完整的"要不要更新"判定（后台线程里调）。

    返回 dict（调用方按 error/available 分支做界面）：
      current    本机版本字符串（APP_VERSION）
      latest     线上最新版本字符串（"2.25.1"）
      tag        线上最新 tag（"v2.25.1-qt"）
      url        仓库页面地址
      available  True = 线上比本机新
      error      非空 = 检查失败原因（网络/解析），其余字段无意义
    """
    result = {"current": APP_VERSION, "latest": "", "tag": "", "url": REPO_WEB_URL,
              "available": False, "error": ""}
    try:
        info = latest_remote(timeout)
    except UpdaterError as exc:
        result["error"] = str(exc)
        return result
    result["latest"] = ".".join(str(p) for p in info["version"])
    result["tag"] = info["tag"]
    cur = parse_version(APP_VERSION)
    if cur is None:
        result["error"] = f"本机版本号无法解析: {APP_VERSION}"
        return result
    result["available"] = compare_versions(info["version"], cur) > 0
    return result


# ---------------------------------------------------------------- 应用更新

def app_root() -> Path:
    """程序所在目录（updater.py 在根目录里，取它的父目录）。"""
    return Path(__file__).resolve().parent


def is_git_checkout(root=None) -> bool:
    """本目录是不是 git 检出（能不能直接 git pull）。"""
    root = Path(root) if root else app_root()
    return (root / ".git").exists()


SINGLE_FILE_NAME = "PyShot.py"
# 单文件版的自更新：直接下载仓库 main 分支里生成好的那份（它就在版本库根目录，
# 每次发布都会重新生成提交）。注意仓库已从 ogowoo/pyshot 改名为 ogowoo/PyShot，
# raw 域名对大小写敏感，用改名后的写法。
RAW_SINGLE_URL = (f"https://raw.githubusercontent.com/{REPO}/main/"
                   f"{SINGLE_FILE_NAME}")
MIN_SINGLE_BYTES = 100 * 1024       # 真单文件 ~580KB；太小肯定是错误页/截断
# 只认行首的赋值：version.py 的文档字符串里还引了历史写法 `APP_VERSION = "2.6"`
_VERSION_ASSIGN_RE = re.compile(r'^APP_VERSION = "([^"]+)"', re.MULTILINE)


def is_single_file() -> bool:
    """正在跑的是单文件版吗（__file__ 自己就是 PyShot.py，且旁边没有 .git）。"""
    return Path(__file__).resolve().name == SINGLE_FILE_NAME \
        and not is_git_checkout()


def fetch_single_file(timeout: int = HTTP_TIMEOUT) -> bytes:
    """从仓库 raw 地址下载最新单文件（失败抛 UpdaterError）。"""
    req = urllib.request.Request(
        RAW_SINGLE_URL, headers={"User-Agent": "pyshot-updater"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise UpdaterError(f"下载单文件失败: {exc}") from exc


def single_file_version(data) -> tuple:
    """从单文件内容里取出真正的 APP_VERSION（行首赋值；文档字符串里的旧写法不算）。"""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    m = _VERSION_ASSIGN_RE.search(data or "")
    return parse_version(m.group(1)) if m else None


def write_sidecar(target: Path, data: bytes, version=None) -> Path:
    """把下载到的新版写到 target 旁边，不动现有文件（源码树/无写权限时用）。"""
    dest = target.parent / f"{target.stem}-{version or 'new'}{target.suffix}"
    dest.write_bytes(data)
    return dest


def apply_single_file_update(expected_version: str = "", timeout: int = 120,
                             target=None) -> tuple:
    """单文件版自更新：下载 → 校验 → 原子替换自己。

    返回 (ok, message)：
      ok=True  message 是替换后的文件路径（调用方提示"重启生效"）
      ok=False message 是失败原因

    target 缺省 = 正在运行的 PyShot.py。测试里传临时文件，别碰真身。
    校验三道：长度（防错误页）、能编译（防截断）、APP_VERSION 符合预期
    （防"下到旧版把新版盖了"）。替换用 os.replace：同目录原子操作。
    """
    dest = Path(target).resolve() if target else Path(__file__).resolve()
    try:
        data = fetch_single_file(timeout)
    except UpdaterError as exc:
        return False, str(exc)
    if len(data) < MIN_SINGLE_BYTES:
        return False, f"下载内容太小（{len(data)} 字节），不像单文件版"
    ver = single_file_version(data)
    if ver is None:
        return False, "下载到的文件里找不到 APP_VERSION，拒绝替换"
    if expected_version:
        try:
            if compare_versions(ver, expected_version) < 0:
                return False, (f"下载到的是旧版 {'.'.join(map(str, ver))} "
                               f"（低于线上 {expected_version}），拒绝替换")
        except UpdaterError:
            return False, f"版本号无法比较: {ver!r} vs {expected_version!r}"
    try:
        compile(data.decode("utf-8", "replace"), str(dest), "exec")
    except SyntaxError as exc:
        return False, f"下载的文件编译不过（多半是下载被截断）：{exc}"
    tmp = dest.with_name(dest.name + ".new")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False, f"无法写入 {dest}（没有写权限？）：{exc}"
    return True, str(dest)


def git_pull(root=None, timeout: int = 120) -> tuple:
    """在 root 里 ``git pull --ff-only``。

    返回 (ok, message)：ok=False 时 message 是失败原因（已含 stderr）。
    --ff-only 是本功能的护栏：本地有未提交改动或历史分叉时它**拒绝**
    合并，而不是硬来把用户的改动搅乱。
    """
    root = Path(root) if root else app_root()
    try:
        out = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=str(root),
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git 执行失败: {exc}"
    text = (out.stdout + ("\n" + out.stderr if out.stderr else "")).strip()
    if out.returncode != 0:
        return False, text or f"git pull 退出码 {out.returncode}"
    return True, text


def smoke():
    """手工冒烟：python -c "import updater; updater.smoke()"。

    注意：**不能有** ``if __name__ == "__main__"`` 块 —— 单文件版 build_single
    只剥 main.py 里 ``main()`` 那一个入口，updater 若留 __main__ 块会被合并
    进 PyShot.py 并在**每次启动时真的跑一遍联网检查**。
    """
    print(f"current : {APP_VERSION}")
    r = check_for_update()
    if r["error"]:
        print(f"error   : {r['error']}")
    else:
        print(f"latest  : {r['latest']} ({r['tag']})")
        print(f"update? : {r['available']}")
