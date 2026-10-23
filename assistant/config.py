# -*- coding: utf-8 -*-
"""全局配置存储（JSON），原子写入。"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "desktop_dir": "",           # 空字符串 = 自动探测真实桌面
    "auto_watch": False,         # 桌面监听自动整理
    "dry_run": True,             # 整理预览模式
    "widgets": {                 # 小组件开关
        "panel": True,           # 360 风格侧边面板（统一入口）
        "ball": False,           # 悬浮球
        "clock": False,          # 时钟
        "weather": False,        # 天气
        "monitor": False,        # 系统监控
        "shelf": False,          # 收纳盒
        "todo": False,           # 事项清单
    },
    "clock_big": False,          # 时钟大字体
    "weather_city": "石家庄",
    "accelerate": {
        "clean_temp": True,      # 加速时清理临时文件
        "clean_memory": True,    # 加速时清理内存
        "clear_recycle": False,  # 加速时顺带清空回收站
    },
    "wallpaper": {               # 壁纸
        "dir": "",               # 壁纸目录（空 = 默认图片目录）
        "rotate": False,         # 定时轮播
        "interval": 600,         # 轮播间隔（秒）
    },
    "auto_start": False,         # 开机自启
}


def config_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".desktop_assistant")
    os.makedirs(d, exist_ok=True)
    return d


class AppConfig:
    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.path.join(config_dir(), "config.json")
        self.path = path
        self.data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.save()
            return
        if isinstance(loaded, dict):
            stored_widgets = loaded.get("widgets")
            self.data = _deep_merge(copy.deepcopy(DEFAULTS), loaded)
            # 旧版配置迁移：没有 panel 键说明是升级用户 → 默认启用侧边面板、收起零散小组件
            if isinstance(stored_widgets, dict) and "panel" not in stored_widgets:
                w = self.data.get("widgets") or {}
                w["panel"] = True
                for k in ("ball", "clock", "weather", "monitor", "shelf", "todo"):
                    w[k] = False
                self.data["widgets"] = w
                self.save()

    def save(self) -> None:
        tmp_fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def set_nested(self, top: str, key: str, value: Any) -> None:
        self.data.setdefault(top, {})[key] = value
        self.save()


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
