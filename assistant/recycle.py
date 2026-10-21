# -*- coding: utf-8 -*-
"""回收站：查询占用信息、清空回收站（仅 Windows，通过 Shell API）。"""

from __future__ import annotations

import os
import sys
from typing import Dict


def recycle_info() -> Dict[str, float]:
    """返回 {item_count, bytes}。非 Windows 返回 0。"""
    if sys.platform != "win32":
        return {"item_count": 0, "bytes": 0}
    try:
        import ctypes
        SHQUERYRBINFO = ctypes.create_string_buffer(24)
        ctypes.memset(SHQUERYRBINFO, 0, 24)
        ctypes.cast(SHQUERYRBINFO, ctypes.POINTER(ctypes.c_uint32))[0] = 24
        shell32 = ctypes.WinDLL("shell32")
        res = shell32.SHQueryRecycleBinW(None, SHQUERYRBINFO)
        if res != 0:
            return {"item_count": 0, "bytes": 0}
        import struct
        size, num = struct.unpack_from("<qq", SHQUERYRBINFO.raw, 4)
        return {"item_count": max(num, 0), "bytes": max(size, 0)}
    except Exception:
        return {"item_count": 0, "bytes": 0}


def empty_recycle_bin(flags: int = 0) -> None:
    """清空回收站。flags: 0=全部, 1=不显示进度/确认。"""
    if sys.platform != "win32":
        raise RuntimeError("仅 Windows 支持清空回收站。")
    import ctypes
    shell32 = ctypes.WinDLL("shell32")
    res = shell32.SHEmptyRecycleBinW(None, None, flags)
    if res != 0:
        raise OSError(f"SHEmptyRecycleBin 返回错误码 {res}")


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"
