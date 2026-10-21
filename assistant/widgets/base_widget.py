# -*- coding: utf-8 -*-
"""桌面小组件基类：无边框、半透明、置顶、可拖动、右键菜单。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QContextMenuEvent
from PySide6.QtWidgets import QMenu, QWidget


class BaseWidget(QWidget):
    """可拖动、置顶、半透明的桌面小组件基类。"""

    closeRequested = Signal(str)

    def __init__(self, key: str, title: str, parent=None):
        super().__init__(parent)
        self.key = key
        self._drag_offset: QPoint | None = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)

    def _make_menu(self) -> QMenu:
        menu = QMenu(self)
        close = QAction("关闭", self)
        close.triggered.connect(lambda: self.closeRequested.emit(self.key))
        menu.addAction(close)
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._make_menu().exec(event.globalPos())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def move_to_screen(self) -> None:
        screen = self.screen() or self.window().screen()
        if screen is None:
            return
        g = self.frameGeometry()
        if not screen.availableGeometry().intersects(g):
            self.move(screen.availableGeometry().center() - self.rect().center())
