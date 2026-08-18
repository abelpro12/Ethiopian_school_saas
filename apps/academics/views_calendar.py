import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone


@login_required
def school_calendar_view(request):
    """
    Visual school calendar page with FullCalendar, Event creation,
    Upcoming events sidebar, and Category filtering.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    current_ay = getattr(request, 'academic_year', None)

    # Allow School Admin, Principal, Registrar to add events
    can_manage = getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']

    if request.method == 'POST' and can_manage:
        from apps.academics.models import SchoolEvent, EventType, TargetAudience
        title = request.POST.get('title', '').strip()
        event_type = request.POST.get('event_type', EventType.SCHOOL_EVENT)
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date') or None
        description = request.POST.get('description', '').strip()

        if title and start_date and current_ay and school:
            SchoolEvent.objects.create(
                school=school,
                academic_year=current_ay,
                title=title,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                description=description or None,
            )
            messages.success(request, f"Event '{title}' added to school calendar!")
        else:
            messages.error(request, "Please fill in all required fields (title & start date).")
        return redirect('school_calendar')

    # Fetch upcoming events list for the sidebar
    upcoming_events = []
    today = timezone.now().date()
    try:
        from apps.academics.models import SchoolEvent
        events_qs = SchoolEvent.objects.filter(school=school, start_date__gte=today).order_by('start_date')[:6]
        upcoming_events = events_qs
    except Exception:
        pass

    # Fetch upcoming exams
    upcoming_exams = []
    try:
        from apps.examinations.models import ExamSchedule
        exams_qs = ExamSchedule.objects.filter(school=school, exam_date__gte=today).select_related('subject').order_by('exam_date')[:5]
        upcoming_exams = exams_qs
    except Exception:
        pass

    return render(request, 'academics/calendar.html', {
        'current_ay': current_ay,
        'can_manage': can_manage,
        'upcoming_events': upcoming_events,
        'upcoming_exams': upcoming_exams,
        'today': today.isoformat(),
    })


@login_required
def calendar_events_json_view(request):
    """JSON endpoint that returns all calendar events for FullCalendar."""
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    current_ay = getattr(request, 'academic_year', None)

    events = []

    # 1. School Events
    try:
        from apps.academics.models import SchoolEvent
        school_events = SchoolEvent.objects.filter(school=school)
        if current_ay:
            school_events = school_events.filter(academic_year=current_ay)
        for ev in school_events:
            color = '#6366f1'  # Indigo default
            if ev.event_type == 'EXAM': color = '#ef4444'
            elif ev.event_type == 'HOLIDAY': color = '#10b981'
            elif ev.event_type == 'MEETING': color = '#f59e0b'
            elif ev.event_type == 'SPORTS': color = '#0ea5e9'

            events.append({
                'id': f'ev-{ev.id}',
                'title': f'📌 {ev.title}',
                'start': ev.start_date.isoformat(),
                'end': ev.end_date.isoformat() if ev.end_date else ev.start_date.isoformat(),
                'color': color,
                'description': ev.description or f"Category: {ev.get_event_type_display()}",
                'type': 'event',
                'category': ev.event_type,
            })
    except Exception:
        pass

    # 2. Exam Schedules
    try:
        from apps.examinations.models import ExamSchedule
        exams = ExamSchedule.objects.filter(school=school).select_related('subject', 'exam_session')
        if current_ay:
            exams = exams.filter(exam_session__academic_year=current_ay)
        for ex in exams:
            events.append({
                'id': f'exam-{ex.id}',
                'title': f'📝 {ex.subject.name} Exam',
                'start': ex.exam_date.isoformat(),
                'end': ex.exam_date.isoformat(),
                'color': '#ef4444',
                'description': f'Subject: {ex.subject.name} | Time: {ex.start_time} - {ex.end_time}',
                'type': 'exam',
                'category': 'EXAM',
            })
    except Exception:
        pass

    # 3. AcademicPeriod Dates
    try:
        from apps.academics.models import AcademicPeriod
        periods = AcademicPeriod.objects.filter(school=school)
        if current_ay:
            periods = periods.filter(academic_year=current_ay)
        for sem in periods:
            if sem.start_date:
                events.append({
                    'id': f'sem-start-{sem.id}',
                    'title': f'🎓 {sem.name} Starts',
                    'start': sem.start_date.isoformat(),
                    'color': '#10b981',
                    'type': 'period',
                    'category': 'PERIOD',
                })
            if sem.end_date:
                events.append({
                    'id': f'sem-end-{sem.id}',
                    'title': f'🏁 {sem.name} Ends',
                    'start': sem.end_date.isoformat(),
                    'color': '#f59e0b',
                    'type': 'period',
                    'category': 'PERIOD',
                })
    except Exception:
        pass

    # 4. Academic Year Start & End
    if current_ay:
        if current_ay.start_date:
            events.append({
                'id': f'ay-start-{current_ay.id}',
                'title': f'📅 {current_ay.name} Begins',
                'start': current_ay.start_date.isoformat(),
                'color': '#0ea5e9',
                'type': 'academic_year',
                'category': 'ACADEMIC_YEAR',
            })
        if current_ay.end_date:
            events.append({
                'id': f'ay-end-{current_ay.id}',
                'title': f'📅 {current_ay.name} Ends',
                'start': current_ay.end_date.isoformat(),
                'color': '#0ea5e9',
                'type': 'academic_year',
                'category': 'ACADEMIC_YEAR',
            })

    return JsonResponse(events, safe=False)
