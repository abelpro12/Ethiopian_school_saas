"""
Ethiopian Calendar Conversion Service
Provides accurate bidirectional conversion between Gregorian calendar dates (datetime.date)
and Ethiopic calendar dates (Year, Month 1-13, Day 1-30/6), as well as localized formatting.
"""

import datetime
from typing import Tuple, Union

ETHIOPIAN_MONTHS_AM = [
    "መስከረም", "ጥቅምት", "ሕዳር", "ታኅሣሥ", "ጥር", "የካቲት",
    "መጋቢት", "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"
]

ETHIOPIAN_MONTHS_EN = [
    "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
    "Megabit", "Miyazya", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"
]

ETHIOPIAN_JDN_ANCHOR = 1724221


def gregorian_to_ethiopian(year: int, month: int, day: int) -> Tuple[int, int, int]:
    """
    Converts a Gregorian date (year, month, day) to Ethiopic (year, month, day).
    Ethiopic months are 1-indexed (1=Meskerem, ..., 13=Pagume).
    """
    jdn = _gregorian_to_jdn(year, month, day)
    return _jdn_to_ethiopian(jdn)


def ethiopian_to_gregorian(year: int, month: int, day: int) -> Tuple[int, int, int]:
    """
    Converts an Ethiopic date (year, month 1-13, day) to Gregorian (year, month, day).
    """
    jdn = _ethiopian_to_jdn(year, month, day)
    return _jdn_to_gregorian(jdn)


def format_ethiopian_date(date_val: Union[datetime.date, Tuple[int, int, int]], lang: str = "am") -> str:
    """
    Formats a date into Ethiopic calendar text string.
    Accepts either a datetime.date object or an (e_year, e_month, e_day) tuple.
    """
    if isinstance(date_val, datetime.date):
        ey, em, ed = gregorian_to_ethiopian(date_val.year, date_val.month, date_val.day)
    else:
        ey, em, ed = date_val

    months = ETHIOPIAN_MONTHS_AM if lang.lower() == "am" else ETHIOPIAN_MONTHS_EN
    month_name = months[em - 1] if 1 <= em <= 13 else f"Month {em}"
    return f"{month_name} {ed}, {ey}"


def _gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """Fliegel-Van Flandern algorithm for Gregorian to Julian Day Number."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn


def _jdn_to_gregorian(jdn: int) -> Tuple[int, int, int]:
    """Julian Day Number to Gregorian (year, month, day)."""
    f = jdn + 1401 + (((4 * jdn + 274274) // 146097) * 3) // 4 - 38
    e = 4 * f + 3
    g = (e % 1461) // 4
    h = 5 * g + 2
    day = (h % 153) // 5 + 1
    month = ((h // 153 + 2) % 12) + 1
    year = (e // 1461) - 4716 + (12 + 2 - month) // 12
    return year, month, day


def _ethiopian_to_jdn(year: int, month: int, day: int) -> int:
    """Ethiopic date to Julian Day Number."""
    y_elapsed = year - 1
    cycles = y_elapsed // 4
    rem_years = y_elapsed % 4
    
    days = cycles * 1461
    if rem_years == 1:
        days += 365
    elif rem_years == 2:
        days += 730
    elif rem_years == 3:
        days += 1096  # Year 3 is leap year (365 + 365 + 366)

    days += (month - 1) * 30 + (day - 1)
    return ETHIOPIAN_JDN_ANCHOR + days


def _jdn_to_ethiopian(jdn: int) -> Tuple[int, int, int]:
    """Julian Day Number to Ethiopic (year, month, day)."""
    days_elapsed = jdn - ETHIOPIAN_JDN_ANCHOR
    cycles = days_elapsed // 1461
    rem_days = days_elapsed % 1461

    if rem_days < 365:
        rem_years = 0
        day_in_year = rem_days
    elif rem_days < 730:
        rem_years = 1
        day_in_year = rem_days - 365
    elif rem_days < 1096:
        rem_years = 2
        day_in_year = rem_days - 730
    else:
        rem_years = 3
        day_in_year = rem_days - 1096

    year = cycles * 4 + rem_years + 1
    month = min(13, day_in_year // 30 + 1)
    day = (day_in_year % 30) + 1

    return year, month, day
