# -*- coding: utf-8 -*-
"""主控制台：桌面整理 / 电脑加速 / 回收站 / 软件管理 / 全局搜索 / 设置。"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QSize, Qt, QUrl

from ..config import AppConfig
from ..organizer import DesktopOrganizer
from ..rules import RuleManager
from ..accelerate import one_click_clean
from ..recycle import human_bytes, recycle_info, empty_recycle_bin
from ..apps import list_installed_apps, uninstall_app, open_app_location, set_auto_start
from ..wallpaper import WallpaperManager
from ..shutdown_timer import ACTIONS as SHUTDOWN_ACTIONS
from ..shutdown_timer import Countdown, cancel as shutdown_cancel, execute as shutdown_execute, supported as shutdown_supported
from ..search import search_files
from ..fast_search import FastIndex, EverythingBackend, default_roots as index_roots
from .rule_dialog import RuleDialog


def toast_like(win, msg: str, ms: int = 2600) -> None:
    try:
        win.statusBar().showMessage(msg, ms)
    except Exception:
        pass


def _default_roots() -> list:
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "Desktop"), os.path.join(home, "Documents"),
             os.path.join(home, "Downloads")]
    if sys.platform == "win32":
        roots += [os.path.join(home, "Pictures"), os.path.join(home, "Music"),
                  os.path.join(home, "Videos")]
    return [r for r in roots if os.path.isdir(r)] or [home]


class _SearchThread(QThread):
    done = Signal(list)
    progress = Signal(str)

    def __init__(self, keyword, roots, limit):
        super().__init__()
        self.keyword, self.roots, self.limit = keyword, roots, limit
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        res = search_files(self.keyword, self.roots, self.limit,
                           on_progress=lambda m: self.progress.emit(m),
                           check_cancel=lambda: self._cancel)
        self.done.emit(res)


class _IndexThread(QThread):
    progress = Signal(int)
    done = Signal(int, str)
    error = Signal(str)

    def __init__(self, fast_index: FastIndex, roots):
        super().__init__()
        self.fast_index = fast_index
        self.roots = roots
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            n = self.fast_index.rebuild(
                self.roots,
                progress=lambda c: self.progress.emit(c),
                cancel=lambda: self._cancel)
            if self._cancel:
                self.done.emit(0, "索引重建已取消（旧索引保留）。")
            else:
                self.done.emit(n, f"索引重建完成：{n:,} 个文件。")
        except Exception as e:
            self.error.emit(str(e))


class _EverythingCheck(QThread):
    result = Signal(bool)

    def __init__(self, backend: EverythingBackend):
        super().__init__()
        self.backend = backend

    def run(self):
        self.result.emit(self.backend.available())


class _AccelThread(QThread):
    """一键加速后台线程，避免清理临时文件时卡死界面。"""
    progress = Signal(str)
    done = Signal(object)

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config

    def run(self):
        try:
            result = one_click_clean(self.config,
                                     on_progress=lambda m: self.progress.emit(m))
        except Exception as e:
            result = e
        self.done.emit(result)


class _AppsThread(QThread):
    """后台枚举已安装软件（注册表读取较慢，避免阻塞界面）。"""
    done = Signal(list)

    def run(self):
        try:
            self.done.emit(list_installed_apps())
        except Exception:
            self.done.emit([])


class _EverythingSearchThread(QThread):
    """Everything HTTP 搜索后台线程（接口无响应时不再冻结界面）。"""
    done = Signal(list)

    def __init__(self, backend: EverythingBackend, keyword: str, limit: int = 200):
        super().__init__()
        self.backend, self.keyword, self.limit = backend, keyword, limit

    def run(self):
        self.done.emit(self.backend.search(self.keyword, self.limit))


class MainWindow(QMainWindow):
    widgetPrefsChanged = Signal()
    wallChanged = Signal(str)   # 壁纸轮播线程 → 主线程安全通知

    def __init__(self, config: AppConfig):
        super().__init__()
        self.cfg = config
        self.rules = RuleManager()
        self.desktop_dir = self._resolve_desktop()
        self.organizer = DesktopOrganizer(self.desktop_dir, self.rules)
        self.organizer.set_log_callback(self._append_log)
        self._search_thread = None
        self._accel_thread = None
        self._apps_thread = None
        self._everything_search_thread = None

        self.setWindowTitle("桌面助手")
        self.resize(980, 680)
        self.wallChanged.connect(
            lambda p: toast_like(self, f"壁纸已自动切换：{os.path.basename(p)}"))
        self._build_ui()
        self._load_settings()
        self.scan_organize()
        self._init_fast_search()

    _TAB_INDEX = {"organize": 0, "accelerate": 1, "recycle": 2, "apps": 3,
                  "search": 4, "wallpaper": 5, "shutdown": 6, "settings": 7}

    def focus_tab(self, key: str) -> None:
        """唤起主窗口并定位到指定功能页签（供侧边面板等调用）。"""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        idx = self._TAB_INDEX.get(key)
        if idx is not None:
            self._tabs.setCurrentIndex(idx)
            if key == "search":
                self.search_input.setFocus()

    def closeEvent(self, event) -> None:
        for th in (getattr(self, "_idx_thread", None), getattr(self, "_search_thread", None),
                   self._accel_thread, self._apps_thread, self._everything_search_thread):
            if th and th.isRunning():
                if hasattr(th, "cancel"):
                    try:
                        th.cancel()
                    except Exception:
                        pass
                th.wait(3000)
        mgr = getattr(self, "wall_mgr", None)
        if mgr:
            mgr.shutdown()
        super().closeEvent(event)

    def _resolve_desktop(self) -> str:
        cfg_dir = self.cfg.get("desktop_dir")
        if cfg_dir and os.path.isdir(cfg_dir):
            return cfg_dir
        d = os.path.join(os.path.expanduser("~"), "Desktop")
        if sys.platform == "win32":
            try:
                from ctypes import windll, wintypes
                buf = wintypes.create_unicode_buffer(wintypes.MAX_PATH)
                if windll.shell32.SHGetFolderPathW(None, 0, None, 0, buf) == 0 and buf.value:
                    d = buf.value
            except Exception:
                pass
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def _build_ui(self) -> None:
        tabs = QTabWidget(self)
        self.setCentralWidget(tabs)
        tabs.addTab(self._build_organize_tab(), "桌面整理")
        tabs.addTab(self._build_accelerate_tab(), "电脑加速")
        tabs.addTab(self._build_recycle_tab(), "回收站")
        tabs.addTab(self._build_apps_tab(), "软件管理")
        tabs.addTab(self._build_search_tab(), "秒级搜索")
        tabs.addTab(self._build_wallpaper_tab(), "壁纸")
        tabs.addTab(self._build_shutdown_tab(), "定时关机")
        tabs.addTab(self._build_settings_tab(), "设置")
        self._tabs = tabs

    def _build_organize_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        top = QHBoxLayout()
        top.addWidget(QLabel("整理目录："))
        self.dir_label = QLabel(self.desktop_dir)
        self.dir_label.setStyleSheet("color:#444;")
        top.addWidget(self.dir_label, 1)
        choose = QPushButton("选择目录…")
        choose.clicked.connect(self._choose_dir)
        top.addWidget(choose)
        self.watch_cb = QCheckBox("自动整理新文件")
        self.watch_cb.toggled.connect(self._toggle_watch)
        top.addWidget(self.watch_cb)
        self.dry_cb = QCheckBox("预览模式(不移动)")
        self.dry_cb.toggled.connect(self._toggle_dry)
        top.addWidget(self.dry_cb)
        root.addLayout(top)

        self.org_stat = QLabel("")
        self.org_stat.setStyleSheet("color:#888;")
        root.addWidget(self.org_stat)

        self.org_table = QTableWidget(0, 5)
        self.org_table.setHorizontalHeaderLabels(["文件名", "类型", "扩展名", "目标文件夹", "状态"])
        self.org_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.org_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.org_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, wid in [(1, 90), (2, 80), (3, 160), (4, 90)]:
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.org_table.setColumnWidth(i, wid)
        root.addWidget(self.org_table, 1)

        btns = QHBoxLayout()
        for text, slot in (("重新扫描", self.scan_organize), ("一键整理", self._organize),
                           ("撤销上次", self._undo), ("分类规则…", self._edit_rules)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        open_btn = QPushButton("打开目录")
        open_btn.clicked.connect(self._open_desktop)
        btns.addWidget(open_btn)
        root.addLayout(btns)

        root.addWidget(QLabel("操作日志"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(140)
        root.addWidget(self.log_view)
        return w

    def _build_accelerate_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        acc = self.cfg.get("accelerate")
        self.acc_temp_cb = QCheckBox("清理临时文件（%TEMP% 等）")
        self.acc_temp_cb.setChecked(acc.get("clean_temp", True))
        self.acc_mem_cb = QCheckBox("清理内存（让系统回收可释放内存页）")
        self.acc_mem_cb.setChecked(acc.get("clean_memory", True))
        self.acc_rc_cb = QCheckBox("顺带清空回收站")
        self.acc_rc_cb.setChecked(acc.get("clear_recycle", False))
        root.addWidget(QLabel("一键加速选项："))
        root.addWidget(self.acc_temp_cb)
        root.addWidget(self.acc_mem_cb)
        root.addWidget(self.acc_rc_cb)

        self.acc_progress = QLabel("")
        self.acc_progress.setWordWrap(True)
        self.acc_progress.setStyleSheet("color:#555;")
        root.addWidget(self.acc_progress)

        run_btn = QPushButton("一键加速")
        run_btn.setStyleSheet("font-weight:bold;padding:6px 18px;")
        run_btn.clicked.connect(self._accelerate)
        self._accel_run_btn = run_btn
        root.addWidget(run_btn)
        root.addStretch(1)
        tip = QLabel("说明：内存清理通过 Windows API 让系统回收可释放的内存页，不会凭空增加物理内存；"
                     "清理临时文件会跳过正在被占用的文件，结果如实统计。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#999;")
        root.addWidget(tip)
        return w

    def _build_recycle_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        self.rc_info = QLabel("")
        root.addWidget(self.rc_info)
        row = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_recycle)
        empty_btn = QPushButton("清空回收站")
        empty_btn.clicked.connect(self._empty_recycle)
        row.addWidget(refresh_btn)
        row.addWidget(empty_btn)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)
        if sys.platform != "win32":
            root.addWidget(QLabel("（回收站功能仅 Windows 可用）"))
        self._refresh_recycle()
        return w

    def _build_apps_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("已安装软件："))
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.clicked.connect(self._load_apps)
        row.addWidget(refresh_btn)
        row.addStretch(1)
        root.addLayout(row)

        self.app_table = QTableWidget(0, 3)
        self.app_table.setHorizontalHeaderLabels(["软件名称", "版本", "发布者"])
        self.app_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.app_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.app_table, 1)

        row2 = QHBoxLayout()
        uninstall_btn = QPushButton("卸载选中")
        uninstall_btn.clicked.connect(self._uninstall_selected)
        loc_btn = QPushButton("打开安装目录")
        loc_btn.clicked.connect(self._open_app_location)
        row2.addWidget(uninstall_btn)
        row2.addWidget(loc_btn)
        row2.addStretch(1)
        root.addLayout(row2)
        if sys.platform != "win32":
            root.addWidget(QLabel("（软件管理仅 Windows 可用）"))
        self._load_apps()
        return w

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("搜索文件名："))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键字，毫秒级返回全盘结果（≥3 字走 FTS 索引）")
        self.search_input.returnPressed.connect(self._do_search)
        row.addWidget(self.search_input, 1)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._do_search)
        row.addWidget(search_btn)
        stop_btn = QPushButton("停止")
        stop_btn.clicked.connect(self._stop_search)
        row.addWidget(stop_btn)
        root.addLayout(row)

        self.idx_stat = QLabel("索引状态：…")
        self.idx_stat.setStyleSheet("color:#888;")
        root.addWidget(self.idx_stat)
        row2 = QHBoxLayout()
        rebuild_btn = QPushButton("重建索引")
        rebuild_btn.clicked.connect(self._rebuild_index)
        refresh_btn = QPushButton("后台刷新")
        refresh_btn.clicked.connect(self._refresh_index)
        row2.addWidget(rebuild_btn)
        row2.addWidget(refresh_btn)
        self.everything_cb = QCheckBox("优先使用 Everything（本机已安装并开启 HTTP 服务时）")
        self.everything_cb.toggled.connect(self._on_everything_toggle)
        row2.addWidget(self.everything_cb)
        row2.addStretch(1)
        root.addLayout(row2)
        self.idx_progress = QLabel("")
        self.idx_progress.setStyleSheet("color:#888;")
        root.addWidget(self.idx_progress)

        self.search_progress = QLabel("")
        self.search_progress.setStyleSheet("color:#888;")
        root.addWidget(self.search_progress)

        self.search_table = QTableWidget(0, 2)
        self.search_table.setHorizontalHeaderLabels(["文件路径", "大小"])
        self.search_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.search_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.search_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.search_table.cellDoubleClicked.connect(self._open_search_item)
        root.addWidget(self.search_table, 1)

        row3 = QHBoxLayout()
        open_btn = QPushButton("打开所选")
        open_btn.clicked.connect(self._open_search_item_btn)
        row3.addWidget(open_btn)
        row3.addStretch(1)
        root.addLayout(row3)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(220)
        self._search_debounce.timeout.connect(self._do_search)
        self.search_input.textChanged.connect(lambda _t: self._search_debounce.start())
        return w

    def _build_wallpaper_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        row = QHBoxLayout()
        row.addWidget(QLabel("壁纸目录："))
        self.wall_dir_label = QLabel("")
        row.addWidget(self.wall_dir_label, 1)
        btn = QPushButton("选择目录…")
        btn.clicked.connect(self._choose_wall_dir)
        row.addWidget(btn)
        root.addLayout(row)

        self.wall_list = QListWidget()
        self.wall_list.setIconSize(QSize(120, 76))
        self.wall_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.wall_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.wall_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.wall_list.itemDoubleClicked.connect(self._apply_wallpaper_item)
        root.addWidget(self.wall_list, 1)

        ops = QHBoxLayout()
        self.wall_apply_btn = QPushButton("应用选中壁纸")
        self.wall_apply_btn.clicked.connect(self._apply_wallpaper_selected)
        ops.addWidget(self.wall_apply_btn)
        self.wall_rotate_cb = QCheckBox("定时轮播")
        self.wall_rotate_cb.toggled.connect(self._toggle_wall_rotate)
        ops.addWidget(self.wall_rotate_cb)
        ops.addWidget(QLabel("间隔(秒)："))
        self.wall_interval_sp = QSpinBox()
        self.wall_interval_sp.setRange(10, 3600)
        self.wall_interval_sp.setValue(600)
        ops.addWidget(self.wall_interval_sp)
        ops.addStretch(1)
        root.addLayout(ops)

        self.wall_stat = QLabel("壁纸：未设置。非 Windows 平台仅预览，不实际修改桌面。")
        self.wall_stat.setStyleSheet("color:#888;")
        root.addWidget(self.wall_stat)

        self.wall_mgr = WallpaperManager()
        self.wall_images: list = []
        self._load_wallpaper_settings()
        return w

    def _choose_wall_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择壁纸目录", self.wall_mgr.directory)
        if d:
            self.wall_mgr.directory = d
            self.wall_dir_label.setText(d)
            self.cfg.set_nested("wallpaper", "dir", d)
            self._reload_wall_list()
            self.wall_stat.setText(f"壁纸目录：{d}（{len(self.wall_images)} 张）")

    def _reload_wall_list(self) -> None:
        self.wall_list.clear()
        self.wall_images = self.wall_mgr.list_images()
        for p in self.wall_images:
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            thumb = QIcon(p)
            if not thumb.isNull():
                item.setIcon(thumb)
            self.wall_list.addItem(item)
        self.wall_stat.setText(f"壁纸：{len(self.wall_images)} 张。双击或选中后点「应用选中壁纸」。")

    def _apply_wallpaper_item(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.ItemDataRole.UserRole)
        ok = self.wall_mgr.apply(p)
        self.wall_stat.setText(
            f"已应用：{os.path.basename(p)}（Windows 实际设置生效）"
            if ok else f"已选择：{os.path.basename(p)}（非 Windows 仅预览，不修改桌面）")
        toast_like(self, "已应用壁纸" if ok else "非 Windows 平台不实际设置壁纸")

    def _apply_wallpaper_selected(self) -> None:
        it = self.wall_list.currentItem()
        if it is None:
            QMessageBox.information(self, "壁纸", "请先在列表中双击选择一张壁纸。")
            return
        self._apply_wallpaper_item(it)

    def _toggle_wall_rotate(self, on: bool) -> None:
        self.cfg.set_nested("wallpaper", "rotate", on)
        self.cfg.set_nested("wallpaper", "interval", int(self.wall_interval_sp.value()))
        if on:
            self.wall_mgr.start_rotation(
                float(self.wall_interval_sp.value()),
                on_change=self.wallChanged.emit)   # 信号发射线程安全，UI 更新在主线程
            self.wall_stat.setText(f"定时轮播已开启，每 {self.wall_interval_sp.value()} 秒切换一张。")
        else:
            self.wall_mgr.stop_rotation()
            self.wall_stat.setText("定时轮播已关闭。")

    def _load_wallpaper_settings(self) -> None:
        wp = self.cfg.get("wallpaper") or {}
        d = wp.get("dir") or ""
        if d and os.path.isdir(d):
            self.wall_mgr.directory = d
        self.wall_dir_label.setText(self.wall_mgr.directory)
        self.wall_interval_sp.setValue(int(wp.get("interval", 600)))
        self._reload_wall_list()
        rotate = bool(wp.get("rotate"))
        self.wall_rotate_cb.setChecked(rotate)
        if rotate:
            self.wall_mgr.start_rotation(
                float(self.wall_interval_sp.value()),
                on_change=self.wallChanged.emit)

    def _build_shutdown_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)

        card = QWidget()
        cv = QVBoxLayout(card)
        cv.addWidget(QLabel("定时操作（Windows 生效）："))
        row = QHBoxLayout()
        row.addWidget(QLabel("操作"))
        self.sd_action_cb = QComboBox()
        for k, v in SHUTDOWN_ACTIONS.items():
            self.sd_action_cb.addItem(v, k)
        row.addWidget(self.sd_action_cb, 1)
        cv.addLayout(row)

        self.sd_mode_cb = QComboBox()
        self.sd_mode_cb.addItem("倒计时（分钟）", "countdown")
        self.sd_mode_cb.addItem("指定时间（HH:MM）", "at")
        self.sd_mode_cb.currentIndexChanged.connect(self._sd_mode_changed)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("模式"))
        row2.addWidget(self.sd_mode_cb, 1)
        cv.addLayout(row2)

        self.sd_minutes_sp = QSpinBox()
        self.sd_minutes_sp.setRange(1, 1440)
        self.sd_minutes_sp.setValue(30)
        self.sd_minutes_sp.setSuffix(" 分钟")
        self.sd_time_edit = QLineEdit("22:00")
        self.sd_time_edit.setEnabled(False)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("时间"))
        row3.addWidget(self.sd_minutes_sp, 1)
        row3.addWidget(self.sd_time_edit, 1)
        cv.addLayout(row3)
        root.addWidget(card)

        ops = QHBoxLayout()
        self.sd_start_btn = QPushButton("开始计时")
        self.sd_start_btn.clicked.connect(self._sd_start)
        ops.addWidget(self.sd_start_btn)
        self.sd_cancel_btn = QPushButton("取消已排定")
        self.sd_cancel_btn.clicked.connect(self._sd_cancel)
        ops.addWidget(self.sd_cancel_btn)
        ops.addStretch(1)
        root.addLayout(ops)

        self.sd_remain = QLabel("剩余时间：--:--:--")
        self.sd_remain.setStyleSheet("font-size:22px;font-weight:600;color:#1e56e0;padding:6px 0;")
        root.addWidget(self.sd_remain)
        self.sd_stat = QLabel("未排定。选择操作与时间后点「开始计时」；倒计时结束自动执行。")
        self.sd_stat.setStyleSheet("color:#888;")
        root.addWidget(self.sd_stat)
        root.addStretch(1)

        self.sd_countdown: Optional[Countdown] = None
        self._sd_deadline = 0.0
        self._sd_action: Optional[str] = None
        self.sd_timer = QTimer(self)
        self.sd_timer.setInterval(1000)
        self.sd_timer.timeout.connect(self._sd_tick)
        return w

    def _sd_mode_changed(self) -> None:
        is_at = self.sd_mode_cb.currentData() == "at"
        self.sd_time_edit.setEnabled(is_at)
        self.sd_minutes_sp.setEnabled(not is_at)

    def _sd_start(self) -> None:
        if not shutdown_supported():
            QMessageBox.information(self, "定时关机", "该功能仅 Windows 生效（非 Windows 仅演示界面）。")
            return
        if self.sd_countdown and not self.sd_countdown.finished:
            toast_like(self, "已有排定任务，请先取消。")
            return
        import datetime as _dt
        action = self.sd_action_cb.currentData()
        if self.sd_mode_cb.currentData() == "countdown":
            secs = self.sd_minutes_sp.value() * 60
        else:
            try:
                hh, mm = (int(x) for x in self.sd_time_edit.text().strip().split(":"))
                now = _dt.datetime.now()
                target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if target <= now:
                    target += _dt.timedelta(days=1)
                secs = int((target - now).total_seconds())
            except (ValueError, AttributeError):
                QMessageBox.warning(self, "定时关机", "时间格式应为 HH:MM（如 22:00）。")
                return
        self.sd_countdown = Countdown(secs)
        self._sd_deadline = time.monotonic() + secs
        self._sd_action = action
        self.sd_timer.start()
        if action == "sleep":
            # shutdown.exe 无法排定睡眠：由助手在倒计时结束时执行（需保持助手运行）
            self._sd_render_stat("已排定「睡眠」，%d 分钟后由助手执行（请保持助手运行）。" % (secs // 60))
        elif shutdown_supported():
            ok = shutdown_execute(action, secs)
            note = "（系统已排定，助手关闭后仍会执行）" if ok else "（系统排定失败，请重试）"
            self._sd_render_stat("已排定「%s」%s%s" % (
                SHUTDOWN_ACTIONS[action],
                "至指定时刻" if self.sd_mode_cb.currentData() == "at" else f"{secs//60} 分钟后",
                note))
        else:
            self._sd_render_stat("已排定「%s」（仅倒计时演示，非 Windows 不实际执行）" % SHUTDOWN_ACTIONS[action])
        toast_like(self, "已排定，倒计时开始")

    def _sd_tick(self) -> None:
        if self.sd_countdown is None:
            self.sd_timer.stop()
            return
        # 以截止时间计算剩余，避免 QTimer 累积漂移
        remaining = int(self._sd_deadline - time.monotonic())
        if remaining <= 0:
            self.sd_timer.stop()
            action = self._sd_action
            self.sd_countdown = None
            if shutdown_supported() and action == "sleep":
                shutdown_execute("sleep", 0)
            self.sd_stat.setText("倒计时结束，系统将立即执行「%s」。" % SHUTDOWN_ACTIONS[action])
            self.sd_remain.setText("剩余时间：--:--:--")
            return
        self.sd_remain.setText("剩余时间："
                               f"{remaining // 3600:02d}:{remaining % 3600 // 60:02d}:{remaining % 60:02d}")

    def _sd_cancel(self) -> None:
        self.sd_timer.stop()
        if shutdown_supported() and self._sd_action and self._sd_action != "sleep":
            shutdown_cancel()
        self.sd_countdown = None
        self._sd_action = None
        self.sd_remain.setText("剩余时间：--:--:--")
        self.sd_stat.setText("已取消排定任务。")
        toast_like(self, "已取消")

    def _sd_render_stat(self, txt: str) -> None:
        self.sd_stat.setText(txt)

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel("桌面小组件："))
        self.wg_panel_cb = QCheckBox("侧边面板（360 风格统一入口）")
        self.wg_ball_cb = QCheckBox("悬浮球（CPU 占用）")
        self.wg_clock_cb = QCheckBox("时钟（农历 · 可大字体）")
        self.wg_weather_cb = QCheckBox("天气")
        self.wg_monitor_cb = QCheckBox("系统监控")
        self.wg_shelf_cb = QCheckBox("收纳盒（拖入文件自动归类）")
        self.wg_todo_cb = QCheckBox("事项清单（待办事项）")
        for cb in (self.wg_panel_cb, self.wg_ball_cb, self.wg_clock_cb,
                   self.wg_weather_cb, self.wg_monitor_cb, self.wg_shelf_cb,
                   self.wg_todo_cb):
            root.addWidget(cb)

        row = QHBoxLayout()
        row.addWidget(QLabel("天气城市："))
        self.city_input = QLineEdit()
        row.addWidget(self.city_input, 1)
        root.addLayout(row)

        self.auto_start_cb = QCheckBox("开机自动启动")
        root.addWidget(self.auto_start_cb)

        save_btn = QPushButton("保存设置")
        save_btn.setStyleSheet("font-weight:bold;padding:6px 18px;")
        save_btn.clicked.connect(self._save_settings)
        root.addWidget(save_btn)
        root.addStretch(1)
        return w

    def _load_settings(self) -> None:
        wg = self.cfg.get("widgets")
        self.wg_panel_cb.setChecked(wg.get("panel", True))
        self.wg_ball_cb.setChecked(wg.get("ball", True))
        self.wg_clock_cb.setChecked(wg.get("clock", True))
        self.wg_weather_cb.setChecked(wg.get("weather", True))
        self.wg_monitor_cb.setChecked(wg.get("monitor", True))
        self.wg_shelf_cb.setChecked(wg.get("shelf", True))
        self.wg_todo_cb.setChecked(wg.get("todo", True))
        self.city_input.setText(self.cfg.get("weather_city", "石家庄"))
        self.auto_start_cb.setChecked(bool(self.cfg.get("auto_start", False)))
        self.watch_cb.setChecked(bool(self.cfg.get("auto_watch", False)))
        self.dry_cb.setChecked(bool(self.cfg.get("dry_run", True)))

    def _save_settings(self) -> None:
        for key, cb in (("panel", self.wg_panel_cb), ("ball", self.wg_ball_cb),
                        ("clock", self.wg_clock_cb), ("weather", self.wg_weather_cb),
                        ("monitor", self.wg_monitor_cb), ("shelf", self.wg_shelf_cb),
                        ("todo", self.wg_todo_cb)):
            self.cfg.set_nested("widgets", key, cb.isChecked())
        self.cfg.set("weather_city", self.city_input.text().strip() or "石家庄")
        self.cfg.set("auto_start", self.auto_start_cb.isChecked())
        try:
            set_auto_start(self.auto_start_cb.isChecked())
        except Exception as e:
            self._append_log(f"设置开机自启失败：{e}")
        self.widgetPrefsChanged.emit()
        QMessageBox.information(self, "完成", "设置已保存。")

    def scan_organize(self) -> None:
        self.organizer.desktop_dir = self.desktop_dir
        items = self.organizer.plan()
        pending = [it for it in items if it.dest is not None]
        self.org_table.setRowCount(0)
        for it in items:
            r = self.org_table.rowCount()
            self.org_table.insertRow(r)
            self.org_table.setItem(r, 0, QTableWidgetItem(it.name))
            self.org_table.setItem(r, 1, QTableWidgetItem(it.category or "未分类"))
            ext = os.path.splitext(it.name)[1].lower() or "-"
            self.org_table.setItem(r, 2, QTableWidgetItem(ext))
            self.org_table.setItem(r, 3, QTableWidgetItem(
                os.path.relpath(os.path.dirname(it.dest), self.desktop_dir) if it.dest else "-"))
            self.org_table.setItem(r, 4, QTableWidgetItem("待整理" if it.dest else "跳过"))
        self.org_stat.setText(
            f"共 {len(items)} 个文件，其中 {len(pending)} 个将被整理到分类文件夹。")

    def _organize(self) -> None:
        if not self.dry_cb.isChecked() and self.organizer.has_undo():
            ret = QMessageBox.question(
                self, "确认", "已存在一次未撤销的整理记录，继续会叠加记录。是否继续？")
            if ret != QMessageBox.StandardButton.Yes:
                return
        dry = bool(self.dry_cb.isChecked())
        ok, fail = self.organizer.run(dry_run=dry)
        self.scan_organize()
        QMessageBox.information(self, "完成", f"{'预览' if dry else '实际整理'}：成功 {ok}，失败 {fail}。")

    def _undo(self) -> None:
        if not self.organizer.has_undo():
            QMessageBox.information(self, "提示", "没有可撤销的整理记录。")
            return
        ok, fail = self.organizer.undo()
        self.scan_organize()
        QMessageBox.information(self, "完成", f"撤销完成：成功 {ok}，失败 {fail}。")

    def _toggle_watch(self, on: bool) -> None:
        self.cfg.set("auto_watch", on)
        self._append_log(("已开启" if on else "已关闭") + "桌面监听自动整理。")

    def _toggle_dry(self, on: bool) -> None:
        self.cfg.set("dry_run", on)

    def _choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择要整理的目录", self.desktop_dir)
        if d:
            self.desktop_dir = d
            self.cfg.set("desktop_dir", d)
            self.dir_label.setText(d)
            self.scan_organize()

    def _edit_rules(self) -> None:
        if RuleDialog(self.rules, self).exec():
            self.scan_organize()

    def _open_desktop(self) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(self.desktop_dir)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", self.desktop_dir])
        except Exception as e:
            self._append_log(f"打开目录失败：{e}")

    def _append_log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def _accelerate(self) -> None:
        if self._accel_thread and self._accel_thread.isRunning():
            toast_like(self, "加速正在进行中，请稍候。")
            return
        self.cfg.set_nested("accelerate", "clean_temp", self.acc_temp_cb.isChecked())
        self.cfg.set_nested("accelerate", "clean_memory", self.acc_mem_cb.isChecked())
        self.cfg.set_nested("accelerate", "clear_recycle", self.acc_rc_cb.isChecked())
        self.acc_progress.setText("正在加速…")
        self._accel_run_btn.setEnabled(False)
        self._accel_thread = _AccelThread(self.cfg)
        self._accel_thread.progress.connect(self.acc_progress.setText)
        self._accel_thread.done.connect(self._on_accel_done)
        self._accel_thread.finished.connect(self._accel_thread.deleteLater)
        self._accel_thread.start()

    def _on_accel_done(self, result) -> None:
        self._accel_run_btn.setEnabled(True)
        if isinstance(result, Exception):
            self.acc_progress.setText(f"加速失败：{result}")
            return
        lines = [
            f"清理临时文件 {result.temp_files} 个，释放约 {result.temp_mb:.1f} MB，跳过 {result.skipped} 个占用文件。",
            "已清空回收站。" if result.recycled else "",
            "已请求系统回收内存。" if result.memory_trimmed else "（内存清理非 Windows 环境已跳过）",
        ]
        if result.errors:
            lines.append("；".join(result.errors))
        self.acc_progress.setText("\n".join(l for l in lines if l))
        toast_like(self, "一键加速完成")

    def _refresh_recycle(self) -> None:
        info = recycle_info()
        self.rc_info.setText(
            f"回收站：{info['item_count']} 个项目，占用 {human_bytes(info['bytes'])}。")

    def _empty_recycle(self) -> None:
        ret = QMessageBox.question(self, "确认", "确定清空回收站？此操作不可恢复。")
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            empty_recycle_bin(1)
            QMessageBox.information(self, "完成", "回收站已清空。")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"清空回收站失败：{e}")
        self._refresh_recycle()

    def _load_apps(self) -> None:
        if self._apps_thread and self._apps_thread.isRunning():
            return
        self.app_table.setRowCount(0)
        self.app_table.insertRow(0)
        self.app_table.setItem(0, 0, QTableWidgetItem("正在读取已安装软件列表…"))
        self._apps_thread = _AppsThread()
        self._apps_thread.done.connect(self._on_apps_loaded)
        self._apps_thread.finished.connect(self._apps_thread.deleteLater)
        self._apps_thread.start()

    def _on_apps_loaded(self, apps: list) -> None:
        self.apps = apps
        self.app_table.setRowCount(0)
        for a in apps:
            r = self.app_table.rowCount()
            self.app_table.insertRow(r)
            self.app_table.setItem(r, 0, QTableWidgetItem(a.name))
            self.app_table.setItem(r, 1, QTableWidgetItem(a.display_version))
            self.app_table.setItem(r, 2, QTableWidgetItem(a.publisher))
        self._apps_count = len(apps)

    def _selected_app(self):
        r = self.app_table.currentRow()
        if 0 <= r < len(getattr(self, "apps", [])):
            return self.apps[r]
        return None

    def _uninstall_selected(self) -> None:
        a = self._selected_app()
        if not a:
            QMessageBox.information(self, "提示", "请先选中一个软件。")
            return
        if not a.uninstall_string:
            QMessageBox.information(self, "提示", "该软件未提供卸载命令（可能是系统组件）。")
            return
        QMessageBox.information(self, "即将卸载",
                                f"将调用 {a.name} 的卸载程序，请按卸载器提示操作。")
        if not uninstall_app(a):
            QMessageBox.warning(self, "失败", "无法启动卸载程序。")

    def _open_app_location(self) -> None:
        a = self._selected_app()
        if not a:
            QMessageBox.information(self, "提示", "请先选中一个软件。")
            return
        if not open_app_location(a):
            QMessageBox.information(self, "提示", "该软件未记录安装目录。")

    def _init_fast_search(self) -> None:
        self.fast_index = FastIndex()
        self.everything = EverythingBackend()
        self._everything_ok = False
        self._idx_thread = None
        self._everything_check = None
        st = self.fast_index.stats()
        self._index_count = st["count"]
        self._render_idx_stat(st)
        if st["count"] == 0:
            self._append_log("首次使用，正在后台建立全盘文件索引…")
            self._rebuild_index(auto=True)

    def _render_idx_stat(self, st: dict = None) -> None:
        st = st or self.fast_index.stats()
        if st["count"] > 0:
            mode = "FTS5 毫秒检索" if st["fts"] else "LIKE 检索"
            self.idx_stat.setText(
                f"索引状态：{st['count']:,} 个文件 · 索引 {st['size_mb']} MB · "
                f"上次重建 {st['built_at'] or '—'} · 模式：{mode}")
        else:
            self.idx_stat.setText("索引状态：尚未建立索引（正在后台建立或点击「重建索引」）。")

    def _rebuild_index(self, auto: bool = False) -> None:
        if self._idx_thread and self._idx_thread.isRunning():
            self._append_log("索引重建已在进行中。")
            return
        self.idx_progress.setText("正在重建索引…（首次约需数分钟，后台进行不影响使用）" if auto else "正在重建索引…")
        self._idx_thread = _IndexThread(self.fast_index, index_roots())
        self._idx_thread.progress.connect(
            lambda c: self.idx_progress.setText(f"已扫描 {c:,} 个文件…"))
        self._idx_thread.done.connect(self._on_index_done)
        self._idx_thread.error.connect(
            lambda e: (self.idx_progress.setText(f"索引失败：{e}"), self._append_log(f"索引失败：{e}")))
        self._idx_thread.finished.connect(self._idx_thread.deleteLater)
        self._idx_thread.start()

    def _refresh_index(self) -> None:
        self._append_log("后台刷新：重建全盘索引…")
        self._rebuild_index()

    def _on_index_done(self, count: int, msg: str) -> None:
        self.idx_progress.setText("")
        self._append_log(msg)
        if count > 0:
            self._index_count = self.fast_index.stats()["count"]
        self._render_idx_stat()
        if count > 0:
            self._append_log("现在可以在「全局搜索」页输入关键字秒级搜索。")

    def _on_everything_toggle(self, on: bool) -> None:
        if on:
            self._append_log("正在检测本机 Everything HTTP 服务…")
            self._everything_check = _EverythingCheck(self.everything)
            self._everything_check.result.connect(self._on_everything_check)
            self._everything_check.start()
        else:
            self._everything_ok = False

    def _on_everything_check(self, ok: bool) -> None:
        self._everything_ok = ok
        if ok:
            self._append_log("已连接 Everything（127.0.0.1:80），搜索将优先走 Everything。")
        else:
            self._append_log("未检测到 Everything HTTP 服务，将使用内置 FTS5 索引。")
            self.everything_cb.blockSignals(True)
            self.everything_cb.setChecked(False)
            self.everything_cb.blockSignals(False)

    def _do_search(self) -> None:
        keyword = self.search_input.text().strip()
        if not keyword:
            self.search_table.setRowCount(0)
            self.search_progress.setText("输入关键字开始搜索。")
            return
        if self.everything_cb.isChecked() and self._everything_ok:
            if self._everything_search_thread and self._everything_search_thread.isRunning():
                return
            self.search_progress.setText("Everything 实时搜索中…")
            self._everything_search_thread = _EverythingSearchThread(self.everything, keyword)
            self._everything_search_thread.done.connect(self._on_everything_search_done)
            self._everything_search_thread.finished.connect(
                self._everything_search_thread.deleteLater)
            self._everything_search_thread.start()
            return
        if getattr(self, "_index_count", 0) > 0:
            res = self.fast_index.search(keyword, 200)
            self._show_results(res, "内置索引检索")
            return
        if self._search_thread and self._search_thread.isRunning():
            return
        self.search_table.setRowCount(0)
        self.search_progress.setText("索引未就绪，使用目录直搜（较慢）…")
        self._search_thread = _SearchThread(keyword, _default_roots(), 200)
        self._search_thread.progress.connect(lambda m: self.search_progress.setText(m))
        self._search_thread.done.connect(self._on_search_done)
        self._search_thread.finished.connect(self._search_thread.deleteLater)
        self._search_thread.start()

    def _on_everything_search_done(self, results: list) -> None:
        self._show_results(results, "Everything 实时搜索")

    def _show_results(self, results: list, mode: str) -> None:
        self.search_table.setRowCount(0)
        for r in results:
            row = self.search_table.rowCount()
            self.search_table.insertRow(row)
            self.search_table.setItem(row, 0, QTableWidgetItem(r["path"]))
            size = r.get("size")
            self.search_table.setItem(row, 1, QTableWidgetItem(
                human_bytes(size) if size else "-"))
        self.search_progress.setText(
            f"{mode}：找到 {len(results)} 个结果（最多显示 200），双击定位打开。")

    def _stop_search(self) -> None:
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.cancel()
            self.search_progress.setText("已停止搜索。")

    def _on_search_done(self, results) -> None:
        rows = [{"path": p, "size": None} for p in results]
        self._show_results(rows, "目录直搜")

    def _open_search_item_btn(self) -> None:
        r = self.search_table.currentRow()
        if r >= 0:
            item = self.search_table.item(r, 0)
            if item:
                self._open_path(item.text())

    def _open_search_item(self, row, col) -> None:
        item = self.search_table.item(row, 0)
        if item:
            self._open_path(item.text())

    @staticmethod
    def _open_path(path: str) -> None:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass
