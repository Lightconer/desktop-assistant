# -*- coding: utf-8 -*-
"""全局文件搜索：按文件名关键字在指定目录树中搜索文件。"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

SKIP_DIR_NAMES = {
    "windows", "winnt", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "node_modules", "appdata",
    ".git", "__pycache__", ".cache", "temp", "tmp",
}


def search_files(
    keyword: str,
    roots: List[str],
    limit: int = 200,
    on_progress: Optional[Callable[[str], None]] = None,
    check_cancel: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """在 roots 目录树下按文件名（含扩展名）子串匹配搜索。"""
    keyword_lower = keyword.lower()
    if not keyword_lower:
        return []
    results: List[str] = []
    scanned = 0

    def walk(root: str) -> None:
        nonlocal scanned
        if len(results) >= limit:
            return
        try:
            entries = list(os.scandir(root))
        except OSError:
            return
        for entry in entries:
            if check_cancel and check_cancel():
                return
            if len(results) >= limit:
                return
            try:
                if entry.is_dir():
                    name = entry.name.lower()
                    if name in SKIP_DIR_NAMES or entry.name.startswith("."):
                        continue
                    walk(entry.path)
                elif keyword_lower in entry.name.lower():
                    results.append(entry.path)
                    scanned += 1
                    if on_progress and scanned % 20 == 0:
                        on_progress(f"已找到 {len(results)} 个…")
            except OSError:
                continue

    for r in roots:
        if os.path.isdir(r):
            walk(r)
    return results
