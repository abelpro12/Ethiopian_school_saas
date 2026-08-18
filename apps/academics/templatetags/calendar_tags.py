"""
Custom template tags & filters for Dual Calendar (Ethiopian E.C. & Gregorian G.C.) support.
"""
from django import template
from apps.academics.ethiopian_date import (
    gregorian_to_ethiopian,
    format_ethiopian_date,
    format_school_date
)

register = template.Library()


@register.filter(name='ethiopian_date')
def ethiopian_date_filter(value, amharic=False):
    """
    Usage: {{ date_obj|ethiopian_date }} or {{ date_obj|ethiopian_date:True }}
    Outputs: 'Meskerem 1, 2017 E.C.' or 'መስከረም 1, 2017 ዓ.ም.'
    """
    if not value:
        return ""
    return format_ethiopian_date(value, amharic=bool(amharic))


@register.filter(name='school_date')
def school_date_filter(value, school=None):
    """
    Usage: {{ date_obj|school_date:request.school }}
    Formats date based on school's calendar preference (ETHIOPIAN vs GREGORIAN).
    """
    if not value:
        return ""
    return format_school_date(value, school=school)


@register.simple_tag
def ethiopian_year_of(value):
    """
    Usage: {% ethiopian_year_of date_obj %}
    Outputs the Ethiopian year integer.
    """
    res = gregorian_to_ethiopian(value)
    if res:
        return res[0]
    return ""


@register.filter(name='academic_year_name')
def academic_year_name_filter(academic_year, calendar_pref=None):
    """
    Usage: {{ year|academic_year_name:calendar_preference }}
    Outputs: '2017 E.C.' or '2024/2025 G.C.'
    """
    if not academic_year:
        return ""
    if hasattr(academic_year, 'formatted_name'):
        return academic_year.formatted_name(calendar_pref)
    return str(academic_year)
