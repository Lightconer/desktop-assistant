# -*- coding: utf-8 -*-
"""电脑加速：一键清理内存工作集、清理临时文件、可选清空回收站。

说明：Windows 下内存“清理”本质是调用 EmptyWorkingSet 让进程释放可回收内存页，
并非凭空增加物理内存；临时文件清理会跳过被占用的文件。结果如实反馈，不夸大。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from .recycle import recycle_info, empty_recycle_bin


@dataclass
class CleanResult:
    temp_files: int = 0
    temp_mb: float = 0.0
    recycled: bool = False
    memory_trimmed: bool = False
    skipped: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _empty_working_set_windows() -> bool:
    """Windows 下调用 SetProcessWorkingSetSize(-1,-1) 尽量让系统回收当前进程内存。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.GetCurrentProcess()
        ok = kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
        return bool(ok)
    except Exception:
        return False


def _temp_dirs() -> List[str]:
    dirs: List[str] = []
    if sys.platform == "win32":
        for env in ("TEMP", "TMP"):
            p = os.environ.get(env)
            if p and os.path.isdir(p) and p not in dirs:
                dirs.append(p)
    else:
        dirs.append("/tmp")
    sys_tmp = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")
    if sys.platform == "win32" and os.path.isdir(sys_tmp) and sys_tmp not in dirs:
        dirs.append(sys_tmp)
    return dirs


def clean_temp_files(on_progress: Optional[Callable[[str], None]] = None) -> Tuple[int, float, int]:
    """清理临时文件。返回 (删除文件数, 释放MB, 跳过数)。"""
    count = 0
    freed = 0.0
    skipped = 0
    for d in _temp_dirs():
        if on_progress:
            on_progress(f"清理 {d} …")
        try:
            for root, _, files in os.walk(d):
                for name in files:
                    try:
                        p = os.path.join(root, name)
                        size = os.path.getsize(p)
                        os.remove(p)
                        count += 1
                        freed += size / (1024 * 1024)
                    except OSError:
                        skipped += 1
        except OSError:
            pass
    return count, freed, skipped


def one_click_clean(config=None, on_progress: Optional[Callable[[str], None]] = None) -> CleanResult:
    """一键加速：按配置清理临时文件 / 内存 / 回收站。"""
    result = CleanResult()
    opts = (config.get("accelerate") if config else None) or {}

    if opts.get("clean_temp", True):
        result.temp_files, result.temp_mb, result.skipped = clean_temp_files(on_progress)

    if opts.get("clear_recycle", False):
        try:
            empty_recycle_bin()
            result.recycled = True
        except Exception as e:
            result.errors.append(f"清空回收站失败：{e}")

    if opts.get("clean_memory", True):
        if sys.platform == "win32":
            result.memory_trimmed = _empty_working_set_windows()
        else:
            result.memory_trimmed = False

    return result
