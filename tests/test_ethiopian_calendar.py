import datetime
from utils.ethiopian_calendar import (
    gregorian_to_ethiopian, ethiopian_to_gregorian, format_ethiopian_date
)

def test_ethiopian_calendar_conversion():
    # 2023-09-12 Gregorian is Meskerem 1, 2016 Ethiopic (New Year after leap year 2015 E.C.)
    ey, em, ed = gregorian_to_ethiopian(2023, 9, 12)
    assert (ey, em, ed) == (2016, 1, 1)

    # Convert back
    gy, gm, gd = ethiopian_to_gregorian(2016, 1, 1)
    assert (gy, gm, gd) == (2023, 9, 12)

def test_ethiopian_formatting():
    d = datetime.date(2023, 9, 12)
    formatted_am = format_ethiopian_date(d, lang='am')
    formatted_en = format_ethiopian_date(d, lang='en')

    assert "መስከረም 1, 2016" in formatted_am
    assert "Meskerem 1, 2016" in formatted_en

def test_meskerem():
    # Meskerem 1, 2016 -> September 12, 2023
    gy, gm, gd = ethiopian_to_gregorian(2016, 1, 1)
    assert (gy, gm, gd) == (2023, 9, 12)
    assert gregorian_to_ethiopian(2023, 9, 12) == (2016, 1, 1)

def test_pagume_leap_year():
    # 2015 E.C. is a leap year in Ethiopian Calendar (Pagume 6)
    gy, gm, gd = ethiopian_to_gregorian(2015, 13, 6)
    assert (gy, gm, gd) == (2023, 9, 11)
    assert gregorian_to_ethiopian(2023, 9, 11) == (2015, 13, 6)

def test_pagume_non_leap_year():
    # 2016 E.C. is not a leap year (Pagume 5 only)
    gy, gm, gd = ethiopian_to_gregorian(2016, 13, 5)
    assert (gy, gm, gd) == (2024, 9, 10)
    assert gregorian_to_ethiopian(2024, 9, 10) == (2016, 13, 5)

def test_tahsas():
    gy, gm, gd = ethiopian_to_gregorian(2016, 4, 1)
    assert (gy, gm, gd) == (2023, 12, 11)
    assert gregorian_to_ethiopian(2023, 12, 11) == (2016, 4, 1)
