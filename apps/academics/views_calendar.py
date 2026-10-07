import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    SchoolEvent,
    EventCategory,
    EventType,
    EventStatus,
    TargetAudience,
)
from apps.academics.calendar_service import AcademicCalendarService
from apps.academics.ethiopian_date import format_school_date, format_ethiopian_date
from apps.audit.services import AuditService


def _get_active_school(request):
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school and (request.user.is_superuser or getattr(request.user, 'role', None) == 'SUPER_ADMIN'):
        from apps.schools.models import School
        active_code = request.session.get('active_school_code', 'SEA')
        school = School.objects.filter(code=active_code).first() or School.objects.first()
    return school


def _can_manage_calendar(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR', 'ACADEMIC_DIRECTOR']:
        return True
    return False


@login_required
def school_calendar_view(request):
    """
    Main interactive Academic Calendar & Event Management dashboard.
    Supports Month, Week, Day, and Agenda/List views with automated generation,
    manual overrides, audience targeting, status tracking, and Ethiopian calendar dual-mode.
    """
    school = _get_active_school(request)
    can_manage = _can_manage_calendar(request.user)

    # Resolve academic year
    current_ay = getattr(request, 'academic_year', None)
    if not current_ay and school:
        current_ay = AcademicYear.objects.filter(school=school, is_active=True).first()
        if not current_ay:
            current_ay = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year').first()

    academic_years = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year') if school else []
    periods = AcademicPeriod.objects.filter(school=school, academic_year=current_ay).order_by('start_date') if current_ay else []

    # Handle standard POST event creation if submitted via traditional form
    if request.method == 'POST' and can_manage:
        title = request.POST.get('title', '').strip()
        event_category = request.POST.get('event_category', EventCategory.ACADEMIC)
        target_audience = request.POST.get('target_audience', TargetAudience.ALL)
        status = request.POST.get('status', EventStatus.SCHEDULED)
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date') or None
        start_time_val = request.POST.get('start_time') or None
        end_time_val = request.POST.get('end_time') or None
        location = request.POST.get('location', '').strip() or None
        description = request.POST.get('description', '').strip() or None
        period_id = request.POST.get('academic_period') or None

        if title and start_date and current_ay and school:
            period_obj = None
            if period_id:
                period_obj = AcademicPeriod.objects.filter(school=school, id=period_id).first()

            ev = SchoolEvent.objects.create(
                school=school,
                academic_year=current_ay,
                academic_period=period_obj,
                title=title,
                event_category=event_category,
                target_audience=target_audience,
                status=status,
                start_date=start_date,
                end_date=end_date,
                start_time=start_time_val,
                end_time=end_time_val,
                location=location,
                description=description,
                is_automated=False,
                is_override=False,
                is_active=True,
                created_by=request.user,
            )

            AuditService.log_action(
                school=school,
                user=request.user,
                action="CALENDAR_EVENT_CREATED",
                object_type="SchoolEvent",
                object_id=ev.id,
                details={"title": title, "category": event_category, "start_date": str(start_date)}
            )
            messages.success(request, f"Event '{title}' successfully added to the school calendar.")
        else:
            messages.error(request, "Please enter all required fields (title & start date).")
        return redirect('school_calendar')

    # Fetch upcoming events and exams for sidebar widgets
    today = timezone.now().date()
    upcoming_events = []
    upcoming_exams = []
    stats = {
        'total_events': 0,
        'upcoming_count': 0,
        'exams_count': 0,
        'holidays_count': 0,
        'automated_count': 0
    }

    if school:
        qs = SchoolEvent.objects.filter(school=school, is_active=True)
        if current_ay:
            qs = qs.filter(academic_year=current_ay)

        stats['total_events'] = qs.count()
        stats['upcoming_count'] = qs.filter(start_date__gte=today).exclude(status=EventStatus.CANCELLED).count()
        stats['exams_count'] = qs.filter(event_category=EventCategory.EXAMINATION).count()
        stats['holidays_count'] = qs.filter(event_category=EventCategory.HOLIDAY).count()
        stats['automated_count'] = qs.filter(is_automated=True).count()

        # Target audience filter for non-admin viewers (students / parents / teachers)
        user_role = getattr(request.user, 'role', '')
        if user_role == 'STUDENT':
            qs = qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.STUDENTS])
        elif user_role == 'PARENT':
            qs = qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.PARENTS])
        elif user_role == 'TEACHER':
            qs = qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.TEACHERS])

        upcoming_events = qs.filter(start_date__gte=today).exclude(status=EventStatus.CANCELLED).order_by('start_date', 'start_time')[:8]

        try:
            from apps.examinations.models import ExamSchedule
            upcoming_exams = ExamSchedule.objects.filter(
                school=school,
                exam_date__gte=today
            ).select_related('subject').order_by('exam_date')[:5]
        except Exception:
            upcoming_exams = []

    calendar_preference = getattr(school, 'calendar_preference', 'ETHIOPIAN') if school else 'ETHIOPIAN'

    return render(request, 'academics/calendar.html', {
        'current_ay': current_ay,
        'academic_years': academic_years,
        'periods': periods,
        'can_manage': can_manage,
        'upcoming_events': upcoming_events,
        'upcoming_exams': upcoming_exams,
        'stats': stats,
        'categories': EventCategory.choices,
        'statuses': EventStatus.choices,
        'audiences': TargetAudience.choices,
        'calendar_preference': calendar_preference,
        'today': today.isoformat(),
    })


