# -*- coding: utf-8 -*-
"""session.py —— 记住上次的截图（重启后还在，但**不需要你手动保存**）。

设计
====
- 关软件/崩溃前，把编辑器里的标签页（底图 + 标注 + 缩放 + 标题）悄悄写到
  `~/.pyshot/session/`；下次启动自动恢复，不弹"要不要保存"。
- 它**不是**用户文件：不占用户目录、不生成"另存为"对话框；被恢复的标签仍然是
  未保存状态，用户想留就自己 Ctrl+S。
- 只保留**最后一次**会话（每次写入先清空，避免越积越多）；限制标签数与总大小。

存储结构::

    ~/.pyshot/session/session.json     # 会话描述（含每个标签的图形）
    ~/.pyshot/session/tab0.png         # 每个标签的底图（无损）

为什么连图形一起存：只存拼好的图会把标注"焊死"，恢复后就没法再改了。
"""
import json
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QPixmap

# 缓存目录；跑测试时用 PYSHOT_SESSION_DIR 指到临时目录，绝不碰用户真实数据
SESSION_DIR = Path(os.environ.get("PYSHOT_SESSION_DIR") or
                   (Path.home() / ".pyshot" / "session"))
SESSION_SETTINGS_PATH = Path.home() / ".pyshot" / "settings.json"
MAX_TABS = 12                       # 最多恢复这么多标签
MAX_BYTES = 120 * 1024 * 1024       # 底图总量上限（约 120MB）


# ---------------------------------------------------------------- 设置开关

