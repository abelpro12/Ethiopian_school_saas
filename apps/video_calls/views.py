import datetime
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.db.models import Q
from django.conf import settings

from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Section, Subject
from apps.messaging.models import Conversation, Message
from .models import VideoMeeting, MeetingAttendance, MeetingType, MeetingStatus


@login_required
def dashboard_view(request):
    """
    Main Video Call & Virtual Classroom Hub.
    Displays Live Now meetings, upcoming scheduled sessions, and history.
    """
    school = getattr(request, 'school', None)
    user = request.user
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    # Query meetings accessible to user in this school
    meetings_qs = VideoMeeting.objects.filter(school=school).select_related(
        'host', 'target_grade', 'target_section', 'target_subject', 'academic_year'
    ).prefetch_related('invited_participants', 'attendances')

    # Role-based visibility filtering
    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        if user.role == UserRole.TEACHER:
            meetings_qs = meetings_qs.filter(
                Q(host=user) |
                Q(meeting_type=MeetingType.STAFF_MEETING) |
                Q(meeting_type=MeetingType.GUEST_CONSULTATION) |
                Q(meeting_type=MeetingType.GENERAL) |
                Q(invited_participants=user) |
                Q(meeting_type=MeetingType.VIRTUAL_CLASS)
            ).distinct()
        elif user.role == UserRole.STUDENT:
            from apps.enrollment.models import StudentEnrollment
            enrollment = StudentEnrollment.objects.filter(
                student__user=user,
                school=school,
                status='ACTIVE'
            ).first()
            
            student_q = Q(invited_participants=user) | Q(meeting_type=MeetingType.GENERAL)
            if enrollment:
                student_q |= Q(
                    meeting_type=MeetingType.VIRTUAL_CLASS,
                    target_grade=enrollment.grade
                ) & (Q(target_section=enrollment.section) | Q(target_section__isnull=True))
            meetings_qs = meetings_qs.filter(student_q).distinct()
        elif user.role == UserRole.PARENT:
            from apps.parents.models import GuardianRelationship
            from apps.enrollment.models import StudentEnrollment
            children_student_ids = GuardianRelationship.objects.filter(
                parent__user=user
            ).values_list('student_id', flat=True)
            
            child_enrollments = StudentEnrollment.objects.filter(
                student_id__in=children_student_ids,
                school=school,
                status='ACTIVE'
            )
            child_grades = child_enrollments.values_list('grade_id', flat=True)
            child_sections = child_enrollments.values_list('section_id', flat=True)
            
            parent_q = Q(invited_participants=user) | Q(meeting_type=MeetingType.GENERAL)
            if child_grades.exists():
                parent_q |= Q(
                    meeting_type=MeetingType.VIRTUAL_CLASS,
                    target_grade_id__in=child_grades
                ) & (Q(target_section_id__in=child_sections) | Q(target_section__isnull=True))
            meetings_qs = meetings_qs.filter(parent_q).distinct()

    # Filter tabs
    tab = request.GET.get('tab', 'all')
    meeting_type_filter = request.GET.get('type')
    
    if meeting_type_filter:
        meetings_qs = meetings_qs.filter(meeting_type=meeting_type_filter)

    now = timezone.now()

    # Auto-update status for overdue scheduled meetings
    live_meetings = meetings_qs.filter(status=MeetingStatus.LIVE).order_by('-scheduled_start')
    upcoming_meetings = meetings_qs.filter(
        status=MeetingStatus.SCHEDULED,
        scheduled_start__gte=now - timezone.timedelta(hours=2)
    ).order_by('scheduled_start')
    
    past_meetings = meetings_qs.filter(
        Q(status=MeetingStatus.ENDED) | 
        Q(status=MeetingStatus.SCHEDULED, scheduled_start__lt=now - timezone.timedelta(hours=2))
    ).order_by('-scheduled_start')[:25]

    # Dropdowns for Create Modal
    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school, is_active=True).select_related('grade', 'stream')
    subjects = Subject.objects.filter(school=school).select_related('grade')
    teachers = User.objects.filter(school=school, role=UserRole.TEACHER, is_active=True).order_by('first_name', 'last_name')
    
    from apps.parents.models import ParentProfile
    parent_profiles = ParentProfile.objects.filter(school=school).select_related('user').prefetch_related('guardianships__student')
    parent_list = []
    for pp in parent_profiles:
        children_names = [g.student.full_name for g in pp.guardianships.all() if g.student]
        child_str = f" (Parent of {', '.join(children_names)})" if children_names else ""
        parent_list.append({
            'user_id': str(pp.user.id),
            'name': pp.user.get_full_name() or pp.user.username,
            'child_info': child_str,
        })

    from apps.students.models import StudentProfile
    student_profiles = StudentProfile.objects.filter(school=school, status='ACTIVE').select_related('user').prefetch_related('enrollments__grade')[:250]
    student_list = []
    for s in student_profiles:
        active_enr = s.enrollments.filter(status='ACTIVE').first() or s.enrollments.first()
        grade_str = f" - {active_enr.grade.name}" if active_enr and active_enr.grade else ""
        student_list.append({
            'user_id': str(s.user.id),
            'name': s.full_name,
            'student_id': s.student_id,
            'grade_info': grade_str,
        })

    # Metrics
    stats = {
        'live_count': live_meetings.count(),
        'upcoming_count': upcoming_meetings.count(),
        'total_hosted': VideoMeeting.objects.filter(school=school, host=user).count() if user.role == UserRole.TEACHER else VideoMeeting.objects.filter(school=school).count(),
        'my_attended': MeetingAttendance.objects.filter(user=user).count(),
    }

    can_create = user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.TEACHER]

    return render(request, 'video_calls/dashboard.html', {
        'live_meetings': live_meetings,
        'upcoming_meetings': upcoming_meetings,
        'past_meetings': past_meetings,
        'tab': tab,
        'stats': stats,
        'can_create': can_create,
        'grades': grades,
        'sections': sections,
        'subjects': subjects,
        'teachers': teachers,
        'student_list': student_list,
        'parent_list': parent_list,
        'meeting_types': MeetingType.choices,
        'now': now,
    })


