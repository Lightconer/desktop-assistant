# -*- coding: utf-8 -*-
"""时钟小组件：时间 + 日期 + 农历（节日提醒），支持大字体显示。"""

from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ..lunar import solar_to_lunar
from .base_widget import BaseWidget


class ClockWidget(BaseWidget):
    def __init__(self, key: str = "clock", big: bool = False,
                 on_big_change: Optional[Callable[[bool], None]] = None, parent=None):
        super().__init__(key, "时钟", parent)
        self.big = big
        self.on_big_change = on_big_change
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lunar_label = QLabel("")
        self.lunar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lunar_label.setStyleSheet("color:#cfe2fa;font-size:12px;background:transparent;")
        layout.addWidget(self.time_label)
        layout.addWidget(self.date_label)
        layout.addWidget(self.lunar_label)

        self.setStyleSheet("background-color:rgba(20,30,45,0.72);"
                           "border-radius:14px;border:1px solid rgba(255,255,255,0.18);")
        self._apply_style()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _apply_style(self) -> None:
        if self.big:
            self.setFixedSize(300, 152)
            self.time_label.setStyleSheet(
                "color:#ffffff;font-size:62px;font-weight:bold;background:transparent;")
            self.date_label.setStyleSheet(
                "color:#ffffff;font-size:16px;background:transparent;")
        else:
            self.setFixedSize(190, 108)
            self.time_label.setStyleSheet(
                "color:#ffffff;font-size:34px;font-weight:bold;background:transparent;")
            self.date_label.setStyleSheet(
                "color:#ffffff;font-size:14px;background:transparent;")

    def _tick(self) -> None:
        now = time.localtime()
        self.time_label.setText(time.strftime("%H:%M:%S", now))
        self.date_label.setText(time.strftime("%Y年%m月%d日 %A", now))
        lunar = solar_to_lunar(now.tm_year, now.tm_mon, now.tm_mday)
        if lunar:
            self.lunar_label.setText(
                f"{lunar.ganzhi_year}{lunar.zodiac}年 · {lunar.display()}")
        else:
            self.lunar_label.setText("")

    def set_big(self, big: bool) -> None:
        if big == self.big:
            return
        self.big = big
        self._apply_style()

    def _make_menu(self):
        menu = super()._make_menu()
        menu.addSeparator()
        act = QAction("大字体显示" if not self.big else "常规字体", menu)
        act.triggered.connect(self._toggle_big)
        menu.addAction(act)
        return menu

    def _toggle_big(self) -> None:
        self.set_big(not self.big)
        if self.on_big_change:
            try:
                self.on_big_change(self.big)
            except Exception:
                pass