def _load_session_settings() -> dict:
    try:
        with open(SESSION_SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:                              # noqa: BLE001
        return {}


def _save_session_settings(data: dict) -> bool:
    try:
        SESSION_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:                              # noqa: BLE001
        return False


def session_enabled() -> bool:
    """是否在启动时恢复上次的截图（默认开）。"""
    return bool(_load_session_settings().get("restore_session", True))


def set_session_enabled(on: bool) -> bool:
    data = _load_session_settings()
    data["restore_session"] = bool(on)
    return _save_session_settings(data)


# ---------------------------------------------------------------- 图形序列化

def shape_to_dict(shape) -> dict:
    """把标注图形转成 JSON 可存的结构（按类名分派）。"""
    from shapes import (ArrowShape, EllipseShape, HighlightShape, LineShape,
                        MosaicShape, PenShape, RectShape, StepShape, TextShape,
                        WatermarkShape)

    def pt(p):
        return [round(float(p.x()), 2), round(float(p.y()), 2)]

    base = {"t": type(shape).__name__, "color": shape.color.name(),
            "w": int(shape.width)}
    # 旋转角（新字段；旧缓存里没有就当作 0，不影响读旧数据）
    if getattr(shape, "rotation", 0.0):
        base["rot"] = round(float(shape.rotation), 2)
    if isinstance(shape, WatermarkShape):
        base.pop("color", None)
        base.pop("w", None)
        base["settings"] = dict(shape.settings)
        base["size"] = [shape.image_size.width(), shape.image_size.height()]
        if shape.offset is not None:
            base["offset"] = pt(shape.offset)
        return base
    if isinstance(shape, (EllipseShape, RectShape)):
        base["rect"] = [shape.rect.x(), shape.rect.y(),
                        shape.rect.width(), shape.rect.height()]
        base["ellipse"] = isinstance(shape, EllipseShape)
        base["fill"] = bool(getattr(shape, "fill", False))
        return base
    if isinstance(shape, HighlightShape):
        base["rect"] = [shape.rect.x(), shape.rect.y(),
                        shape.rect.width(), shape.rect.height()]
        return base
    if isinstance(shape, MosaicShape):
        base["rect"] = [shape.rect.x(), shape.rect.y(),
                        shape.rect.width(), shape.rect.height()]
        return base
    if isinstance(shape, ArrowShape):
        base["p1"], base["p2"] = pt(shape.p1), pt(shape.p2)
        return base
    if isinstance(shape, LineShape):
        base["p1"], base["p2"] = pt(shape.p1), pt(shape.p2)
        return base
    if isinstance(shape, PenShape):
        base["points"] = [pt(p) for p in shape.points]
        return base
    if isinstance(shape, TextShape):
        base["pos"] = pt(shape.pos)
        base["text"] = shape.text
        base["font_size"] = int(shape.font_size)
        return base
    if isinstance(shape, StepShape):
        base["center"] = pt(shape.center)
        base["number"] = int(shape.number)
        base["diameter"] = float(shape.diameter)
        return base
    return {}                                      # 认不出来就不存（跳过）


def shape_from_dict(d: dict):
    """反序列化：认不出来返回 None。"""
    from shapes import (ArrowShape, EllipseShape, HighlightShape, LineShape,
                        MosaicShape, PenShape, RectShape, StepShape, TextShape,
                        WatermarkShape)
    t = d.get("t")
    color = QColor(d.get("color", "#e53935"))
    w = int(d.get("w", 3))

    def pt(seq):
        return QPointF(float(seq[0]), float(seq[1]))

    try:
        if t == "WatermarkShape":
            size = d.get("size") or [640, 400]
            off = pt(d["offset"]) if d.get("offset") else None
            return WatermarkShape(d.get("settings", {}), QSize(int(size[0]),
                                                              int(size[1])),
                                  off)
        if t == "EllipseShape":
            r = d["rect"]
            return _with_rotation(EllipseShape(color, w,
                                               QRectF(*[float(v) for v in r]),
                                               bool(d.get("fill", False))), d)
        if t == "RectShape":
            r = d["rect"]
            return _with_rotation(RectShape(color, w,
                                            QRectF(*[float(v) for v in r]),
                                            bool(d.get("fill", False))), d)
        if t == "HighlightShape":
            return _with_rotation(HighlightShape(color, w,
                                                 QRectF(*[float(v) for v in d["rect"]])), d)
        if t == "MosaicShape":
            return _with_rotation(MosaicShape(color, w,
                                              QRectF(*[float(v) for v in d["rect"]])), d)
        if t == "ArrowShape":
            return _with_rotation(ArrowShape(color, w, pt(d["p1"]), pt(d["p2"])), d)
        if t == "LineShape":
            return _with_rotation(LineShape(color, w, pt(d["p1"]), pt(d["p2"])), d)
        if t == "PenShape":
            return _with_rotation(PenShape(color, w,
                                           [pt(p) for p in d.get("points", [])]), d)
        if t == "TextShape":
            return _with_rotation(TextShape(color, w, pt(d["pos"]), d.get("text", ""),
                                            int(d.get("font_size", 20))), d)
        if t == "StepShape":
            return _with_rotation(StepShape(color, w, pt(d["center"]),
                                            int(d.get("number", 1)), 0,
                                            float(d.get("diameter", 36))), d)
    except Exception:                              # noqa: BLE001
        return None
    return None


def _with_rotation(shape, d: dict):
    """把存下来的旋转角装回去（旧缓存没有 rot 字段 = 0）。"""
    if shape is not None and d.get("rot"):
        shape.rotation = float(d["rot"]) % 360.0
    return shape


# ---------------------------------------------------------------- 保存 / 读取

def _clear_dir():
    try:
        if SESSION_DIR.exists():
            shutil.rmtree(SESSION_DIR, ignore_errors=True)
    except Exception:                              # noqa: BLE001
        pass


def clear_session():
    """清掉上次的会话（用户关掉所有标签或主动清除时调用）。"""
    _clear_dir()


def has_session() -> bool:
    return (SESSION_DIR / "session.json").exists()


def save_session(tabs: list) -> bool:
    """保存会话。tabs: [{title, zoom, pixmap, shapes:[Shape]}, ...]"""
    tabs = [t for t in tabs if t.get("pixmap") is not None][:MAX_TABS]
    if not tabs:
        clear_session()
        return True
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:                              # noqa: BLE001
        return False

    # 先写到临时目录再整体替换，避免写到一半崩掉留下坏会话
    tmp = SESSION_DIR.with_name("session.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        total = 0
        items = []
        for i, tab in enumerate(tabs):
            pix = tab["pixmap"]
            name = f"tab{i}.png"
            path = tmp / name
            if not pix.save(str(path), "PNG"):
                continue
            total += path.stat().st_size
            if total > MAX_BYTES:
                path.unlink(missing_ok=True)
                break
            shapes = []
            for sh in tab.get("shapes", []):
                d = shape_to_dict(sh)
                if d:
                    shapes.append(d)
            items.append({"title": tab.get("title") or f"截图 {i + 1}",
                          "zoom": float(tab.get("zoom", 1.0)),
                          "dpr": float(pix.devicePixelRatio() or 1.0),
                          "file": name,
                          "shapes": shapes})
        meta = {"version": 1, "tabs": items}
        with open(tmp / "session.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        # 原子替换
        _clear_dir()
        tmp.rename(SESSION_DIR)
        return True
    except Exception:                              # noqa: BLE001
        shutil.rmtree(tmp, ignore_errors=True)
        return False


def load_session() -> list:
    """读回上次的会话；返回 [{title, zoom, pixmap, shapes}, ...]。"""
    meta_path = SESSION_DIR / "session.json"
    if not meta_path.exists():
        return []
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:                              # noqa: BLE001
        return []
    out = []
    for item in meta.get("tabs", [])[:MAX_TABS]:
        path = SESSION_DIR / str(item.get("file", ""))
        if not path.exists():
            continue
        pix = QPixmap(str(path))
        if pix.isNull():
            continue
        dpr = float(item.get("dpr") or 1.0)
        pix.setDevicePixelRatio(dpr)
        shapes = []
        for d in item.get("shapes", []):
            sh = shape_from_dict(d)
            if sh is not None:
                shapes.append(sh)
        out.append({"title": item.get("title") or "截图",
                    "zoom": float(item.get("zoom", 1.0)),
                    "pixmap": pix, "shapes": shapes})
    return out