@login_required
def create_meeting_view(request):
    """
    Create or schedule a new Virtual Class, Guest Consultation, or Video Conference.
    """
    school = getattr(request, 'school', None)
    user = request.user
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.TEACHER]:
        messages.error(request, "You do not have permission to host video meetings.")
        return redirect('video_calls:dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        meeting_type = request.POST.get('meeting_type', MeetingType.VIRTUAL_CLASS)
        duration_minutes = int(request.POST.get('duration_minutes', 45))
        is_instant = request.POST.get('is_instant') == 'true'
        allow_guest_access = request.POST.get('allow_guest_access') == 'true' or request.POST.get('allow_guest_access') == 'on'
        
        grade_id = request.POST.get('target_grade')
        section_id = request.POST.get('target_section')
        subject_id = request.POST.get('target_subject')
        passcode = request.POST.get('passcode', '').strip()
        
        start_date_str = request.POST.get('start_date')
        start_time_str = request.POST.get('start_time')

        if not title:
            messages.error(request, "Meeting title is required.")
            return redirect('video_calls:dashboard')

        if is_instant:
            scheduled_start = timezone.now()
            status = MeetingStatus.LIVE
        else:
            try:
                if start_date_str and start_time_str:
                    combined_str = f"{start_date_str} {start_time_str}"
                    naive_dt = datetime.datetime.strptime(combined_str, "%Y-%m-%d %H:%M")
                    scheduled_start = timezone.make_aware(naive_dt, timezone.get_current_timezone())
                else:
                    scheduled_start = timezone.now()
            except Exception:
                scheduled_start = timezone.now()
            status = MeetingStatus.SCHEDULED

        meeting = VideoMeeting.objects.create(
            school=school,
            academic_year=current_ay,
            title=title,
            description=description,
            meeting_type=meeting_type,
            host=user,
            target_grade_id=grade_id if grade_id else None,
            target_section_id=section_id if section_id else None,
            target_subject_id=subject_id if subject_id else None,
            passcode=passcode if passcode else None,
            allow_guest_access=allow_guest_access,
            scheduled_start=scheduled_start,
            duration_minutes=duration_minutes,
            status=status
        )

        # Invited specific users if provided
        participant_ids = request.POST.getlist('participants')
        if participant_ids:
            meeting.invited_participants.set(participant_ids)

        if is_instant:
            messages.success(request, f"Instant live room '{meeting.title}' is ready!")
            return redirect('video_calls:room', room_id=meeting.id)
        else:
            messages.success(request, f"Meeting '{meeting.title}' has been scheduled successfully.")
            return redirect('video_calls:dashboard')

    return redirect('video_calls:dashboard')


@login_required
def start_instant_call_view(request):
    """
    Instantly create a 1-on-1 direct call, guest call, or consultation and redirect to room.
    """
    school = getattr(request, 'school', None)
    user = request.user
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    recipient_id = request.GET.get('user_id')
    conversation_id = request.GET.get('conversation_id')
    is_guest_mode = request.GET.get('guest') == 'true'
    
    recipient = None
    if recipient_id:
        recipient = User.objects.filter(id=recipient_id, school=school).first()

    title = f"Video Call: {user.get_full_name() or user.username}"
    if recipient:
        title += f" & {recipient.get_full_name() or recipient.username}"
    elif is_guest_mode:
        title = f"VIP Guest Call hosted by {user.get_full_name() or user.username}"

    meeting = VideoMeeting.objects.create(
        school=school,
        academic_year=current_ay,
        title=title,
        meeting_type=MeetingType.GUEST_CONSULTATION if is_guest_mode else (MeetingType.DIRECT_CALL if recipient else MeetingType.GENERAL),
        host=user,
        allow_guest_access=True,
        scheduled_start=timezone.now(),
        duration_minutes=60,
        status=MeetingStatus.LIVE
    )

    if recipient:
        meeting.invited_participants.add(recipient)

        # Send invite message in existing conversation thread if available
        if conversation_id:
            conv = Conversation.objects.filter(id=conversation_id, school=school).first()
            if conv:
                join_url = f"/video-calls/room/{meeting.id}/"
                Message.objects.create(
                    school=school,
                    conversation=conv,
                    sender=user,
                    body=f"📹 Started an instant video call. Join here: {join_url}"
                )

    messages.success(request, "Live call room launched! You can copy the guest link to invite external participants.")
    return redirect('video_calls:room', room_id=meeting.id)


@login_required
def meeting_room_view(request, room_id):
    """
    In-room Video Conference and Pre-call device test lobby for authenticated users.
    """
    school = getattr(request, 'school', None)
    user = request.user
    meeting = get_object_or_404(VideoMeeting, id=room_id, school=school)

    if not meeting.can_user_access(user):
        messages.error(request, "You do not have permission to join this video meeting.")
        return redirect('video_calls:dashboard')

    # If meeting was scheduled and host joins, set to LIVE
    if meeting.status == MeetingStatus.SCHEDULED and (meeting.host_id == user.id or user.role in [UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]):
        meeting.status = MeetingStatus.LIVE
        meeting.save(update_fields=['status'])

    # Log entry in MeetingAttendance
    attendance, created = MeetingAttendance.objects.get_or_create(
        meeting=meeting,
        user=user,
        school=school,
        defaults={
            'joined_at': timezone.now(),
            'is_present': True,
            'is_guest': False,
            'device_info': request.META.get('HTTP_USER_AGENT', '')[:250]
        }
    )
    if not created and attendance.left_at:
        # Re-joining
        attendance.left_at = None
        attendance.save(update_fields=['left_at'])

    is_host = (meeting.host_id == user.id or user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL])
    
    # Generate clean Jitsi room name scoped to tenant
    clean_tenant = (school.code if school else 'ETHIO_SCHOOL').replace(' ', '_')
    jitsi_room = f"{clean_tenant}_{meeting.room_name}"
    jitsi_domain = getattr(settings, 'JITSI_DOMAIN', 'vc.autistici.org')

    guest_full_url = meeting.get_guest_url(request)
    standalone_meeting_url = f"https://{jitsi_domain}/{jitsi_room}"

    context = {
        'meeting': meeting,
        'is_host': is_host,
        'jitsi_room': jitsi_room,
        'jitsi_domain': jitsi_domain,
        'standalone_meeting_url': standalone_meeting_url,
        'user_display_name': user.get_full_name() or user.username,
        'user_email': user.email or f"{user.username}@ethioschool.internal",
        'user_role_display': user.get_role_display(),
        'user_avatar': user.profile_picture.url if user.profile_picture else '',
        'guest_full_url': guest_full_url,
    }
    return render(request, 'video_calls/room.html', context)