@login_required
def calendar_events_json_view(request):
    """
    JSON feed endpoint for FullCalendar.
    Supports filtering by category, audience, status, and academic year.
    Dual-calendar aware with color coding by category.
    """
    school = _get_active_school(request)
    can_manage = _can_manage_calendar(request.user)

    if not school:
        return JsonResponse([], safe=False)

    ay_id = request.GET.get('academic_year_id')
    cat_filter = request.GET.get('category')
    aud_filter = request.GET.get('audience')
    stat_filter = request.GET.get('status')

    current_ay = None
    if ay_id:
        current_ay = AcademicYear.objects.filter(school=school, id=ay_id).first()
    if not current_ay:
        current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    events_payload = []

    CATEGORY_COLORS = {
        EventCategory.EXAMINATION: '#ef4444',    # Crimson red
        EventCategory.HOLIDAY: '#10b981',        # Emerald green
        EventCategory.BREAK: '#0d9488',          # Teal
        EventCategory.ACADEMIC: '#4f46e5',       # Indigo
        EventCategory.REGISTRATION: '#2563eb',   # Royal blue
        EventCategory.TRAINING: '#7c3aed',       # Violet purple
        EventCategory.MEETING: '#d97706',        # Amber
        EventCategory.CEREMONY: '#db2777',       # Rose pink
        EventCategory.EXTRACURRICULAR: '#ea580c',# Orange
        EventCategory.OTHER: '#64748b',          # Slate grey
    }

    # 1. School Events
    events_qs = SchoolEvent.objects.filter(school=school, is_active=True)
    if current_ay:
        events_qs = events_qs.filter(academic_year=current_ay)

    # Non-admin audience restriction
    user_role = getattr(request.user, 'role', '')
    if not can_manage:
        if user_role == 'STUDENT':
            events_qs = events_qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.STUDENTS])
        elif user_role == 'PARENT':
            events_qs = events_qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.PARENTS])
        elif user_role == 'TEACHER':
            events_qs = events_qs.filter(target_audience__in=[TargetAudience.ALL, TargetAudience.TEACHERS])

    if cat_filter and cat_filter != 'ALL':
        events_qs = events_qs.filter(event_category=cat_filter)
    if aud_filter and aud_filter != 'ALL':
        events_qs = events_qs.filter(target_audience=aud_filter)
    if stat_filter and stat_filter != 'ALL':
        events_qs = events_qs.filter(status=stat_filter)

    for ev in events_qs:
        base_color = CATEGORY_COLORS.get(ev.event_category, '#4f46e5')
        is_cancelled = (ev.status == EventStatus.CANCELLED)
        color = '#94a3b8' if is_cancelled else base_color

        start_str = ev.start_date.isoformat()
        if ev.start_time:
            start_str += f"T{ev.start_time.strftime('%H:%M:%S')}"

        end_str = (ev.end_date or ev.start_date).isoformat()
        if ev.end_time:
            end_str += f"T{ev.end_time.strftime('%H:%M:%S')}"
        elif ev.end_date and ev.end_date > ev.start_date:
            # FullCalendar end date for all-day events is exclusive, so add 1 day for inclusive visualization
            inclusive_end = ev.end_date + datetime.timedelta(days=1)
            end_str = inclusive_end.isoformat()

        title_prefix = ""
        if ev.event_category == EventCategory.EXAMINATION: title_prefix = "📝 "
        elif ev.event_category == EventCategory.HOLIDAY: title_prefix = "🌴 "
        elif ev.event_category == EventCategory.BREAK: title_prefix = "🏖️ "
        elif ev.event_category == EventCategory.REGISTRATION: title_prefix = "📋 "
        elif ev.event_category == EventCategory.TRAINING: title_prefix = "🧑‍🏫 "
        elif ev.event_category == EventCategory.MEETING: title_prefix = "🤝 "
        elif ev.event_category == EventCategory.CEREMONY: title_prefix = "🎉 "
        elif ev.event_category == EventCategory.ACADEMIC: title_prefix = "🎓 "

        events_payload.append({
            'id': f"ev-{ev.id}",
            'raw_id': ev.id,
            'title': f"{title_prefix}{ev.title}",
            'raw_title': ev.title,
            'start': start_str,
            'end': end_str,
            'color': color,
            'backgroundColor': color,
            'borderColor': color,
            'type': 'schoolevent',
            'category': ev.event_category,
            'category_display': ev.get_event_category_display(),
            'status': ev.status,
            'status_display': ev.get_status_display(),
            'audience': ev.target_audience,
            'audience_display': ev.get_target_audience_display(),
            'start_date': ev.start_date.isoformat(),
            'end_date': ev.end_date.isoformat() if ev.end_date else '',
            'start_time': ev.start_time.strftime('%H:%M') if ev.start_time else '',
            'end_time': ev.end_time.strftime('%H:%M') if ev.end_time else '',
            'location': ev.location or '',
            'description': ev.description or '',
            'is_automated': ev.is_automated,
            'is_override': ev.is_override,
            'ethiopian_date': ev.ethiopian_start_date,
            'academic_period_id': ev.academic_period_id or '',
            'can_manage': can_manage,
        })

    # 2. Add Examination Schedules from Exam app if category not filtered out
    if cat_filter in [None, 'ALL', EventCategory.EXAMINATION]:
        try:
            from apps.examinations.models import ExamSchedule
            exams = ExamSchedule.objects.filter(school=school).select_related('subject', 'exam_session')
            if current_ay:
                exams = exams.filter(exam_session__academic_year=current_ay)
            for ex in exams:
                ex_start = ex.exam_date.isoformat()
                if ex.start_time:
                    ex_start += f"T{ex.start_time.strftime('%H:%M:%S')}"
                ex_end = ex.exam_date.isoformat()
                if ex.end_time:
                    ex_end += f"T{ex.end_time.strftime('%H:%M:%S')}"

                events_payload.append({
                    'id': f"exam-{ex.id}",
                    'raw_id': ex.id,
                    'title': f"📝 Exam: {ex.subject.name}",
                    'raw_title': f"{ex.subject.name} Examination",
                    'start': ex_start,
                    'end': ex_end,
                    'color': '#ef4444',
                    'backgroundColor': '#ef4444',
                    'borderColor': '#dc2626',
                    'type': 'exam_schedule',
                    'category': EventCategory.EXAMINATION,
                    'category_display': 'Examination & Assessment',
                    'status': EventStatus.SCHEDULED,
                    'status_display': 'Scheduled',
                    'audience': TargetAudience.ALL,
                    'audience_display': 'All Users',
                    'start_date': ex.exam_date.isoformat(),
                    'end_date': ex.exam_date.isoformat(),
                    'start_time': ex.start_time.strftime('%H:%M') if ex.start_time else '',
                    'end_time': ex.end_time.strftime('%H:%M') if ex.end_time else '',
                    'location': getattr(ex, 'room', '') or 'Assigned Hall',
                    'description': f"Formal examination for {ex.subject.name}.",
                    'is_automated': True,
                    'is_override': False,
                    'ethiopian_date': format_ethiopian_date(ex.exam_date),
                    'can_manage': False,
                })
        except Exception:
            pass

    return JsonResponse(events_payload, safe=False)


