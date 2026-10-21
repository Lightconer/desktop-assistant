# -*- coding: utf-8 -*-
"""壁纸：扫描本地图片目录、设置 Windows 桌面壁纸、定时轮播。

- Windows：通过 SystemParametersInfoW(SPI_SETDESKWALLPAPER) 设置桌面壁纸。
- 非 Windows：扫描与轮播逻辑可用，实际设置返回 False（供界面提示）。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, List, Optional

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def _set_wallpaper_win(path: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, str(path),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return bool(ok)
    except Exception:
        return False


def default_wallpaper_dir() -> str:
    pics = os.path.join(os.path.expanduser("~"), "Pictures")
    cand = os.path.join(pics, "Wallpapers") if sys.platform == "win32" else pics
    return cand if os.path.isdir(cand) else pics


class WallpaperManager:
    """本地壁纸管理 + 定时轮播（轮播线程常驻，可后台运行）。"""

    def __init__(self, directory: str = "") -> None:
        self.directory = directory or default_wallpaper_dir()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._on_change: Optional[Callable[[str], None]] = None
        self._interval = 60.0
        self._current: Optional[str] = None

    def list_images(self) -> List[str]:
        d = self.directory
        if not os.path.isdir(d):
            return []
        try:
            names = [n for n in os.listdir(d)
                     if n.lower().endswith(IMAGE_EXTS)
                     and os.path.isfile(os.path.join(d, n))]
        except OSError:
            return []
        names.sort(key=str.lower)
        return [os.path.join(d, n) for n in names]

    def apply(self, path: str) -> bool:
        if not path or not os.path.isfile(path):
            return False
        if _set_wallpaper_win(path):
            self._current = path
            return True
        self._current = path
        return False

    def next(self) -> Optional[str]:
        imgs = self.list_images()
        if not imgs:
            return None
        idx = 0
        if self._current in imgs:
            idx = imgs.index(self._current) + 1
            if idx >= len(imgs):
                idx = 0
        self.apply(imgs[idx])
        return self._current

    def start_rotation(self, interval_sec: float,
                       on_change: Optional[Callable[[str], None]] = None) -> None:
        self.stop_rotation()
        self._interval = max(5.0, float(interval_sec))
        self._on_change = on_change
        self._stop.clear()
        self._thread = threading.Thread(target=self._rotation_loop,
                                        name="wallpaper-rotation",
                                        daemon=True)
        self._thread.start()

    def stop_rotation(self) -> None:
        self._stop.set()
        th, self._thread = self._thread, None
        if th and th.is_alive():
            th.join(timeout=3.0)

    def _rotation_loop(self) -> None:
        while not self._stop.wait(self._interval):
            if self._stop.is_set():
                break
            try:
                p = self.next()
                if p and self._on_change:
                    with self._lock:
                        self._on_change(p)
            except Exception:
                continue

    @property
    def rotating(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def shutdown(self) -> None:
        self.stop_rotation()
