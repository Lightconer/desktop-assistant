# -*- coding: utf-8 -*-
"""桌面助手 —— 程序入口。

运行：  python main.py
功能：  桌面整理 / 电脑加速 / 回收站 / 软件管理 / 全局搜索 / 设置
        桌面小组件（悬浮球/时钟/天气/系统监控）+ 系统托盘常驻
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    from assistant.config import AppConfig
    from assistant.ui.main_window import MainWindow
    from assistant.widgets.clock_widget import ClockWidget
    from assistant.widgets.weather_widget import WeatherWidget
    from assistant.widgets.monitor_widget import MonitorWidget
    from assistant.widgets.floating_ball import FloatingBall
    from assistant.widgets.shelf_widget import ShelfWidget
    from assistant.widgets.todo_widget import TodoWidget

    app = QApplication(sys.argv)
    app.setApplicationName("桌面助手")
    app.setQuitOnLastWindowClosed(False)

    cfg = AppConfig()
    win = MainWindow(cfg)
    win.show()

    # ---------------- 小组件管理 ----------------
    class WidgetManager:
        def __init__(self):
            self.clock = None
            self.weather = None
            self.monitor = None
            self.ball = None
            self.shelf = None
            self.todo = None

        def sync(self, weather_city: str = None) -> None:
            wg = cfg.get("widgets")
            city = weather_city or cfg.get("weather_city", "石家庄")

            def close_persist(key: str):
                """小组件点关闭 → 持久化关闭该组件并同步。"""
                return lambda _k: (cfg.set_nested("widgets", key, False),
                                   self.sync())

            # 时钟（农历 + 大字体）
            if wg.get("clock", True):
                if self.clock is None:
                    self.clock = ClockWidget(
                        big=bool(cfg.get("clock_big", False)),
                        on_big_change=lambda b: cfg.set("clock_big", b))
                    self.clock.closeRequested.connect(close_persist("clock"))
                    self.clock.show()
            else:
                if self.clock:
                    self.clock.close(); self.clock = None

            # 天气（城市变化时重建）
            if wg.get("weather", True):
                if self.weather is None or (weather_city and self.weather.city != city):
                    if self.weather:
                        self.weather.close()
                    self.weather = WeatherWidget(city)
                    self.weather.closeRequested.connect(close_persist("weather"))
                    self.weather.show()
            else:
                if self.weather:
                    self.weather.close(); self.weather = None

            # 监控
            if wg.get("monitor", True):
                if self.monitor is None:
                    self.monitor = MonitorWidget()
                    self.monitor.closeRequested.connect(close_persist("monitor"))
                    self.monitor.show()
            else:
                if self.monitor:
                    self.monitor.close(); self.monitor = None

            # 悬浮球
            if wg.get("ball", True):
                if self.ball is None:
                    self.ball = FloatingBall(menu_builder=lambda: build_ball_menu())
                    self.ball.show()
            else:
                if self.ball:
                    self.ball.close(); self.ball = None

            # 收纳盒
            if wg.get("shelf", True):
                if self.shelf is None:
                    self.shelf = ShelfWidget(win.desktop_dir, win.rules, log_cb=win._append_log)
                    self.shelf.message.connect(win._append_log)
                    self.shelf.closeRequested.connect(close_persist("shelf"))
                    self.shelf.show()
            else:
                if self.shelf:
                    self.shelf.close(); self.shelf = None

            # 事项清单
            if wg.get("todo", True):
                if self.todo is None:
                    self.todo = TodoWidget()
                    self.todo.closeRequested.connect(close_persist("todo"))
                    self.todo.show()
            else:
                if self.todo:
                    self.todo.close(); self.todo = None

        def _recreate(self) -> None:
            # 通过同步逻辑让已关闭的组件自动重建或保持关闭
            self.sync()

    def build_ball_menu() -> QMenu:
        menu = QMenu()
        for text, fn in (
            ("显示主界面", lambda: (win.showNormal(), win.raise_(), win.activateWindow())),
            ("一键整理桌面", lambda: (win.showNormal(), win.raise_(), win.activateWindow(), win._organize())),
            ("一键加速", lambda: (win.showNormal(), win.raise_(), win.activateWindow(), win._accelerate())),
            ("回收站", lambda: (win.showNormal(), win.raise_(), win.activateWindow())),
        ):
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        menu.addSeparator()
        wg = cfg.get("widgets")
        for key, label in (("clock", "时钟"), ("weather", "天气"), ("monitor", "系统监控")):
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(wg.get(key, True))
            act.triggered.connect(lambda checked, k=key: (cfg.set_nested("widgets", k, checked), mgr._recreate()))
            menu.addAction(act)
        menu.addSeparator()
        quit_act = QAction("退出", menu)
        quit_act.triggered.connect(app.quit)
        menu.addAction(quit_act)
        return menu

    mgr = WidgetManager()
    mgr.sync()
    # 设置页改动（含天气城市）后同步小组件
    win.widgetPrefsChanged.connect(lambda: mgr.sync(weather_city=cfg.get("weather_city", "石家庄")))

    # ---------------- 系统托盘 ----------------
    tray = QSystemTrayIcon(app)
    tray.setToolTip("桌面助手")
    tray.setIcon(app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon))
    tmenu = QMenu()
    for text, fn in (
        ("显示主界面", lambda: (win.showNormal(), win.raise_(), win.activateWindow())),
        ("一键整理桌面", lambda: (win.showNormal(), win.raise_(), win.activateWindow(), win._organize())),
        ("一键加速", lambda: (win.showNormal(), win.raise_(), win.activateWindow(), win._accelerate())),
    ):
        act = QAction(text, tmenu)
        act.triggered.connect(fn)
        tmenu.addAction(act)
    tmenu.addSeparator()
    quit_act = QAction("退出", tmenu)
    quit_act.triggered.connect(app.quit)
    tmenu.addAction(quit_act)
    tray.setContextMenu(tmenu)
    tray.activated.connect(
        lambda reason: (win.showNormal(), win.raise_(), win.activateWindow())
        if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
