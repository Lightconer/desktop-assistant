# -*- coding: utf-8 -*-
"""桌面整理分类规则：默认规则 + 自定义规则持久化。"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any, Dict, Optional

DEFAULT_EXTENSIONS: Dict[str, list] = {
    "图片": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tif",
            ".tiff", ".heic", ".ico", ".raw", ".cr2", ".nef"],
    "文档": [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt",
            ".md", ".rtf", ".odt", ".csv", ".wps", ".et", ".dps"],
    "视频": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".rmvb"],
    "音频": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".mid"],
    "压缩包": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab"],
    "软件安装包": [".exe", ".msi", ".apk", ".dmg", ".deb", ".rpm"],
    "快捷方式": [".lnk", ".url"],
    "代码": [".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs",
            ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sh", ".bat",
            ".sql", ".ipynb", ".vue", ".php", ".rb"],
    "字体": [".ttf", ".otf", ".woff", ".woff2", ".eot"],
}

PROTECTED_NAMES = {"desktop.ini", "thumbs.db", "autorun.inf"}


class RuleManager:
    """分类规则的读取、修改与持久化。"""

    def __init__(self, rules_path: Optional[str] = None):
        if rules_path is None:
            rules_path = os.path.join(os.path.expanduser("~"), ".desktop_assistant", "rules.json")
        self.rules_path = rules_path
        self.rules: Dict[str, Any] = {
            "categories": {name: {"extensions": exts, "folder": name, "enabled": True}
                           for name, exts in DEFAULT_EXTENSIONS.items()},
            "ignore": {name: True for name in PROTECTED_NAMES},
        }
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.rules_path):
            self.save()
            return
        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.save()
            return
        if isinstance(data, dict):
            self.rules["categories"].update(data.get("categories") or {})
            self.rules["ignore"].update(data.get("ignore") or {})

    def save(self) -> None:
        parent = os.path.dirname(self.rules_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.rules_path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    def get_enabled_categories(self) -> Dict[str, Dict]:
        return {n: c for n, c in self.rules["categories"].items() if c.get("enabled", True)}

    def get_ignore_names(self) -> set:
        return {n.lower() for n, v in self.rules["ignore"].items() if v}

    def classify(self, filename: str) -> Optional[str]:
        ext = os.path.splitext(filename)[1].lower()
        for name, cat in self.get_enabled_categories().items():
            if ext in cat["extensions"]:
                return name
        return None

    def set_categories(self, categories: Dict[str, Dict]) -> None:
        self.rules["categories"] = categories
        self.save()
