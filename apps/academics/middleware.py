import threading
import datetime
from apps.academics.models import AcademicYear
import django.template.defaultfilters as defaultfilters
from apps.academics.ethiopian_date import gregorian_to_ethiopian, ETHIOPIAN_MONTHS

_thread_locals = threading.local()


def get_current_calendar_preference():
    return getattr(_thread_locals, 'calendar_preference', 'ETHIOPIAN')


# Smart Date Filter Patch for Django's built-in `date` filter
_original_date_filter = defaultfilters.date


def smart_calendar_date_filter(value, arg=None):
    if not value:
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        # Preserve input[type=date] values when arg == 'Y-m-d' for HTML5 datepickers
        if arg == 'Y-m-d' and not isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d')

        pref = get_current_calendar_preference()
        if pref == 'ETHIOPIAN':
            ey, em, ed = gregorian_to_ethiopian(value)
            if ey and em:
                m_name = ETHIOPIAN_MONTHS[em]
                if isinstance(value, datetime.datetime) and arg and ('H:i' in str(arg) or 'h:i' in str(arg)):
                    time_str = value.strftime('%H:%M')
                    return f"{m_name} {ed:02d}, {ey} E.C. {time_str}".strip()
                return f"{m_name} {ed:02d}, {ey} E.C."
        else:
            res = _original_date_filter(value, arg)
            if res and 'G.C.' not in str(res) and any(c.isdigit() for c in str(res)):
                return f"{res} G.C."
            return res

    return _original_date_filter(value, arg)


# Register patch globally into Django template engine
defaultfilters.date = smart_calendar_date_filter
defaultfilters.register.filters['date'] = smart_calendar_date_filter


class CalendarPreferenceMiddleware:
    """
    Sets thread-local calendar_preference for the current request.
    Enables automatic smart date and year formatting across all Django templates system-wide.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        pref = 'ETHIOPIAN'
        if hasattr(request, 'session') and request.session.get('calendar_preference'):
            pref = request.session.get('calendar_preference')
        elif hasattr(request, 'school') and request.school and hasattr(request.school, 'calendar_preference'):
            pref = request.school.calendar_preference
        
        _thread_locals.calendar_preference = pref
        request.calendar_preference = pref

        response = self.get_response(request)
        return response


class AcademicYearMiddleware:
    """
    Extracts the selected academic year from the session for Admin roles.
    For Student, Parent, and Teacher roles, strictly forces the active academic year.
    Sets request.academic_year and request.available_academic_years.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.academic_year = None
        request.available_academic_years = []

        if hasattr(request, 'school') and request.school:
            # Fetch all academic years for this school
            all_years = AcademicYear.objects.filter(school=request.school).order_by('-gregorian_start_date')
            active_year = all_years.filter(is_active=True).first() or all_years.first()

            user = getattr(request, 'user', None)
            is_admin_or_super = user and user.is_authenticated and (
                user.is_superuser or getattr(user, 'role', None) in ['SCHOOL_ADMIN', 'SUPER_ADMIN', 'PRINCIPAL', 'REGISTRAR']
            )

            if is_admin_or_super:
                if active_year:
                    available = all_years.filter(gregorian_start_date__lte=active_year.gregorian_start_date)
                else:
                    available = all_years
                
                request.available_academic_years = list(available)

                if all_years.exists():
                    selected_year_id = request.session.get('selected_academic_year_id')
                    if selected_year_id:
                        try:
                            selected_ay = AcademicYear.objects.get(id=selected_year_id, school=request.school)
                            if not active_year or selected_ay.gregorian_start_date <= active_year.gregorian_start_date:
                                request.academic_year = selected_ay
                        except AcademicYear.DoesNotExist:
                            pass
            else:
                # Student, Parent, Teacher roles are strictly locked to the Active Academic Year only
                request.available_academic_years = [active_year] if active_year else []

            # Fallback to active year if no valid session year is found
            if not request.academic_year:
                request.academic_year = active_year

        response = self.get_response(request)
        return response
