# -*- coding: utf-8 -*-
"""系统监控：CPU / 内存 / 磁盘 / 网速（基于 psutil）。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False


@dataclass
class Snapshot:
    cpu_percent: float
    mem_percent: float
    mem_used_gb: float
    mem_total_gb: float
    disk_percent: float
    net_up_kbs: float
    net_down_kbs: float


class SystemMonitor:
    def __init__(self):
        self._prev = None
        self._prev_t = time.monotonic()
        if _HAS_PSUTIL:
            psutil.cpu_percent(interval=None)  # 预热，避免首次返回 0
            self._prev = psutil.net_io_counters()

    @property
    def available(self) -> bool:
        return _HAS_PSUTIL

    def snapshot(self) -> Snapshot:
        if not _HAS_PSUTIL:
            return Snapshot(0, 0, 0, 0, 0, 0, 0)
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        now = psutil.net_io_counters()
        dt = max(time.monotonic() - self._prev_t, 0.001)
        up = (now.bytes_sent - self._prev.bytes_sent) / dt / 1024
        down = (now.bytes_recv - self._prev.bytes_recv) / dt / 1024
        self._prev = now
        self._prev_t = time.monotonic()
        return Snapshot(
            cpu_percent=cpu,
            mem_percent=mem.percent,
            mem_used_gb=mem.used / (1024 ** 3),
            mem_total_gb=mem.total / (1024 ** 3),
            disk_percent=disk.percent,
            net_up_kbs=up,
            net_down_kbs=down,
        )
