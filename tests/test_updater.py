# -*- coding: utf-8 -*-
"""updater.py 单测：版本解析/比较、最新 tag 选取、检查结论、git 检出判定。

全部离线跑（不碰 GitHub）：网络层用 monkeypatch 掉，只验证本机逻辑。
想真查一次线上可以单独跑：python updater.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PYSHOT_LANG", "zh_CN")
HERE = Path(__file__).resolve().parent.parent   # 项目根（本文件在 tests/ 里）
sys.path.insert(0, str(HERE))

import updater
from updater import (UpdaterError, check_for_update, compare_versions,
                     is_git_checkout, latest_remote, parse_version)

failures = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        failures.append(name)


# ---------- 1) 版本号解析 ----------
check("'v2.25.1-qt' → (2, 25, 1)", parse_version("v2.25.1-qt") == (2, 25, 1))
check("'2.9' → (2, 9)", parse_version("2.9") == (2, 9))
check("'v2.25-qt' → (2, 25)", parse_version("v2.25-qt") == (2, 25))
check("'v3.0-tk' → (3, 0)", parse_version("v3.0-tk") == (3, 0))
check("'V2.4-QT' 大小写不敏感", parse_version("V2.4-QT") == (2, 4))
check("垃圾串 → None", parse_version("latest") is None)
check("空串 → None", parse_version("") is None)
check("'v2.25.1-beta' 非 qt/tk 后缀也认", parse_version("v2.25.1-beta") == (2, 25, 1))
check("'v2' 单段也算", parse_version("v2") == (2,))

# ---------- 2) 版本比较（字符串比会把 2.9.2 当成比 2.25.1 新 —— 就是当年踩的坑）----------
check("2.9.2 < 2.25.1（不能按字符串比）",
      compare_versions("2.9.2", "2.25.1") == -1)
check("2.25.1 > 2.25", compare_versions("2.25.1", "2.25") == 1)
check("2.25 == 2.25.0（段数不同补 0）", compare_versions("2.25", "2.25.0") == 0)
check("相等", compare_versions((2, 25, 1), "v2.25.1-qt") == 0)
try:
    compare_versions("junk", "2.0")
    check("非法版本抛 UpdaterError", False)
except UpdaterError:
    check("非法版本抛 UpdaterError", True)

# ---------- 3) latest_remote：从一堆 tag 里挑最大的 ----------
real_api, real_git = updater._fetch_tags_via_api, updater._fetch_tags_via_git

updater._fetch_tags_via_api = lambda timeout=8: [
    "v2.8.4-qt", "v2.25.1-qt", "v2.9.2-qt", "v2.25-qt", "latest", "beta-1"]
info = latest_remote()
check("latest_remote 挑出 v2.25.1-qt", info["tag"] == "v2.25.1-qt"
      and info["version"] == (2, 25, 1), str(info))

# API 挂了回落到 git
def _boom_api(timeout=8):
    raise UpdaterError("GitHub API 不可达: boom")
updater._fetch_tags_via_api = _boom_api
updater._fetch_tags_via_git = lambda timeout=8: ["v1.0-qt", "v1.1-qt"]
info = latest_remote()
check("API 失败回落 git ls-remote", info["tag"] == "v1.1-qt", str(info))

# 两个渠道都没有可识别标签 → UpdaterError
updater._fetch_tags_via_git = lambda timeout=8: ["latest", "snapshot"]
try:
    latest_remote()
    check("无可识别标签时抛 UpdaterError", False)
except UpdaterError:
    check("无可识别标签时抛 UpdaterError", True)

updater._fetch_tags_via_api, updater._fetch_tags_via_git = real_api, real_git

# ---------- 4) check_for_update 的结论 ----------
real_latest = updater.latest_remote

updater.latest_remote = lambda timeout=8: {"version": (9, 9, 9), "tag": "v9.9.9-qt"}
r = check_for_update()
check("线上更新 → available=True", r["available"] and r["latest"] == "9.9.9"
      and r["current"] == updater.APP_VERSION, str(r))

updater.latest_remote = lambda timeout=8: {"version": (0, 0, 1), "tag": "v0.0.1-qt"}
r = check_for_update()
check("线上更旧 → available=False", not r["available"] and not r["error"], str(r))

def _boom_latest(timeout=8):
    raise UpdaterError("GitHub API 不可达: no network")
updater.latest_remote = _boom_latest
r = check_for_update()
check("网络失败 → error 非空且 available=False",
      bool(r["error"]) and not r["available"], str(r))

updater.latest_remote = real_latest

# ---------- 5) git 检出判定 + git_pull 的失败路径（临时目录，离线）----------
tmp = Path(tempfile.mkdtemp(prefix="pyshot_upd_"))
check("普通目录不是 git 检出", not is_git_checkout(tmp))
(tmp / ".git").mkdir()
check("有 .git 才算 git 检出", is_git_checkout(tmp))

ok, msg = updater.git_pull(tmp, timeout=30)
check("非仓库目录 git pull 失败且带原因", not ok and bool(msg), msg[:60])

# ---------- 6) 单文件版自更新：下载 → 校验 → 原子替换 ----------
# 真单文件 ~580KB，这里造 >100KB 的合法内容（编译要通过）
_PAD = "# padding\n" * 12000                     # ~108KB


def make_single(version: str) -> bytes:
    return (f'# -*- coding: utf-8 -*-\n'
            f'"""PyShot {version} 单文件版"""\n'
            f'APP_VERSION = "{version}"\n{_PAD}').encode("utf-8")


# 文档字符串里引了历史写法 APP_VERSION = "2.6"，行首锚定不能取错
mixed = ('"""以前写死 `APP_VERSION = "2.6"`"""\n'
         'APP_VERSION = "2.27"\n').encode("utf-8")
check("版本解析跳过文档字符串里的旧写法",
      updater.single_file_version(mixed) == (2, 27),
      str(updater.single_file_version(mixed)))

work = Path(tempfile.mkdtemp(prefix="pyshot_selfupd_"))
target = work / "PyShot.py"
target.write_text('APP_VERSION = "2.26.1"\nprint("old")\n', encoding="utf-8")

real_fetch = updater.fetch_single_file


def _fetch_ok(timeout=120):
    return make_single("2.27")


updater.fetch_single_file = _fetch_ok
ok, msg = updater.apply_single_file_update("2.27", target=target)
check("自更新成功并替换目标文件", ok and Path(msg) == target.resolve(), str(msg))
check("替换后的文件是新版内容",
      'APP_VERSION = "2.27"' in target.read_text(encoding="utf-8"))
check("临时文件已清理（没有 .new 残留）", not (work / "PyShot.py.new").exists())

# 下载比预期旧 → 拒绝（防止"下到旧版把新版盖了"）
ok, msg = updater.apply_single_file_update("2.28", target=target)
check("下载版本低于预期 → 拒绝替换", not ok and "旧版" in msg, msg[:50])
check("拒绝时原文件没被动过",
      'APP_VERSION = "2.27"' in target.read_text(encoding="utf-8"))

# 太小（错误页）
updater.fetch_single_file = lambda timeout=120: b"404 not found"
ok, msg = updater.apply_single_file_update("2.27", target=target)
check("内容太小 → 拒绝", not ok and "太小" in msg, msg[:50])

# 没有 APP_VERSION
updater.fetch_single_file = lambda timeout=120: b"# nothing\n" + b"#" * 200000
ok, msg = updater.apply_single_file_update("2.27", target=target)
check("缺 APP_VERSION → 拒绝", not ok and "APP_VERSION" in msg, msg[:50])

# 截断（编译不过）
updater.fetch_single_file = lambda timeout=120: (
    b'APP_VERSION = "2.27"\ndef broken(:\n' + b"#" * 200000)
ok, msg = updater.apply_single_file_update("2.27", target=target)
check("编译不过（截断）→ 拒绝", not ok, msg[:50])

# 网络失败
def _boom_fetch(timeout=120):
    raise UpdaterError("下载单文件失败: no network")
updater.fetch_single_file = _boom_fetch
ok, msg = updater.apply_single_file_update("2.27", target=target)
check("下载失败 → 返回失败原因", not ok and "no network" in msg, msg[:50])

# 没写权限（指向不存在目录）→ 明确报错而不是抛到界面
updater.fetch_single_file = _fetch_ok
ok, msg = updater.apply_single_file_update(
    "2.27", target=work / "no_such_dir" / "PyShot.py")
check("目标不可写 → 返回失败原因", not ok and bool(msg), msg[:70])

updater.fetch_single_file = real_fetch

# 源码树（非 git）旁置下载：写 PyShot-<版本>.py，不动原文件
side = updater.write_sidecar(work / "PyShot.py", make_single("2.27"), "2.27")
check("旁置文件命名为 PyShot-<版本>.py", side.name == "PyShot-2.27.py", side.name)
check("旁置文件内容正确", 'APP_VERSION = "2.27"' in side.read_text(encoding="utf-8"))

print()
if failures:
    print("失败项:", failures)
    sys.exit(1)
print("updater 检查全部通过 ✔")