def guest_room_view(request, token):
    """
    Publicly accessible guest video calling room for external guests (VIPs, inspectors, prospective parents).
    No login required.
    """
    meeting = get_object_or_404(VideoMeeting, guest_token=token)
    school = meeting.school

    if not meeting.allow_guest_access:
        return render(request, 'video_calls/guest_closed.html', {
            'meeting': meeting,
            'reason': 'Guest access has been disabled for this meeting by the school host.'
        })

    if meeting.status == MeetingStatus.ENDED or meeting.status == MeetingStatus.CANCELLED:
        return render(request, 'video_calls/guest_closed.html', {
            'meeting': meeting,
            'reason': 'This video meeting has already ended.'
        })

    error_msg = None
    guest_name = request.session.get(f'guest_name_{meeting.id}') or request.GET.get('name')

    # Passcode verification
    if request.method == 'POST':
        submitted_name = request.POST.get('guest_name', '').strip()
        submitted_passcode = request.POST.get('passcode', '').strip()

        if not submitted_name:
            error_msg = "Please enter your full name or title to join."
        elif meeting.passcode and submitted_passcode != meeting.passcode:
            error_msg = "Incorrect room passcode. Please check with your host."
        else:
            guest_name = submitted_name
            request.session[f'guest_name_{meeting.id}'] = guest_name

    clean_tenant = (school.code if school else 'ETHIO_SCHOOL').replace(' ', '_')
    jitsi_room = f"{clean_tenant}_{meeting.room_name}"
    jitsi_domain = getattr(settings, 'JITSI_DOMAIN', 'vc.autistici.org')
    standalone_meeting_url = f"https://{jitsi_domain}/{jitsi_room}"

    # Log guest attendance if name is set
    attendance_id = None
    if guest_name:
        att = MeetingAttendance.objects.create(
            school=school,
            meeting=meeting,
            user=None,
            guest_name=guest_name,
            is_guest=True,
            joined_at=timezone.now(),
            is_present=True,
            device_info=request.META.get('HTTP_USER_AGENT', '')[:250]
        )
        attendance_id = str(att.id)

    context = {
        'meeting': meeting,
        'school': school,
        'guest_name': guest_name,
        'attendance_id': attendance_id,
        'jitsi_room': jitsi_room,
        'jitsi_domain': jitsi_domain,
        'standalone_meeting_url': standalone_meeting_url,
        'error_msg': error_msg,
        'requires_passcode': bool(meeting.passcode),
    }
    return render(request, 'video_calls/guest_room.html', context)



