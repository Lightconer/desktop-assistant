# -*- coding: utf-8 -*-
"""天气获取：wttr.in 免费接口，离线/失败时优雅降级。

返回结构示例：
    {"city": "石家庄", "temp": "10", "desc": "多云", "humidity": "45%"}
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Dict, Optional


def get_weather(city: str = "石家庄", timeout: float = 6.0) -> Optional[Dict[str, str]]:
    """抓取指定城市实时天气；任何失败返回 None。"""
    try:
        url = "https://wttr.in/" + urllib.parse.quote(city) + "?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cur = data["current_condition"][0]
        desc = ""
        lang = cur.get("lang_zh") or []
        if lang:
            desc = lang[0].get("value", "")
        if not desc:
            desc = cur.get("weatherDesc", [{}])[0].get("value", "")
        return {
            "city": data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city),
            "temp": cur.get("temp_C", "?"),
            "desc": desc or "未知",
            "humidity": cur.get("humidity", "?"),
            "wind": cur.get("windspeedKmph", "?"),
        }
    except Exception:
        return None
