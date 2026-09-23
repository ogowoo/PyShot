# -*- coding: utf-8 -*-
"""i18n.py —— 三语支持（简体 / 繁體 / English），默认跟随系统。

设计
====
- **键就是简体原文**（gettext 风格）：源码里写 `tr("区域截图")`，好读也好维护
- 词表在 `i18n_data.py`（由 `_gen_i18n.py` 生成）
- 查不到的词条**回落到原文**，所以漏译只是显示原文，不会崩
- 语言选择存在 `~/.pyshot/settings.json`，首次运行按系统语言猜

用法::

    from i18n import tr, set_language, current_language, LANGUAGES
    tr("区域截图")
    tr("已保存：{}", path)          # 占位符用 {}，内部走 str.format
"""
import json
import locale
import os
from pathlib import Path

from i18n_data import TABLE

# 语言代码 → 菜单里显示的名字（这三项本身不翻译）
LANGUAGES = [("zh_CN", "简体中文"), ("zh_TW", "繁體中文"), ("en", "English")]
DEFAULT_LANGUAGE = "zh_CN"
AUTO = "auto"

SETTINGS_PATH = Path.home() / ".pyshot" / "settings.json"
_current = None
_settings_cache = {}


# ---------------------------------------------------------------- 系统语言探测

def system_language() -> str:
    """按系统语言决定用哪套文案：中文分简繁，其它一律英文。"""
    code = ""
    # 先问 Qt（它更懂 Windows 的区域设置）
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name() or ""      # 例：zh_CN / zh_TW / en_US
    except Exception:                              # noqa: BLE001
        code = ""
    if not code:
        try:
            code = locale.getdefaultlocale()[0] or ""
        except Exception:                          # noqa: BLE001
            code = ""
    return language_from_locale(code)


def language_from_locale(code: str) -> str:
    """把 'zh_TW' / 'zh-Hant-HK' / 'en_US' 这类标识归到三语之一。"""
    c = (code or "").replace("-", "_").lower()
    if not c:
        return DEFAULT_LANGUAGE
    if c.startswith("zh"):
        # 繁体区：台湾 / 香港 / 澳门 / 以及带 Hant 的写法
        if any(k in c for k in ("tw", "hk", "mo", "hant", "traditional")):
            return "zh_TW"
        return "zh_CN"
    return "en"


# ---------------------------------------------------------------- 设置读写

def _load_settings() -> dict:
    global _settings_cache
    if _settings_cache:
        return dict(_settings_cache)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _settings_cache = data if isinstance(data, dict) else {}
    except Exception:                              # noqa: BLE001
        _settings_cache = {}
    return dict(_settings_cache)


def _save_settings(data: dict) -> bool:
    global _settings_cache
    _settings_cache = dict(data)
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(_settings_cache, f, ensure_ascii=False, indent=2)
        return True
    except Exception:                              # noqa: BLE001
        return False


def saved_language() -> str:
    """读设置里保存的语言；没保存过返回 AUTO（表示跟随系统）。"""
    code = str(_load_settings().get("language", AUTO) or AUTO)
    if code in (AUTO, "", None):
        return AUTO
    return code if code in dict(LANGUAGES) else AUTO


def current_language() -> str:
    """当前语言：环境变量 PYSHOT_LANG > 保存的设置 > 系统语言。"""
    global _current
    if _current is None:
        env = os.environ.get("PYSHOT_LANG")
        if env and env in dict(LANGUAGES):
            _current = env
        else:
            code = saved_language()
            _current = system_language() if code == AUTO else code
    return _current


def set_language(code: str, persist: bool = True) -> str:
    """切换语言。code 可以是三语之一，也可以是 AUTO（跟随系统）。

    返回真正生效的语言代码。设置 PYSHOT_LANG 时它优先（测试/强制指定用）。
    """
    global _current
    env = os.environ.get("PYSHOT_LANG")
    if env and env in dict(LANGUAGES):
        _current = env
        return _current
    if code == AUTO:
        _current = system_language()
    elif code in dict(LANGUAGES):
        _current = code
    else:
        _current = system_language()
    if persist:
        data = _load_settings()
        data["language"] = code
        _save_settings(data)
    return _current


def reset_cache():
    """测试用：清掉内存里的语言与设置缓存。"""
    global _current, _settings_cache
    _current = None
    _settings_cache = {}


def language_name(code: str) -> str:
    return dict(LANGUAGES).get(code, code)


# ---------------------------------------------------------------- 翻译

def tr(text: str, *args, **kwargs) -> str:
    """翻译一段文案；支持 {} 占位符。

    三种情况都能处理：
    - 传入的是**简体原文**（源码里的写法）→ 直接查表
    - 传入的是**已经翻译过的文本**（切换语言时对现有控件再翻一次）→ 反向查回原文
    - 查不到 → 原样返回（漏译不会崩，只是显示原文）
    """
    return _translate(current_language(), text, *args, **kwargs)


def tr_in(lang: str, text: str, *args, **kwargs) -> str:
    """指定语言翻译（生成对照/测试用）。"""
    return _translate(lang, text, *args, **kwargs)


def _translate(lang: str, text: str, *args, **kwargs) -> str:
    key = text
    if key not in TABLE:
        key = _REVERSE.get(text, text)          # 已翻译过的文本 → 找回原文
    entry = TABLE.get(key)
    out = key
    if entry is not None:
        if lang == "zh_TW":
            out = entry[0] or key
        elif lang == "en":
            out = entry[1] or key
    if args or kwargs:
        try:
            out = out.format(*args, **kwargs)
        except Exception:                          # noqa: BLE001
            pass
    return out


def _build_reverse() -> dict:
    """译文 → 原文 的索引，便于"再翻译一次"（对现有控件做通用刷新）。"""
    rev = {}
    for key, (zh_tw, en) in TABLE.items():
        for value in (zh_tw, en):
            if value and value != key:
                rev.setdefault(value, key)
    return rev


_REVERSE = _build_reverse()


def coverage() -> tuple:
    """返回 (总条数, 繁体条数, 英文条数)——用于自检与测试。"""
    total = len(TABLE)
    zh_tw = sum(1 for v in TABLE.values() if v[0])
    en = sum(1 for v in TABLE.values() if v[1])
    return total, zh_tw, en