@login_required
def meeting_detail_view(request, room_id):
    """
    Post-meeting summary and participant attendance roster (including guests).
    """
    school = getattr(request, 'school', None)
    user = request.user
    meeting = get_object_or_404(VideoMeeting, id=room_id, school=school)

    if not meeting.can_user_access(user):
        messages.error(request, "Access denied.")
        return redirect('video_calls:dashboard')

    attendances = meeting.attendances.select_related('user').order_by('joined_at')
    
    # Class roster comparison if this was a Virtual Class
    enrolled_students = []
    if meeting.target_grade and meeting.meeting_type == MeetingType.VIRTUAL_CLASS:
        from apps.enrollment.models import StudentEnrollment
        enrollments_qs = StudentEnrollment.objects.filter(
            school=school,
            grade=meeting.target_grade,
            status='ACTIVE'
        ).select_related('student__user')
        if meeting.target_section:
            enrollments_qs = enrollments_qs.filter(section=meeting.target_section)
        
        attended_user_ids = set(attendances.filter(is_guest=False).values_list('user_id', flat=True))
        for enr in enrollments_qs:
            student_user = enr.student.user
            enrolled_students.append({
                'enrollment': enr,
                'user': student_user,
                'attended': student_user.id in attended_user_ids
            })

    guest_full_url = meeting.get_guest_url(request)

    return render(request, 'video_calls/detail.html', {
        'meeting': meeting,
        'attendances': attendances,
        'enrolled_students': enrolled_students,
        'guest_full_url': guest_full_url,
        'is_host': (meeting.host_id == user.id or user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]),
    })


