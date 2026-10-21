# -*- coding: utf-8 -*-
"""系统监控小组件：CPU / 内存 / 磁盘 / 网速，秒级刷新。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ..monitor import SystemMonitor
from .base_widget import BaseWidget


class MonitorWidget(BaseWidget):
    def __init__(self, key: str = "monitor", parent=None):
        super().__init__(key, "系统监控", parent)
        self.setFixedSize(210, 120)
        self.monitor = SystemMonitor()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        title = QLabel("系统状态")
        title.setStyleSheet("color:#ffffff;font-size:13px;font-weight:bold;background:transparent;")
        layout.addWidget(title)

        self.cpu_label = self._mk_label()
        self.mem_label = self._mk_label()
        self.disk_label = self._mk_label()
        self.net_label = self._mk_label()
        layout.addWidget(self.cpu_label)
        layout.addWidget(self.mem_label)
        layout.addWidget(self.disk_label)
        layout.addWidget(self.net_label)

        self.setStyleSheet("background-color:rgba(20,30,45,0.72);"
                           "border-radius:14px;border:1px solid rgba(255,255,255,0.18);")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1000)
        self._refresh()

    @staticmethod
    def _mk_label() -> QLabel:
        lb = QLabel("-")
        lb.setStyleSheet("color:#e6f0ff;font-size:13px;background:transparent;")
        return lb

    def _refresh(self) -> None:
        s = self.monitor.snapshot()
        if not self.monitor.available:
            self.cpu_label.setText("系统监控：需要安装 psutil")
            return
        self.cpu_label.setText(f"CPU  {s.cpu_percent:5.1f}%")
        self.mem_label.setText(
            f"内存 {s.mem_percent:5.1f}%  ({s.mem_used_gb:.1f}/{s.mem_total_gb:.1f}G)")
        self.disk_label.setText(f"磁盘 {s.disk_percent:5.1f}%")
        self.net_label.setText(
            f"网速  ↑{s.net_up_kbs/1024:5.1f}  ↓{s.net_down_kbs/1024:5.1f} MB/s")
