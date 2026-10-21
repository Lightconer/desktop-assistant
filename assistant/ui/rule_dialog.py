# -*- coding: utf-8 -*-
"""分类规则编辑对话框。"""

from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..rules import RuleManager


class RuleDialog(QDialog):
    def __init__(self, rules: RuleManager, parent=None):
        super().__init__(parent)
        self.rules = rules
        self.setWindowTitle("分类规则设置")
        self.resize(580, 430)
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel("每行一个分类：扩展名用逗号分隔（如 .jpg,.png）；勾选=启用；"
                      "目标文件夹为被整理目录下的子文件夹名。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["启用", "分类名", "扩展名", "目标文件夹"])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 280)
        self.table.setColumnWidth(3, 110)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.SelectedClicked)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        add = QPushButton("新增分类")
        dele = QPushButton("删除选中")
        row.addWidget(add)
        row.addWidget(dele)
        row.addStretch(1)
        save = QPushButton("保存")
        cancel = QPushButton("取消")
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

        add.clicked.connect(self._add)
        dele.clicked.connect(self._delete)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)

    def _load(self) -> None:
        self.table.setRowCount(0)
        for name, cat in self.rules.rules["categories"].items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            ck = QTableWidgetItem()
            ck.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            ck.setCheckState(Qt.CheckState.Checked if cat.get("enabled", True)
                             else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, ck)
            self.table.setItem(r, 1, QTableWidgetItem(name))
            self.table.setItem(r, 2, QTableWidgetItem(",".join(cat["extensions"])))
            self.table.setItem(r, 3, QTableWidgetItem(cat.get("folder", name)))

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "新增分类", "分类名称：")
        if not ok or not name.strip():
            return
        if name.strip() in {self.table.item(r, 1).text() for r in range(self.table.rowCount())}:
            QMessageBox.warning(self, "提示", "分类名已存在。")
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        ck = QTableWidgetItem()
        ck.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        ck.setCheckState(Qt.CheckState.Checked)
        self.table.setItem(r, 0, ck)
        self.table.setItem(r, 1, QTableWidgetItem(name.strip()))
        self.table.setItem(r, 2, QTableWidgetItem(""))
        self.table.setItem(r, 3, QTableWidgetItem(name.strip()))
        self.table.setCurrentCell(r, 2)

    def _delete(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _collect(self) -> List[Tuple[str, List[str], str, bool]]:
        out = []
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 1)
            if not name or not name.text().strip():
                continue
            ext_text = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            exts = [e.strip().lower() for e in ext_text.split(",") if e.strip()]
            folder = self.table.item(r, 3).text().strip() if self.table.item(r, 3) else name.text().strip()
            enabled = bool(self.table.item(r, 0).checkState() == Qt.CheckState.Checked)
            out.append((name.text().strip(), exts, folder or name.text().strip(), enabled))
        return out

    def _save(self) -> None:
        rows = self._collect()
        if not rows:
            QMessageBox.warning(self, "提示", "至少保留一个有效分类。")
            return
        cats = {name: {"extensions": exts, "folder": folder, "enabled": enabled}
                for name, exts, folder, enabled in rows}
        self.rules.set_categories(cats)
        self.accept()
