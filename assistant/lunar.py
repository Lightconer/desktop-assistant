# -*- coding: utf-8 -*-
"""农历（阴历）与公历互转（1900–2100），用于时钟小组件显示农历日期。

基于经典农历数据表（每年一个 32 位整数编码：闰月、大小月），
公历锚点：1900-01-31 为农历一九〇〇年正月初一。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

MIN_YEAR = 1900
MAX_YEAR = 2100

# 每年编码：低 4 位=闰月(0 无闰)，0x10000 位=闰月 30 天，
# 其余各位(0x8000>>m)=第 m 月 30 天(0 为 29 天)
_LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x055c0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
    0x0d520,
]
assert len(_LUNAR_INFO) == MAX_YEAR - MIN_YEAR + 1

_MONTH_NAMES = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
_DAY_NAMES = ["初{}", "十{}", "廿{}", "三{}"]
_DAY_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
_STEMS = "甲乙丙丁戊己庚辛壬癸"
_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_ZODIAC = "鼠牛虎兔龙蛇马羊猴鸡狗猪"

_FESTIVALS = {
    (1, 1): "春节", (1, 15): "元宵节", (2, 2): "龙抬头",
    (5, 5): "端午节", (7, 7): "七夕节", (7, 15): "中元节",
    (8, 15): "中秋节", (9, 9): "重阳节", (12, 8): "腊八节",
    (12, 23): "北方小年", (12, 24): "南方小年",
}

_ANCHOR = datetime.date(1900, 1, 31)  # 农历 1900-01-01


@dataclass
class LunarDate:
    year: int
    month: int          # 1-12
    day: int
    is_leap: bool = False

    @property
    def month_name(self) -> str:
        return ("闰" if self.is_leap else "") + _MONTH_NAMES[self.month - 1] + "月"

    @property
    def day_name(self) -> str:
        d = self.day
        if d == 10:
            return "初十"
        if d == 20:
            return "二十"
        if d == 30:
            return "三十"
        part = (d - 1) // 10
        return _DAY_NAMES[part].format(_DAY_NUMS[d - 1 - part * 10])

    @property
    def ganzhi_year(self) -> str:
        return _STEMS[(self.year - 4) % 10] + _BRANCHES[(self.year - 4) % 12] + "年"

    @property
    def zodiac(self) -> str:
        return _ZODIAC[(self.year - 4) % 12]

    @property
    def festival(self) -> Optional[str]:
        if self.month == 12:
            # 除夕 = 腊月最后一天（廿九或三十）
            if self.day == _month_days(self.year, 12):
                return "除夕"
        return _FESTIVALS.get((self.month, self.day))

    def display(self) -> str:
        s = f"农历{self.month_name}{self.day_name}"
        f = self.festival
        if f:
            s += f" · {f}"
        return s


def _year_days(y: int) -> int:
    total = 0
    for i in range(1, 13):
        total += 30 if _LUNAR_INFO[y - MIN_YEAR] & (0x10000 >> i) else 29
    if _leap_month(y):
        total += _leap_days(y)
    return total


def _leap_month(y: int) -> int:
    return _LUNAR_INFO[y - MIN_YEAR] & 0xF


def _leap_days(y: int) -> int:
    return 30 if _LUNAR_INFO[y - MIN_YEAR] & 0x10000 else 29


def _month_days(y: int, m: int) -> int:
    return 30 if _LUNAR_INFO[y - MIN_YEAR] & (0x10000 >> m) else 29


def solar_to_lunar(year: int, month: int, day: int) -> Optional[LunarDate]:
    """公历 → 农历；超出 1900–2100 范围返回 None。"""
    if not (MIN_YEAR <= year <= MAX_YEAR):
        return None
    try:
        target = datetime.date(year, month, day)
    except ValueError:
        return None
    offset = (target - _ANCHOR).days
    if offset < 0:
        return None

    lunar_year = MIN_YEAR
    for i in range(MIN_YEAR, MAX_YEAR + 1):
        yd = _year_days(i)
        if offset < yd:
            lunar_year = i
            break
        offset -= yd
    else:
        return None

    leap = _leap_month(lunar_year)
    is_leap = False
    lunar_month = 1
    # 上界 14：允许 i == leap+1 == 13 表示闰十二月
    for i in range(1, 14):
        if leap > 0 and i == leap + 1 and not is_leap:
            if offset < _leap_days(lunar_year):
                lunar_month = leap
                is_leap = True
                break
            offset -= _leap_days(lunar_year)
            if i == 13:   # 闰十二月之后无正常月份
                lunar_month = 12
                break
        if offset < _month_days(lunar_year, i):
            lunar_month = i
            break
        offset -= _month_days(lunar_year, i)
    else:
        lunar_month = 12

    return LunarDate(lunar_year, lunar_month, offset + 1, is_leap)


def today() -> Optional[LunarDate]:
    t = datetime.date.today()
    return solar_to_lunar(t.year, t.month, t.day)
