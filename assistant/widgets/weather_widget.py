# -*- coding: utf-8 -*-
"""天气小组件：联网获取实时天气，失败时显示降级文案并定时重试。"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ..weather import get_weather
from .base_widget import BaseWidget


class _WeatherWorker(QObject):
    done = Signal(object)

    def __init__(self, city: str):
        super().__init__()
        self.city = city

    def run(self) -> None:
        self.done.emit(get_weather(self.city))


class WeatherWidget(BaseWidget):
    def __init__(self, city: str, key: str = "weather", parent=None):
        super().__init__(key, "天气", parent)
        self.city = city
        self.setFixedSize(220, 110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        self.title_label = QLabel(city)
        self.title_label.setStyleSheet(
            "color:#ffffff;font-size:14px;font-weight:bold;background:transparent;")
        self.temp_label = QLabel("获取中…")
        self.temp_label.setStyleSheet(
            "color:#ffffff;font-size:30px;font-weight:bold;background:transparent;")
        self.desc_label = QLabel("")
        self.desc_label.setStyleSheet("color:#dfe9ff;font-size:13px;background:transparent;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.temp_label)
        layout.addWidget(self.desc_label)

        self.setStyleSheet("background-color:rgba(20,30,45,0.72);"
                           "border-radius:14px;border:1px solid rgba(255,255,255,0.18);")

        self._thread = None
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        if self._thread is not None:
            return
        self._thread = QThread(self)
        worker = _WeatherWorker(self.city)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.done.connect(self._on_result)
        worker.done.connect(self._thread.quit)
        worker.done.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_thread)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(4000)
            self._thread = None

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)

    def _clear_thread(self) -> None:
        self._thread = None

    def _on_result(self, data) -> None:
        if data:
            self.title_label.setText(f"{data['city']} · {data['desc']}")
            self.temp_label.setText(f"{data['temp']}°C")
            self.desc_label.setText(
                f"湿度 {data['humidity']}%   风速 {data['wind']} km/h")
        else:
            self.temp_label.setText("天气获取失败")
            self.desc_label.setText("将自动重试")
            self._retry.start(60000)
