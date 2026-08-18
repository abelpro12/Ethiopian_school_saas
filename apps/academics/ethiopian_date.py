"""
Ethiopian Calendar Conversion & Utility Module
Provides bidirectional accurate conversion between Gregorian (GC) and Ethiopian (EC) calendars,
plus school-aware date formatting.
"""
import datetime

ETHIOPIAN_MONTHS = [
    "", "Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit",
    "Megabit", "Miazia", "Ginbot", "Sene", "Hamle", "Nehase", "Pagume"
]

ETHIOPIAN_MONTHS_AMHARIC = [
    "", "መስከረም", "ጥቅምት", "ህዳር", "ታህሳስ", "ጥር", "የካቲት",
    "መጋቢት", "ሚያዝያ", "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"
]


def gregorian_to_ethiopian(date_obj):
    """
    Converts a datetime.date or datetime.datetime object to (eth_year, eth_month, eth_day).
    Accurately maps Gregorian dates (e.g. Sept 11, 2024 G.C. -> Meskerem 01, 2017 E.C.).
    """
    if date_obj is None:
        return None
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.date.fromisoformat(date_obj)
        except ValueError:
            return None
    if isinstance(date_obj, datetime.datetime):
        date_obj = date_obj.date()
    if not isinstance(date_obj, datetime.date):
        return None

    # Fliegel-Van Flandern algorithm
    a = (14 - date_obj.month) // 12
    y = date_obj.year + 4800 - a
    m = date_obj.month + 12 * a - 3
    jdn = date_obj.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045

    # JDN to Ethiopian
    days_elapsed = jdn - 1724221
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

    eth_year = cycles * 4 + rem_years + 1
    eth_month = min(13, day_in_year // 30 + 1)
    eth_day = (day_in_year % 30) + 1

    return eth_year, eth_month, eth_day


def ethiopian_to_gregorian(eth_year, eth_month, eth_day):
    """
    Converts (eth_year, eth_month, eth_day) to a Gregorian datetime.date object.
    """
    try:
        eth_year = int(eth_year)
        eth_month = int(eth_month)
        eth_day = int(eth_day)
    except (ValueError, TypeError):
        return None

    y_elapsed = eth_year - 1
    cycles = y_elapsed // 4
    rem_years = y_elapsed % 4
    
    days = cycles * 1461
    if rem_years == 1:
        days += 365
    elif rem_years == 2:
        days += 730
    elif rem_years == 3:
        days += 1096

    days += (eth_month - 1) * 30 + (eth_day - 1)
    jdn = 1724221 + days

    f = jdn + 1401 + (((4 * jdn + 274274) // 146097) * 3) // 4 - 38
    e = 4 * f + 3
    g = (e % 1461) // 4
    h = 5 * g + 2
    day = (h % 153) // 5 + 1
    month = ((h // 153 + 2) % 12) + 1
    year = (e // 1461) - 4716 + (12 + 2 - month) // 12

    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def format_ethiopian_date(date_obj, amharic=False, include_year=True):
    """
    Formats a date object into a human readable Ethiopian date string.
    Example: 'Meskerem 1, 2017 E.C.' or 'መስከረም 1, 2017 ዓ.ም.'
    """
    res = gregorian_to_ethiopian(date_obj)
    if not res:
        return ""
    ey, em, ed = res
    months = ETHIOPIAN_MONTHS_AMHARIC if amharic else ETHIOPIAN_MONTHS
    m_name = months[em] if 1 <= em <= 13 else str(em)

    if amharic:
        return f"{m_name} {ed}, {ey} ዓ.ም." if include_year else f"{m_name} {ed}"
    else:
        return f"{m_name} {ed}, {ey} E.C." if include_year else f"{m_name} {ed}"


def format_school_date(date_obj, school=None, amharic=False):
    """
    Formats a date based on the school's calendar preference.
    If preference is 'ETHIOPIAN', returns Ethiopian formatted date (e.g. 'Meskerem 1, 2017 E.C.').
    If preference is 'GREGORIAN', returns standard Gregorian formatted date (e.g. 'Sep 12, 2023 G.C.').
    """
    if date_obj is None:
        return ""
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.date.fromisoformat(date_obj)
        except ValueError:
            return date_obj

    pref = 'ETHIOPIAN'
    try:
        from apps.academics.middleware import get_current_calendar_preference
        global_pref = get_current_calendar_preference()
        if global_pref:
            pref = global_pref
        elif school and hasattr(school, 'calendar_preference'):
            pref = school.calendar_preference
    except Exception:
        if school and hasattr(school, 'calendar_preference'):
            pref = school.calendar_preference

    if pref == 'ETHIOPIAN':
        return format_ethiopian_date(date_obj, amharic=amharic)
    else:
        return date_obj.strftime("%b %d, %Y G.C.")


def get_attendance_calendar_context(selected_date, school, section, current_ay=None, calendar_preference=None, record_model=None):
    """
    Generates a full calendar navigation context for attendance views.
    Supports both ETHIOPIAN (E.C.) and GREGORIAN (G.C.) month navigation & day tiles,
    bounded strictly by the active Academic Year if available.
    """
    from apps.attendance.models import AttendanceRecord
    if record_model is None:
        record_model = AttendanceRecord

    if not calendar_preference:
        try:
            from apps.academics.middleware import get_current_calendar_preference
            calendar_preference = get_current_calendar_preference()
        except Exception:
            pass

    if not calendar_preference and school and hasattr(school, 'calendar_preference'):
        calendar_preference = school.calendar_preference

    if not calendar_preference:
        calendar_preference = 'ETHIOPIAN'

    ay_start = getattr(current_ay, 'gregorian_start_date', None)
    ay_end = getattr(current_ay, 'gregorian_end_date', None)

    # Bound selected_date within active AcademicYear
    if ay_start and ay_end:
        if selected_date < ay_start:
            selected_date = ay_start
        elif selected_date > ay_end:
            selected_date = ay_end

    today = datetime.date.today()
    ey, em, ed = gregorian_to_ethiopian(selected_date)

    if calendar_preference == 'ETHIOPIAN':
        if em == 13:
            num_days = 6 if (ey % 4 == 3) else 5
        else:
            num_days = 30

        month_start_greg = ethiopian_to_gregorian(ey, em, 1)
        month_end_greg = ethiopian_to_gregorian(ey, em, num_days)

        logged_dates = set(record_model.objects.filter(
            school=school,
            section=section,
            date__gte=month_start_greg,
            date__lte=month_end_greg
        ).values_list('date', flat=True)) if school and section else set()

        month_days = []
        for d_i in range(1, num_days + 1):
            greg_d = ethiopian_to_gregorian(ey, em, d_i)
            is_within_ay = (not ay_start or not ay_end or (ay_start <= greg_d <= ay_end))
            month_days.append({
                'date': greg_d,
                'date_str': greg_d.strftime('%Y-%m-%d'),
                'day_num': d_i,
                'weekday': greg_d.strftime('%a'),
                'month_name': ETHIOPIAN_MONTHS[em],
                'is_selected': (greg_d == selected_date),
                'is_today': (greg_d == today),
                'has_attendance': (greg_d in logged_dates),
                'is_within_ay': is_within_ay,
            })

        # Previous Ethiopian Month
        if em == 1:
            prev_ey, prev_em = ey - 1, 13
        else:
            prev_ey, prev_em = ey, em - 1
        prev_month_greg = ethiopian_to_gregorian(prev_ey, prev_em, 1)

        # Next Ethiopian Month
        if em == 13:
            next_ey, next_em = ey + 1, 1
        else:
            next_ey, next_em = ey, em + 1
        next_month_greg = ethiopian_to_gregorian(next_ey, next_em, 1)

        month_label = f"{ETHIOPIAN_MONTHS[em]} {ey} E.C."

    else:
        # GREGORIAN calendar preference
        import calendar
        g_year = selected_date.year
        g_month = selected_date.month
        _, num_days = calendar.monthrange(g_year, g_month)

        month_start_greg = datetime.date(g_year, g_month, 1)
        month_end_greg = datetime.date(g_year, g_month, num_days)

        logged_dates = set(record_model.objects.filter(
            school=school,
            section=section,
            date__gte=month_start_greg,
            date__lte=month_end_greg
        ).values_list('date', flat=True)) if school and section else set()

        month_days = []
        for d_i in range(1, num_days + 1):
            greg_d = datetime.date(g_year, g_month, d_i)
            is_within_ay = (not ay_start or not ay_end or (ay_start <= greg_d <= ay_end))
            month_days.append({
                'date': greg_d,
                'date_str': greg_d.strftime('%Y-%m-%d'),
                'day_num': d_i,
                'weekday': greg_d.strftime('%a'),
                'month_name': calendar.month_name[g_month],
                'is_selected': (greg_d == selected_date),
                'is_today': (greg_d == today),
                'has_attendance': (greg_d in logged_dates),
                'is_within_ay': is_within_ay,
            })

        # Previous Gregorian Month
        if g_month == 1:
            prev_month_greg = datetime.date(g_year - 1, 12, 1)
        else:
            prev_month_greg = datetime.date(g_year, g_month - 1, 1)

        # Next Gregorian Month
        if g_month == 12:
            next_month_greg = datetime.date(g_year + 1, 1, 1)
        else:
            next_month_greg = datetime.date(g_year, g_month + 1, 1)

        month_label = f"{calendar.month_name[g_month]} {g_year} G.C."

    # Bound prev and next month by AcademicYear
    prev_month_date = prev_month_greg.strftime('%Y-%m-%d') if not ay_start or prev_month_greg >= datetime.date(ay_start.year, ay_start.month, 1) else None
    next_month_date = next_month_greg.strftime('%Y-%m-%d') if not ay_end or next_month_greg <= datetime.date(ay_end.year, ay_end.month, 1) else None

    eth_month_choices = [(i, ETHIOPIAN_MONTHS[i]) for i in range(1, 14)]

    return {
        'selected_date': selected_date,
        'calendar_preference': calendar_preference,
        'selected_eth_year': ey,
        'selected_eth_month': em,
        'selected_eth_day': ed,
        'eth_month_name': ETHIOPIAN_MONTHS[em],
        'eth_month_label': month_label,
        'eth_month_choices': eth_month_choices,
        'month_days': month_days,
        'prev_month_date': prev_month_date,
        'next_month_date': next_month_date,
        'ay_start_str': ay_start.strftime('%Y-%m-%d') if ay_start else '',
        'ay_end_str': ay_end.strftime('%Y-%m-%d') if ay_end else '',
    }
