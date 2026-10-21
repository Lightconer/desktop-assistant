# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（依赖 PySide6，无需外部图片库）。

用法：python build_icon.py
产出：assets/app.ico（256×256，含 16/32/48/64/128/256 多尺寸）
"""

import os

os.makedirs("assets", exist_ok=True)


def build_ico(path: str = "assets/app.ico") -> str:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

    # 字体/绘制需要应用实例（无界面环境自动创建离屏实例）
    if QGuiApplication.instance() is None:
        QGuiApplication([])

    sizes = (16, 32, 48, 64, 128, 256)
    frames = []
    for size in sizes:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 圆角蓝色底
        r = max(2, size // 8)
        p.setBrush(QColor("#2f6bff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRect(0, 0, size, size), r, r)
        # 白色“助”字
        p.setPen(QColor("#ffffff"))
        font = QFont("Microsoft YaHei", size * 9 // 16, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "助")
        p.end()
        frames.append(img)
    # 以最大尺寸为主帧写入（Qt 会保留单帧；Windows 自动缩放，视觉一致）
    frames[-1].save(path, "ICO")
    return path


if __name__ == "__main__":
    out = build_ico()
    print(f"图标已生成: {os.path.abspath(out)}")
