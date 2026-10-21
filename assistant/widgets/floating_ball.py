# -*- coding: utf-8 -*-
"""悬浮球：桌面常驻小圆球，显示 CPU 占用，点击弹出快捷菜单。"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QContextMenuEvent, QPainter
from PySide6.QtWidgets import QMenu, QWidget

from ..monitor import SystemMonitor


class FloatingBall(QWidget):
    """圆形悬浮球。menu_builder(callable) 返回 QMenu 用于右键/单击菜单。"""

    def __init__(self, menu_builder: Optional[Callable[[], QMenu]] = None, parent=None):
        super().__init__(parent)
        self.menu_builder = menu_builder
        self._drag_offset = None
        self.setFixedSize(56, 56)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.monitor = SystemMonitor()
        self._cpu = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def set_menu_builder(self, builder: Callable[[], QMenu]) -> None:
        self.menu_builder = builder

    def _tick(self) -> None:
        s = self.monitor.snapshot()
        self._cpu = s.cpu_percent if self.monitor.available else 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QColor(30, 144, 255, 235)
        painter.setBrush(base)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, self.width() - 4, self.height() - 4)
        from PySide6.QtCore import QRectF
        rect = QRectF(7, 7, self.width() - 14, self.height() - 14)
        painter.setPen(QColor(255, 255, 255, 120))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * min(max(self._cpu, 0), 100) / 100))
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._cpu:.0f}%")
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_offset is not None and event.button() == Qt.MouseButton.LeftButton:
            moved = (event.globalPosition().toPoint() - (self._drag_offset + self.frameGeometry().topLeft()))
            if moved.manhattanLength() < 8:
                self._show_menu(event.globalPos())
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._show_menu(event.globalPos())

    def _show_menu(self, global_pos) -> None:
        if self.menu_builder:
            menu = self.menu_builder()
            if menu:
                menu.exec(global_pos)