@login_required
@require_POST
def create_calendar_event_ajax(request):
    """AJAX endpoint to create a new calendar event."""
    if not _can_manage_calendar(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    school = _get_active_school(request)
    if not school:
        return JsonResponse({'success': False, 'error': 'School context missing.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    title = data.get('title', '').strip()
    start_date = data.get('start_date')
    if not title or not start_date:
        return JsonResponse({'success': False, 'error': 'Title and Start Date are required.'}, status=400)

    ay_id = data.get('academic_year_id')
    academic_year = None
    if ay_id:
        academic_year = AcademicYear.objects.filter(school=school, id=ay_id).first()
    if not academic_year:
        academic_year = AcademicYear.objects.filter(school=school, is_active=True).first()
    if not academic_year:
        return JsonResponse({'success': False, 'error': 'No active academic year found.'}, status=400)

    period_id = data.get('academic_period_id')
    academic_period = None
    if period_id:
        academic_period = AcademicPeriod.objects.filter(school=school, id=period_id).first()

    ev = SchoolEvent.objects.create(
        school=school,
        academic_year=academic_year,
        academic_period=academic_period,
        title=title,
        event_category=data.get('event_category', EventCategory.ACADEMIC),
        target_audience=data.get('target_audience', TargetAudience.ALL),
        status=data.get('status', EventStatus.SCHEDULED),
        start_date=start_date,
        end_date=data.get('end_date') or None,
        start_time=data.get('start_time') or None,
        end_time=data.get('end_time') or None,
        location=data.get('location', '').strip() or None,
        description=data.get('description', '').strip() or None,
        is_automated=False,
        is_override=False,
        is_active=True,
        created_by=request.user
    )

    AuditService.log_action(
        school=school,
        user=request.user,
        action="CALENDAR_EVENT_CREATED",
        object_type="SchoolEvent",
        object_id=ev.id,
        details={"title": title, "category": ev.event_category, "start_date": str(start_date)}
    )

    return JsonResponse({'success': True, 'event_id': ev.id, 'message': f"Event '{title}' created successfully."})


@login_required
@require_POST
def update_calendar_event_ajax(request, event_id):
    """AJAX endpoint to update an existing calendar event (sets is_override=True)."""
    if not _can_manage_calendar(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    school = _get_active_school(request)
    ev = get_object_or_404(SchoolEvent, id=event_id, school=school)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    title = data.get('title', '').strip()
    start_date = data.get('start_date')
    if not title or not start_date:
        return JsonResponse({'success': False, 'error': 'Title and Start Date are required.'}, status=400)

    period_id = data.get('academic_period_id')
    academic_period = None
    if period_id:
        academic_period = AcademicPeriod.objects.filter(school=school, id=period_id).first()

    ev.title = title
    ev.event_category = data.get('event_category', ev.event_category)
    ev.target_audience = data.get('target_audience', ev.target_audience)
    ev.status = data.get('status', ev.status)
    ev.start_date = start_date
    ev.end_date = data.get('end_date') or None
    ev.start_time = data.get('start_time') or None
    ev.end_time = data.get('end_time') or None
    ev.location = data.get('location', '').strip() or None
    ev.description = data.get('description', '').strip() or None
    ev.academic_period = academic_period

    # If an automated event was edited, mark as override so re-generation does not overwrite it
    if ev.is_automated:
        ev.is_override = True

    ev.save()

    AuditService.log_action(
        school=school,
        user=request.user,
        action="CALENDAR_EVENT_UPDATED",
        object_type="SchoolEvent",
        object_id=ev.id,
        details={
            "title": title,
            "category": ev.event_category,
            "status": ev.status,
            "is_override": ev.is_override
        }
    )

    return JsonResponse({'success': True, 'message': f"Event '{ev.title}' updated successfully."})


@login_required
@require_POST
def delete_calendar_event_ajax(request, event_id):
    """AJAX endpoint to delete or cancel an existing calendar event."""
    if not _can_manage_calendar(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    school = _get_active_school(request)
    ev = get_object_or_404(SchoolEvent, id=event_id, school=school)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    action_type = data.get('action', 'delete')  # 'delete' or 'cancel'

    if action_type == 'cancel':
        ev.status = EventStatus.CANCELLED
        if ev.is_automated:
            ev.is_override = True
        ev.save()

        AuditService.log_action(
            school=school,
            user=request.user,
            action="CALENDAR_EVENT_CANCELLED",
            object_type="SchoolEvent",
            object_id=ev.id,
            details={"title": ev.title, "event_id": ev.id}
        )
        return JsonResponse({'success': True, 'message': f"Event '{ev.title}' marked as Cancelled."})
    else:
        title = ev.title
        ev_id = ev.id
        ev.delete()

        AuditService.log_action(
            school=school,
            user=request.user,
            action="CALENDAR_EVENT_DELETED",
            object_type="SchoolEvent",
            object_id=ev_id,
            details={"title": title}
        )
        return JsonResponse({'success': True, 'message': f"Event '{title}' removed from calendar."})


@login_required
@require_POST
def generate_academic_calendar_view(request):
    """
    Automated generation endpoint for academic milestones, exams, holidays, and breaks.
    """
    if not _can_manage_calendar(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    school = _get_active_school(request)
    if not school:
        return JsonResponse({'success': False, 'error': 'School context missing.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    ay_id = data.get('academic_year_id')
    overwrite = data.get('overwrite', False)
    if isinstance(overwrite, str):
        overwrite = (overwrite.lower() in ['true', '1', 'yes'])

    academic_year = None
    if ay_id:
        academic_year = AcademicYear.objects.filter(school=school, id=ay_id).first()
    if not academic_year:
        academic_year = AcademicYear.objects.filter(school=school, is_active=True).first()

    if not academic_year:
        return JsonResponse({'success': False, 'error': 'Active academic year not found.'}, status=400)

    result = AcademicCalendarService.generate_events_for_academic_year(
        academic_year=academic_year,
        user=request.user,
        overwrite=overwrite
    )

    if result.get('success'):
        msg = f"Generated {result['created']} calendar events for {academic_year.name} ({result['skipped']} existing skipped, {result['preserved_overrides']} custom overrides preserved)."
        messages.success(request, msg)
        return JsonResponse({
            'success': True,
            'message': msg,
            'stats': result
        })
    else:
        return JsonResponse({'success': False, 'error': result.get('error', 'Failed to generate calendar events.')}, status=400)
