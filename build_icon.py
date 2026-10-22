# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（依赖 PySide6，无需外部图片库）。

用法：python build_icon.py
产出：assets/app.ico（256×256，含 16/32/48/64/128/256 多尺寸）
"""

import os
import sys

# 兼容 CI/跨语言环境：控制台编码非 UTF-8 时强制 UTF-8，避免中文 print 崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.makedirs("assets", exist_ok=True)


def build_ico(path: str = "assets/app.ico") -> str:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

    if QGuiApplication.instance() is None:
        QGuiApplication([])

    sizes = (16, 32, 48, 64, 128, 256)
    frames = []
    for size in sizes:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = max(2, size // 8)
        p.setBrush(QColor("#2f6bff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRect(0, 0, size, size), r, r)
        p.setPen(QColor("#ffffff"))
        font = QFont("Microsoft YaHei", size * 9 // 16, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "助")
        p.end()
        frames.append(img)
    frames[-1].save(path, "ICO")
    return path


if __name__ == "__main__":
    out = build_ico()
    print(f"图标已生成: {os.path.abspath(out)}")
