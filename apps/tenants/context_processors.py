def tenant_context(request):
    school = getattr(request, 'school', None)
    if not school and hasattr(request, 'user') and request.user.is_authenticated and hasattr(request.user, 'school'):
        school = request.user.school

    session_pref = request.session.get('calendar_preference') if hasattr(request, 'session') else None
    if session_pref in ['ETHIOPIAN', 'GREGORIAN']:
        active_pref = session_pref
    elif school and hasattr(school, 'calendar_preference'):
        active_pref = school.calendar_preference
    else:
        active_pref = 'ETHIOPIAN'

    return {
        'active_school': school,
        'calendar_preference': active_pref,
        'active_calendar_pref': active_pref,
    }
