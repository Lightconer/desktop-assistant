# -*- coding: utf-8 -*-
"""桌面整理执行器：扫描、计划、移动、冲突处理、撤销。"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .rules import RuleManager


@dataclass
class FileItem:
    src: str
    name: str
    category: Optional[str]
    dest: Optional[str] = None
    moved: bool = False


@dataclass
class ActionRecord:
    src: str
    dest: str
    timestamp: float = field(default_factory=time.time)


class DesktopOrganizer:
    def __init__(self, desktop_dir: str, rules: RuleManager):
        self.desktop_dir = os.path.abspath(desktop_dir)
        self.rules = rules
        self.records: List[ActionRecord] = []
        self.logs: List[str] = []
        self._log_cb: Optional[Callable[[str], None]] = None

    def set_log_callback(self, cb: Optional[Callable[[str], None]]) -> None:
        self._log_cb = cb

    def _log(self, msg: str) -> None:
        self.logs.append(msg)
        if self._log_cb:
            try:
                self._log_cb(msg)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def scan(self) -> List[FileItem]:
        items: List[FileItem] = []
        if not os.path.isdir(self.desktop_dir):
            return items
        ignore = self.rules.get_ignore_names()
        for entry in sorted(os.scandir(self.desktop_dir), key=lambda e: e.name.lower()):
            if entry.is_dir():
                continue
            name = entry.name
            if name.startswith("."):
                continue
            if name.lower() in ignore:
                continue
            items.append(FileItem(entry.path, name, self.rules.classify(name)))
        return items

    def plan(self, items: Optional[List[FileItem]] = None) -> List[FileItem]:
        items = items if items is not None else self.scan()
        for it in items:
            if it.category is None:
                it.dest = None
                continue
            folder = self.rules.get_enabled_categories()[it.category].get("folder") or it.category
            it.dest = self._unique_dest(os.path.join(self.desktop_dir, folder), it.name)
        return items

    @staticmethod
    def _unique_dest(dest_dir: str, name: str) -> str:
        base, ext = os.path.splitext(name)
        candidate = os.path.join(dest_dir, name)
        n = 1
        while os.path.exists(candidate):
            candidate = os.path.join(dest_dir, f"{base} ({n}){ext}")
            n += 1
        return candidate

    # ------------------------------------------------------------------
    def run(self, items: Optional[List[FileItem]] = None, dry_run: bool = True) -> Tuple[int, int]:
        items = self.plan(items)
        planned = [it for it in items if it.dest is not None]
        if not planned:
            self._log("没有需要整理的文件。")
            return 0, 0
        ok = fail = 0
        if dry_run:
            self._log(f"[预览] 共 {len(planned)} 个文件将被整理，未实际移动。")
            for it in planned:
                self._log(f"  移动 → {it.dest}")
            return len(planned), 0
        self._log(f"开始整理 {self.desktop_dir} …")
        for it in planned:
            try:
                dest_dir = os.path.dirname(it.dest)
                os.makedirs(dest_dir, exist_ok=True)
                final = it.dest
                if os.path.exists(final) and os.path.normcase(os.path.abspath(final)) \
                        != os.path.normcase(os.path.abspath(it.src)):
                    final = self._unique_dest(dest_dir, it.name)
                shutil.move(it.src, final)
                it.dest = final
                it.moved = True
                self.records.append(ActionRecord(it.src, final))
                self._log(f"  ✓ {it.name} → {os.path.basename(os.path.dirname(final))}/")
                ok += 1
            except OSError as e:
                self._log(f"  ✗ {it.name} 移动失败：{e}")
                fail += 1
        self._log(f"整理完成：成功 {ok}，失败 {fail}。")
        return ok, fail

    def undo(self) -> Tuple[int, int]:
        ok = fail = 0
        for rec in reversed(self.records):
            try:
                if not os.path.exists(rec.src) and os.path.exists(rec.dest):
                    os.makedirs(os.path.dirname(rec.src), exist_ok=True)
                    shutil.move(rec.dest, rec.src)
                    ok += 1
            except OSError as e:
                self._log(f"撤销 {rec.dest} 失败：{e}")
                fail += 1
        n = len(self.records)
        self.records.clear()
        self._log(f"已撤销 {n} 个文件的移动（成功 {ok}，失败 {fail}）。")
        return ok, fail

    def has_undo(self) -> bool:
        return bool(self.records)