@login_required
def end_meeting_view(request, room_id):
    """
    Host / Administrator ends the live meeting session for all participants and guests.
    """
    school = getattr(request, 'school', None)
    user = request.user
    meeting = get_object_or_404(VideoMeeting, id=room_id, school=school)

    if meeting.host_id != user.id and user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        messages.error(request, "Only the meeting host or school admin can end this meeting.")
        return redirect('video_calls:room', room_id=meeting.id)

    meeting.status = MeetingStatus.ENDED
    meeting.scheduled_end = timezone.now()
    meeting.save(update_fields=['status', 'scheduled_end'])

    # Close active attendances
    for att in meeting.attendances.filter(left_at__isnull=True):
        att.mark_left()

    messages.success(request, f"Meeting '{meeting.title}' has ended. Attendance logs have been saved.")
    return redirect('video_calls:detail', room_id=meeting.id)


@login_required
def delete_meeting_view(request, room_id):
    """
    Host / Administrator deletes a scheduled or past video meeting session.
    """
    school = getattr(request, 'school', None)
    user = request.user
    meeting = get_object_or_404(VideoMeeting, id=room_id, school=school)

    if meeting.host_id != user.id and user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        messages.error(request, "Only the meeting host or school administrator can delete this meeting.")
        return redirect('video_calls:dashboard')

    title = meeting.title
    meeting.delete()
    messages.success(request, f"Scheduled meeting '{title}' has been successfully deleted.")
    return redirect('video_calls:dashboard')



@csrf_exempt
def api_log_attendance_view(request, room_id):
    """
    AJAX endpoint called periodically or on page unload to log continuous presence and duration.
    Supports both logged-in users and external guests.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    meeting = get_object_or_404(VideoMeeting, id=room_id)
    school = meeting.school

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    action = data.get('action', 'heartbeat')  # 'join', 'heartbeat', 'leave'
    attendance_id = data.get('attendance_id')
    guest_name = data.get('guest_name')

    attendance = None
    if attendance_id:
        attendance = MeetingAttendance.objects.filter(id=attendance_id, meeting=meeting).first()
    
    if not attendance and request.user.is_authenticated:
        attendance, _ = MeetingAttendance.objects.get_or_create(
            meeting=meeting,
            user=request.user,
            school=school,
            defaults={'joined_at': timezone.now(), 'is_present': True, 'is_guest': False}
        )
    elif not attendance and guest_name:
        attendance = MeetingAttendance.objects.create(
            meeting=meeting,
            user=None,
            guest_name=guest_name,
            is_guest=True,
            school=school,
            joined_at=timezone.now(),
            is_present=True
        )

    if not attendance:
        return JsonResponse({'status': 'error', 'message': 'Could not locate attendance record'}, status=400)

    if action == 'leave':
        attendance.mark_left()
        return JsonResponse({'status': 'ok', 'message': 'Left meeting'})
    else:
        # Heartbeat update
        delta = (timezone.now() - attendance.joined_at).total_seconds()
        attendance.duration_seconds = max(0, int(delta))
        attendance.left_at = None
        attendance.save(update_fields=['duration_seconds', 'left_at'])
        return JsonResponse({'status': 'ok', 'duration_seconds': attendance.duration_seconds, 'attendance_id': str(attendance.id)})
