# -*- coding: utf-8 -*-
"""事项清单小组件：桌面待办事项，支持添加 / 勾选完成 / 删除，JSON 持久化。"""

from __future__ import annotations

import json
import os
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .base_widget import BaseWidget


class TodoWidget(BaseWidget):
    def __init__(self, todo_path: str = "", key: str = "todo", parent=None):
        super().__init__(key, "事项清单", parent)
        if not todo_path:
            base = os.path.join(os.path.expanduser("~"), ".desktop_assistant")
            os.makedirs(base, exist_ok=True)
            todo_path = os.path.join(base, "todo.json")
        self.todo_path = todo_path
        self.items: List[dict] = []
        self.setFixedSize(248, 300)
        self._build_ui()
        self.load()
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("事项清单")
        title.setStyleSheet("color:#ffffff;font-size:14px;font-weight:bold;background:transparent;")
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color:#8fb4dd;font-size:12px;background:transparent;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count_label)
        layout.addLayout(head)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("添加待办事项…")
        self.input.setStyleSheet(
            "background:rgba(255,255,255,0.12);border:1px solid rgba(255,255,255,0.2);"
            "border-radius:7px;padding:5px 8px;color:#fff;font-size:13px;")
        self.input.returnPressed.connect(self.add_item)
        add_btn = QPushButton("添加")
        add_btn.setStyleSheet(
            "background:#2f6bff;color:#fff;border:none;border-radius:7px;padding:5px 12px;font-size:13px;")
        add_btn.clicked.connect(self.add_item)
        row.addWidget(self.input, 1)
        row.addWidget(add_btn)
        layout.addLayout(row)

        self.list = QListWidget()
        self.list.setStyleSheet(
            "background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.14);"
            "border-radius:8px;color:#eef4fb;font-size:13px;")
        self.list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list, 1)

        self.setStyleSheet("background-color:rgba(20,30,45,0.78);"
                           "border-radius:14px;border:1px solid rgba(255,255,255,0.18);")

    def add_item(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.items.append({"text": text, "done": False})
        self.input.clear()
        self.save()
        self._render()

    def _add_list_row(self, idx: int) -> None:
        item_data = self.items[idx]
        item = QListWidgetItem(item_data["text"])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if item_data["done"]
                           else Qt.CheckState.Unchecked)
        self.list.addItem(item)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        idx = self.list.row(item)
        if 0 <= idx < len(self.items):
            self.items[idx]["done"] = bool(item.checkState() == Qt.CheckState.Checked)
            self.save()
            self._update_count()

    def _update_count(self) -> None:
        left = sum(1 for it in self.items if not it["done"])
        self.count_label.setText(f"待办 {left} · 共 {len(self.items)}")

    def _render(self) -> None:
        self.list.clear()
        for i in range(len(self.items)):
            self._add_list_row(i)
        self._update_count()

    def load(self) -> None:
        if not os.path.exists(self.todo_path):
            return
        try:
            with open(self.todo_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.items = [{"text": str(d.get("text", "")), "done": bool(d.get("done", False))}
                              for d in data if d.get("text")]
        except (json.JSONDecodeError, OSError):
            self.items = []

    def save(self) -> None:
        # 原子写入：先写临时文件再替换，异常断电不损坏现有待办
        try:
            import tempfile
            tmp_fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self.todo_path) or ".", suffix=".tmp")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.todo_path)
        except OSError:
            pass
