# -*- coding: utf-8 -*-
"""定时关机 / 重启 / 注销 / 睡眠模块。

- Windows：通过系统 shutdown.exe 实现关机(/s)、重启(/r)、注销(/l)、取消(/a)；
  睡眠通过 powrprof.SetSuspendState 实现。
- 非 Windows：命令构造与倒计时逻辑可用（可测试），实际执行返回 False。
"""

from __future__ import annotations

import subprocess
import sys
from typing import List, Optional

ACTIONS = {
    "shutdown": "关机",
    "restart": "重启",
    "logout": "注销",
    "sleep": "睡眠",
}

_ACTION_CMD = {
    "shutdown": "/s",
    "restart": "/r",
    "logout": "/l",
}


def supported() -> bool:
    return sys.platform == "win32"


def build_command(action: str, seconds: int) -> Optional[List[str]]:
    """构造 Windows shutdown 命令；注销不支持延时，返回立即注销命令。"""
    if action == "sleep":
        return None
    flag = _ACTION_CMD.get(action)
    if flag is None:
        return None
    cmd = ["shutdown", flag]
    if action != "logout":
        cmd += ["/t", str(int(max(0, seconds)))]
    return cmd


def cancel() -> bool:
    """取消已排定的关机/重启。无排定任务时返回 False。"""
    if not supported():
        return False
    try:
        r = subprocess.run(["shutdown", "/a"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def execute(action: str, seconds: int = 0) -> bool:
    """执行指定操作。Windows 真正执行；其他平台返回 False。"""
    if not supported():
        return False
    if action == "sleep":
        try:
            import ctypes
            return bool(ctypes.windll.powrprof.SetSuspendState(0, 0, 0))
        except Exception:
            return False
    cmd = build_command(action, seconds)
    if cmd is None:
        return False
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class Countdown:
    """倒计时逻辑（纯 Python，便于测试；UI 层用 QTimer 驱动 tick）。"""

    def __init__(self, total_sec: int) -> None:
        self.total = max(0, int(total_sec))
        self.remaining = self.total
        self.finished = False

    def tick(self, dt: int = 1) -> bool:
        """前进 dt 秒，返回是否刚好归零。"""
        if self.finished:
            return True
        self.remaining = max(0, self.remaining - int(dt))
        if self.remaining == 0:
            self.finished = True
            return True
        return False

    def format_remaining(self) -> str:
        s = self.remaining
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

    def reset(self, total_sec: int) -> None:
        self.total = max(0, int(total_sec))
        self.remaining = self.total
        self.finished = False
