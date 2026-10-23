# -*- coding: utf-8 -*-
"""360 桌面助手风格侧边面板：一个统一入口替代零散小组件。

从上到下：
- 标题栏（桌面助手 · 搜索 / 设置入口）
- 大时钟（时:分:秒 + 日期 + 农历干支生肖 + 今日运势，点击看详情）
- 快捷工具宫格（桌面整理 / 健康护眼 / 快捷搜索 / 定时关机 / 计算器 / 工具管理 / 截屏）
- 待办速记（回车添加，与事项清单共用 todo.json）
- 桌面文件分类速览（按分类规则分 Tab，双击打开文件，30 秒自动刷新）
"""

from __future__ import annotations

import os
import time
import zlib
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QFileInfo, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileIconProvider,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..lunar import solar_to_lunar
from ..rules import RuleManager
from .base_widget import BaseWidget

PANEL_REFRESH_MS = 30 * 1000          # 桌面文件自动刷新间隔
EYE_REST_MS = 45 * 60 * 1000          # 护眼提醒间隔（45 分钟）

FORTUNE_LEVELS = ("大吉", "中吉", "小吉", "平", "吉")
FORTUNE_TIPS = (
    "宜整理桌面，事半功倍",
    "宜早睡早起，精神百倍",
    "宜多喝水，保持专注",
    "宜完成一件拖延已久的小事",
    "宜清理旧文件，轻装上阵",
    "宜专注一件事，不贪多",
    "宜主动休息，效率更高",
)

# (动作键, 图标, 标签)
TOOLS = [
    ("organize", "🗂", "桌面整理"),
    ("eye", "👁", "健康护眼"),
    ("search", "🔍", "快捷搜索"),
    ("shutdown", "⏻", "定时关机"),
    ("calc", "🧮", "计算器"),
    ("apps", "🧰", "工具管理"),
    ("snip", "✂", "截屏"),
]

WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")

_PANEL_QSS = (
    "background-color:rgba(22,32,48,0.92);"
    "border-radius:16px;border:1px solid rgba(255,255,255,0.16);"
)
_LABEL_QSS = "color:#e8f1ff;background:transparent;"
_DIM_QSS = "color:#9db8d8;background:transparent;"


def fortune_for_date(date_key: str) -> Tuple[str, str]:
    """按日期确定性地给出「今日运势」（同一天结果相同）。"""
    seed = zlib.crc32(date_key.encode("utf-8"))
    return (FORTUNE_LEVELS[seed % len(FORTUNE_LEVELS)],
            FORTUNE_TIPS[(seed >> 3) % len(FORTUNE_TIPS)])


