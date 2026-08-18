def academic_year_context(request):
    """
    Exposes the contextual academic year and list of available years to all templates.
    """
    return {
        'current_academic_year': getattr(request, 'academic_year', None),
        'available_academic_years': getattr(request, 'available_academic_years', []),
    }

def calendar_preference_context(request):
    from apps.academics.middleware import get_current_calendar_preference
    return {
        'calendar_preference': get_current_calendar_preference() or 'ETHIOPIAN'
    }
