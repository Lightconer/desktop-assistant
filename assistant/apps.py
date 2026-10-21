# -*- coding: utf-8 -*-
"""已安装软件与启动项管理（仅 Windows，通过注册表 Uninstall 项）。"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class InstalledApp:
    name: str
    display_version: str = ""
    install_location: str = ""
    uninstall_string: str = ""
    publisher: str = ""


_REGISTER_PATHS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
]


def _read_registry(root, subkey):
    import winreg
    try:
        key = winreg.OpenKey(root, subkey)
    except OSError:
        return []
    out = []
    i = 0
    while True:
        try:
            name = winreg.EnumKey(key, i)
        except OSError:
            break
        i += 1
        try:
            sk = winreg.OpenKey(root, subkey + "\\" + name)
            values = {}
            j = 0
            while True:
                try:
                    vname, vdata, _ = winreg.EnumValue(sk, j)
                    values[vname] = vdata
                    j += 1
                except OSError:
                    break
            winreg.CloseKey(sk)
            out.append((name, values))
        except OSError:
            continue
    winreg.CloseKey(key)
    return out


def list_installed_apps() -> List[InstalledApp]:
    """枚举系统已安装软件（去重）。非 Windows 返回空。"""
    if sys.platform != "win32":
        return []
    import winreg
    apps: dict = {}
    for root, sub in ((winreg.HKEY_CURRENT_USER, _REGISTER_PATHS[0]),
                      (winreg.HKEY_LOCAL_MACHINE, _REGISTER_PATHS[0]),
                      (winreg.HKEY_LOCAL_MACHINE, _REGISTER_PATHS[1])):
        for _, values in _read_registry(root, sub):
            name = values.get("DisplayName", "")
            if not name:
                continue
            apps.setdefault(name, InstalledApp(
                name=name,
                display_version=str(values.get("DisplayVersion", "") or ""),
                install_location=str(values.get("InstallLocation", "") or ""),
                uninstall_string=str(values.get("UninstallString", "") or ""),
                publisher=str(values.get("Publisher", "") or ""),
            ))
    return sorted(apps.values(), key=lambda a: a.name.lower())


def uninstall_app(app: InstalledApp) -> bool:
    """调用官方卸载命令。返回是否成功启动。"""
    if not app.uninstall_string:
        return False
    try:
        if sys.platform == "win32":
            os.startfile(app.uninstall_string)
            return True
    except Exception:
        pass
    return False


def open_app_location(app: InstalledApp) -> bool:
    if app.install_location and os.path.isdir(app.install_location):
        try:
            if sys.platform == "win32":
                os.startfile(app.install_location)
                return True
        except Exception:
            pass
    return False


def startup_items() -> List[InstalledApp]:
    """读取 HKCU 启动项。非 Windows 返回空。"""
    if sys.platform != "win32":
        return []
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
    except OSError:
        return []
    items: List[InstalledApp] = []
    j = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(k, j)
            items.append(InstalledApp(name=name, uninstall_string=str(value)))
            j += 1
        except OSError:
            break
    winreg.CloseKey(k)
    return items


def set_auto_start(enabled: bool, app_path: Optional[str] = None) -> None:
    """设置开机自启（当前用户 Run 项）。app_path 缺省取当前进程。"""
    if sys.platform != "win32":
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    name = "DesktopAssistant"
    try:
        if enabled:
            if app_path is None:
                app_path = os.path.abspath(sys.argv[0])
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'"{app_path}"')
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
