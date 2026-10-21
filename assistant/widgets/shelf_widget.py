# -*- coding: utf-8 -*-
"""桌面收纳盒：把文件拖入盒内，自动按规则归类到分类文件夹。"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ..organizer import DesktopOrganizer, FileItem
from ..rules import RuleManager
from .base_widget import BaseWidget


class ShelfWidget(BaseWidget):
    """收纳盒小组件。拖入文件 → 自动分类归位。"""

    organizedCount = Signal(int)
    message = Signal(str)

    def __init__(self, desktop_dir: str, rules: RuleManager,
                 log_cb: Optional[Callable[[str], None]] = None, key: str = "shelf",
                 parent=None):
        super().__init__(key, "收纳盒", parent)
        self.desktop_dir = desktop_dir
        self.rules = rules
        self._log_cb = log_cb
        self.shelf_count = 0
        self.setFixedSize(132, 128)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)
        self.title_label = QLabel("收纳盒")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(
            "color:#ffffff;font-size:14px;font-weight:bold;background:transparent;")
        self.count_label = QLabel("已收纳 0 个")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setStyleSheet(
            "color:#cfe2fa;font-size:12px;background:transparent;")
        self.hint_label = QLabel("拖入文件自动归类")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet(
            "color:#8fb4dd;font-size:11px;background:transparent;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.count_label)
        layout.addWidget(self.hint_label)
        layout.addStretch(1)

        self.setStyleSheet("background-color:rgba(20,30,45,0.72);"
                           "border-radius:14px;border:1px solid rgba(255,255,255,0.18);")

    def _log(self, msg: str) -> None:
        if self._log_cb:
            try:
                self._log_cb(msg)
            except Exception:
                pass

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths: List[str] = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isfile(p):
                paths.append(p)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self._absorb(paths)

    def _absorb(self, paths: List[str]) -> None:
        items = [FileItem(src=p, name=os.path.basename(p),
                          category=self.rules.classify(os.path.basename(p))) for p in paths]
        items = [it for it in items if it.category is not None]
        if not items:
            self.message.emit("没有可归类的文件（未知类型或被保护）。")
            return
        org = DesktopOrganizer(self.desktop_dir, self.rules)
        ok, fail = org.run(items, dry_run=False)
        self.shelf_count += ok
        self.count_label.setText(f"已收纳 {self.shelf_count} 个")
        self.message.emit(f"收纳盒：成功归类 {ok} 个文件，失败 {fail}。")
        self.organizedCount.emit(ok)