class SidePanel(BaseWidget):
    """360 风格桌面侧边面板。"""

    toolRequested = Signal(str)       # 请求主窗口打开某页签 / 系统工具
    organizeRequested = Signal()      # 请求执行一键整理
    message = Signal(str)             # 日志消息

    def __init__(self, desktop_dir: str, rules: RuleManager,
                 todo_path: str = "", key: str = "panel", parent=None):
        super().__init__(key, "桌面助手", parent)
        self.desktop_dir = desktop_dir
        self.rules = rules
        if not todo_path:
            base = os.path.join(os.path.expanduser("~"), ".desktop_assistant")
            os.makedirs(base, exist_ok=True)
            todo_path = os.path.join(base, "todo.json")
        self.todo_path = todo_path
        self._todo_items: List[dict] = []
        self._eye_on = False
        self._icon_provider = QFileIconProvider()

        self.setFixedSize(340, 660)
        self._build_ui()
        self._load_todo()
        self._render_todo()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self._file_timer = QTimer(self)
        self._file_timer.timeout.connect(self.refresh_files)
        self._file_timer.start(PANEL_REFRESH_MS)

        self._eye_timer = QTimer(self)
        self._eye_timer.timeout.connect(self._eye_rest_remind)

        self._tick_clock()
        self.refresh_files()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(8)

        # 标题栏
        head = QHBoxLayout()
        title = QLabel("桌面助手")
        title.setStyleSheet("color:#ffffff;font-size:15px;font-weight:bold;background:transparent;")
        head.addWidget(title)
        head.addStretch(1)
        for text, tip, key in (("🔍", "快捷搜索", "search"), ("⚙", "设置", "settings")):
            b = QPushButton(text)
            b.setFixedSize(30, 26)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{background:transparent;border:none;color:#cfe2fa;"
                            "font-size:14px;}QPushButton:hover{color:#ffffff;}")
            b.clicked.connect(lambda _=False, k=key: self.toolRequested.emit(k))
            head.addWidget(b)
        root.addLayout(head)

        # 大时钟
        self.time_label = QLabel("--:--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet(
            "color:#ffffff;font-size:40px;font-weight:bold;background:transparent;")
        root.addWidget(self.time_label)

        self.date_label = QLabel("")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(_DIM_QSS + "font-size:12px;")
        root.addWidget(self.date_label)

        fortune_row = QHBoxLayout()
        self.fortune_label = QLabel("")
        self.fortune_label.setStyleSheet("color:#ffd479;font-size:12px;background:transparent;")
        self.fortune_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fortune_label.mousePressEvent = lambda _e: self._show_fortune_detail()
        fortune_row.addWidget(self.fortune_label)
        fortune_row.addStretch(1)
        root.addLayout(fortune_row)

        # 快捷工具宫格（4 列）
        grid = QGridLayout()
        grid.setSpacing(6)
        self._tool_buttons: Dict[str, QPushButton] = {}
        for i, (act, icon, label) in enumerate(TOOLS):
            b = QPushButton(f"{icon}\n{label}")
            b.setFixedSize(74, 52)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,0.08);border:none;border-radius:9px;"
                "color:#e8f1ff;font-size:11px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.16);}")
            b.clicked.connect(lambda _=False, a=act: self._on_tool(a))
            grid.addWidget(b, i // 4, i % 4)
            self._tool_buttons[act] = b
        grid_item = QWidget()
        grid_item.setStyleSheet("background:transparent;")
        grid_item.setLayout(grid)
        root.addWidget(grid_item)

        # 待办速记
        todo_row = QHBoxLayout()
        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText("⊕ 添加待办事项，回车确认")
        self.todo_input.setStyleSheet(
            "background:rgba(255,255,255,0.10);border:none;border-radius:9px;"
            "padding:7px 10px;color:#fff;font-size:12px;")
        self.todo_input.returnPressed.connect(self._add_todo)
        todo_row.addWidget(self.todo_input, 1)
        root.addLayout(todo_row)

        self.todo_list = QListWidget()
        self.todo_list.setMaximumHeight(96)
        self.todo_list.setStyleSheet(
            "background:rgba(255,255,255,0.06);border:none;border-radius:9px;"
            "color:#eef4fb;font-size:12px;")
        self.todo_list.itemClicked.connect(self._toggle_todo)
        root.addWidget(self.todo_list)

        # 桌面文件分类速览
        self.file_tabs = QTabWidget()
        self.file_tabs.setDocumentMode(True)
        self.file_tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:rgba(255,255,255,0.05);border-radius:9px;}"
            "QTabBar::tab{background:transparent;color:#9db8d8;padding:5px 14px;font-size:12px;}"
            "QTabBar::tab:selected{color:#ffffff;border-bottom:2px solid #4f8cff;}")
        root.addWidget(self.file_tabs, 1)

        self.setStyleSheet(_PANEL_QSS)

    # ------------------------------------------------------------------ 时钟
    def _tick_clock(self) -> None:
        now = time.localtime()
        self.time_label.setText(time.strftime("%H:%M:%S", now))
        lunar = solar_to_lunar(now.tm_year, now.tm_mon, now.tm_mday)
        lunar_txt = ""
        if lunar:
            lunar_txt = f"{lunar.ganzhi_year}{lunar.zodiac}·{lunar.month_name}{lunar.day_name}"
        date_txt = (f"{now.tm_mon}月{now.tm_mday}日 星期{WEEKDAY_CN[now.tm_wday]}"
                    + (f"  {lunar_txt}" if lunar_txt else ""))
        self.date_label.setText(date_txt)
        level, _tip = fortune_for_date(time.strftime("%Y-%m-%d", now))
        self.fortune_label.setText(f"{level} · 今日运势 ›")

    def _show_fortune_detail(self) -> None:
        level, tip = fortune_for_date(time.strftime("%Y-%m-%d"))
        QMessageBox.information(self, "今日运势", f"今日运势：{level}\n{tip}")

    # ------------------------------------------------------------------ 工具
    def _on_tool(self, action: str) -> None:
        if action == "organize":
            self.organizeRequested.emit()
        elif action == "eye":
            self._toggle_eye()
        elif action in ("search", "shutdown", "apps", "settings"):
            self.toolRequested.emit(action)
        elif action == "calc":
            try:
                os.startfile("calc.exe")  # noqa: S606 Windows 计算器
            except OSError as e:
                self.message.emit(f"无法打开计算器：{e}")
        elif action == "snip":
            try:
                os.startfile("ms-screenclip:")  # noqa: S606 Windows 截图（Snip & Sketch）
            except OSError as e:
                self.message.emit(f"无法启动截屏：{e}")

    def _toggle_eye(self) -> None:
        self._eye_on = not self._eye_on
        b = self._tool_buttons["eye"]
        b.setStyleSheet(
            "QPushButton{background:" + ("#2f6bff" if self._eye_on else "rgba(255,255,255,0.08)")
            + ";border:none;border-radius:9px;color:#e8f1ff;font-size:11px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.16);}")
        if self._eye_on:
            self._eye_timer.start(EYE_REST_MS)
            self.message.emit("健康护眼已开启：每 45 分钟提醒休息。")
        else:
            self._eye_timer.stop()
            self.message.emit("健康护眼已关闭。")

    def _eye_rest_remind(self) -> None:
        QMessageBox.information(self, "健康护眼", "已连续用眼 45 分钟，建议远眺休息片刻。")

    # ------------------------------------------------------------------ 待办
    def _load_todo(self) -> None:
        import json
        if not os.path.exists(self.todo_path):
            return
        try:
            with open(self.todo_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._todo_items = [{"text": str(d.get("text", "")),
                                     "done": bool(d.get("done", False))}
                                    for d in data if d.get("text")]
        except (OSError, ValueError):
            self._todo_items = []

    def _save_todo(self) -> None:
        import json
        import tempfile
        try:
            tmp_fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self.todo_path) or ".", suffix=".tmp")
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self._todo_items, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.todo_path)
        except OSError:
            pass

    def _add_todo(self) -> None:
        text = self.todo_input.text().strip()
        if not text:
            return
        self._todo_items.append({"text": text, "done": False})
        self.todo_input.clear()
        self._save_todo()
        self._render_todo()

    def _toggle_todo(self, item: QListWidgetItem) -> None:
        idx = self.todo_list.row(item)
        if 0 <= idx < len(self._pending_index):
            real = self._pending_index[idx]
            self._todo_items[real]["done"] = True
            self._save_todo()
            self._render_todo()

    def _render_todo(self) -> None:
        self.todo_list.clear()
        self._pending_index: List[int] = []
        for i, it in enumerate(self._todo_items):
            if not it["done"]:
                self._pending_index.append(i)
                self.todo_list.addItem(QListWidgetItem(f"○ {it['text']}"))
        if not self._pending_index:
            self.todo_list.addItem(QListWidgetItem("～ 暂无待办，点上方输入框添加"))

    # ------------------------------------------------------------- 桌面速览
    def refresh_files(self) -> None:
        """扫描桌面文件，按分类规则分组展示（只读，不移动）。"""
        groups: Dict[str, List[Tuple[str, str]]] = {}
        ignore = self.rules.get_ignore_names()
        if os.path.isdir(self.desktop_dir):
            try:
                entries = sorted(os.scandir(self.desktop_dir),
                                 key=lambda e: e.name.lower())
            except OSError:
                entries = []
            for entry in entries:
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                name = entry.name
                if name.startswith(".") or name.lower() in ignore:
                    continue
                cat = self.rules.classify(name) or "未分类"
                groups.setdefault(cat, []).append((name, entry.path))
        cats = [c for c in self.rules.get_enabled_categories() if groups.get(c)]
        if groups.get("未分类"):
            cats.append("未分类")

        current = self.file_tabs.tabText(self.file_tabs.currentIndex()) \
            if self.file_tabs.count() else ""
        self.file_tabs.blockSignals(True)
        self.file_tabs.clear()
        for cat in cats:
            lw = QListWidget()
            lw.setStyleSheet("background:transparent;border:none;color:#e8f1ff;font-size:12px;")
            lw.itemDoubleClicked.connect(self._open_file_item)
            for name, path in groups[cat]:
                it = QListWidgetItem(name)
                it.setToolTip(path)
                icon = self._icon_provider.icon(QFileInfo(path))
                if not icon.isNull():
                    it.setIcon(icon)
                it.setData(Qt.ItemDataRole.UserRole, path)
                lw.addItem(it)
            self.file_tabs.addTab(lw, f"{cat} {len(groups[cat])}")
        # 恢复选中页签
        if current:
            for i in range(self.file_tabs.count()):
                if self.file_tabs.tabText(i).split(" ")[0] == current.split(" ")[0]:
                    self.file_tabs.setCurrentIndex(i)
                    break
        self.file_tabs.blockSignals(False)
        if not cats:
            empty = QListWidget()
            empty.setStyleSheet("background:transparent;border:none;color:#9db8d8;")
            empty.addItem(QListWidgetItem("桌面上暂无可分类文件"))
            self.file_tabs.addTab(empty, "空")

    def _open_file_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except Exception:  # noqa: BLE001
                self.message.emit(f"打开失败：{path}")

    # ------------------------------------------------------------------ 布局
    def dock_right(self) -> None:
        """停靠到屏幕右侧（首次显示时调用）。"""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        g = screen.availableGeometry()
        self.move(g.right() - self.width() - 6,
                  g.top() + max(24, (g.height() - self.height()) // 3))

    def _make_menu(self):
        menu = super()._make_menu()
        menu.addSeparator()
        refresh = QAction("刷新桌面文件", menu)
        refresh.triggered.connect(self.refresh_files)
        menu.addAction(refresh)
        return menu
