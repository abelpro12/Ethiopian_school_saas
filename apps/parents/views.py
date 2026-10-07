from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.models import UserRole
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark, MarkStatus, AcademicPeriodResult
from apps.finance.models import StudentInvoice, Payment
from apps.communication.models import Announcement
from apps.library.models import BorrowRecord


@login_required
def parent_dashboard_view(request):
    """
    Parent Portal Dashboard.
    Supports viewing multiple linked children, attendance, published marks, invoices, and conduct.
    """
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    user = request.user
    parent_id = request.GET.get('parent_id')

    if parent_id and getattr(user, 'role', None) in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        try:
            parent_profile = ParentProfile.objects.get(id=parent_id, school=school)
        except (ParentProfile.DoesNotExist, ValueError):
            parent_profile = None
    else:
        try:
            parent_profile = ParentProfile.objects.get(user=user, school=school)
        except ParentProfile.DoesNotExist:
            if user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
                parent_profile = ParentProfile.objects.filter(school=school).first()
            else:
                messages.error(request, "Parent profile not found.")
                return redirect('index')

    guardianships = GuardianRelationship.objects.filter(parent=parent_profile, school=school).select_related('student')
    children = [g.student for g in guardianships]

    if not children:
        return render(request, 'parents/parent_portal.html', {
            'parent_profile': parent_profile,
            'children': [],
            'selected_child': None,
        })

    # Determine selected child
    selected_child_id = request.GET.get('child_id')
    selected_child = None
    if selected_child_id:
        selected_child = next((c for c in children if str(c.id) == selected_child_id or c.student_id == selected_child_id), None)

    if not selected_child:
        selected_child = children[0]

    from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
    from apps.assessments.models import StudentConduct
    from apps.academics.models import AcademicYear

    current_ay = getattr(request, 'academic_year', None)
    if not current_ay and school:
        current_ay = AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date').first()

    # Child's current enrollment (Active Academic Year Only)
    enrollment_qs = StudentEnrollment.objects.filter(school=school, student=selected_child)
    if current_ay:
        enrollment = enrollment_qs.filter(academic_year=current_ay).select_related('section', 'grade', 'stream', 'academic_year').first()
    else:
        enrollment = enrollment_qs.filter(status=EnrollmentStatus.ACTIVE).select_related('section', 'grade', 'stream', 'academic_year').first()

    target_ay = current_ay or (enrollment.academic_year if enrollment else None)

    # Attendance for ACTIVE academic year ONLY
    attendance_qs = AttendanceRecord.objects.filter(school=school, student=selected_child)
    if target_ay:
        attendance_qs = attendance_qs.filter(date__gte=target_ay.gregorian_start_date, date__lte=target_ay.gregorian_end_date)
    total_days = attendance_qs.count()
    absent_count = attendance_qs.filter(status='ABSENT').count()
    present_count = attendance_qs.filter(status='PRESENT').count()
    late_count = attendance_qs.filter(status='LATE').count()
    recent_attendance = attendance_qs.order_by('-date')[:10]
    attendance_percentage = round(((present_count + late_count) / total_days * 100), 1) if total_days > 0 else 100.0

    # All student marks assigned by teachers for ACTIVE academic year ONLY
    published_marks = StudentMark.objects.filter(
        school=school,
        enrollment__student=selected_child
    ).select_related('assessment_component__subject', 'assessment_component__period').order_by('-created_at')
    if target_ay:
        published_marks = published_marks.filter(
            Q(enrollment__academic_year=target_ay) | Q(assessment_component__academic_year=target_ay)
        )

    subject_marks_dict = {}
    subject_list = []
    seen_subjects = set()
    for m in published_marks:
        sub = m.assessment_component.subject
        if sub.id not in seen_subjects:
            seen_subjects.add(sub.id)
            subject_list.append(sub)

        if sub.id not in subject_marks_dict:
            subject_marks_dict[sub.id] = {
                'subject': sub,
                'marks': [],
                'total_score': 0.0,
                'max_total': 0.0,
                'count': 0
            }

        try:
            val = float(m.mark_value)
            mx = float(m.assessment_component.max_marks)
        except (ValueError, TypeError):
            val = 0.0
            mx = 100.0

        subject_marks_dict[sub.id]['marks'].append(m)
        subject_marks_dict[sub.id]['total_score'] += val
        subject_marks_dict[sub.id]['max_total'] += mx
        subject_marks_dict[sub.id]['count'] += 1

    published_statuses = {'PUBLISHED', 'APPROVED', 'LOCKED'}
    subject_summary_list = []
    for sub_id, data in subject_marks_dict.items():
        tot = round(data['total_score'], 2)
        max_tot = round(data['max_total'], 2) if data['max_total'] > 0 else 100.0
        pct = round((tot / max_tot * 100), 1) if max_tot > 0 else tot
        
        if pct >= 90:
            letter = 'A+'
        elif pct >= 83:
            letter = 'A'
        elif pct >= 75:
            letter = 'B'
        elif pct >= 65:
            letter = 'C'
        elif pct >= 50:
            letter = 'D'
        else:
            letter = 'F'

        marks_statuses = [m.status for m in data['marks']]
        is_published = len(marks_statuses) > 0 and all(st in published_statuses for st in marks_statuses)

        subject_summary_list.append({
            'subject': data['subject'],
            'marks': data['marks'],
            'total_score': tot,
            'max_total': max_tot,
            'percentage': pct,
            'letter_grade': letter,
            'count': data['count'],
            'is_published': is_published,
        })

    # Conduct for ACTIVE academic year ONLY
    latest_conduct_qs = StudentConduct.objects.filter(
        school=school,
        enrollment__student=selected_child
    )
    if target_ay:
        latest_conduct_qs = latest_conduct_qs.filter(enrollment__academic_year=target_ay)
    latest_conduct = latest_conduct_qs.order_by('-created_at').first()

    # Financial Invoices for ACTIVE academic year ONLY
    invoices = StudentInvoice.objects.filter(school=school, student=selected_child).order_by('-created_at')
    if target_ay:
        invoices = invoices.filter(academic_year=target_ay)
    outstanding_balance = sum(inv.remaining_balance for inv in invoices)

    # Announcements
    announcements = Announcement.objects.filter(
        school=school,
        target_type__in=['SCHOOL', 'PARENTS']
    ).order_by('-created_at')[:5]

    # Active Library Borrows
    try:
        from apps.library.models import BorrowRecord
        active_borrows = BorrowRecord.objects.filter(
            school=school,
            borrower_student=selected_child,
            return_date__isnull=True
        ).select_related('book_copy__book')
    except Exception:
        active_borrows = []

    # Active Academic Year Enrollment Details Only (No Past Years)
    all_enrollments = StudentEnrollment.objects.filter(
        school=school, student=selected_child
    ).select_related('academic_year', 'grade', 'stream', 'section', 'promotion_decision')
    if target_ay:
        all_enrollments = all_enrollments.filter(academic_year=target_ay)

    # Official Computed & Published Evaluation Period Results / Report Cards (Active Academic Year Only)
    period_results_qs = AcademicPeriodResult.objects.filter(
        school=school,
        enrollment__student=selected_child,
        is_published=True
    ).select_related('period', 'period__academic_year').order_by('-period__academic_year__gregorian_start_date', '-period__start_date')
    if target_ay:
        period_results_qs = period_results_qs.filter(period__academic_year=target_ay)

    all_parents = []
    if getattr(request.user, 'role', None) in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        all_parents = ParentProfile.objects.filter(school=school).select_related('user')[:200]

    # Active & Upcoming 1-on-1 Parent-Teacher Video Calls
    active_video_calls = []
    upcoming_video_calls = []
    try:
        from apps.video_calls.models import VideoMeeting, MeetingStatus, MeetingType
        parent_user = parent_profile.user if parent_profile else None
        if parent_user and school:
            from django.utils import timezone
            now = timezone.now()
            # Active Live Calls
            active_video_calls = VideoMeeting.objects.filter(
                school=school,
                status=MeetingStatus.LIVE
            ).filter(
                Q(invited_participants=parent_user) |
                Q(meeting_type=MeetingType.GENERAL)
            ).select_related('host').distinct()

            # Upcoming Scheduled Consultations
            upcoming_video_calls = VideoMeeting.objects.filter(
                school=school,
                status=MeetingStatus.SCHEDULED,
                scheduled_start__gte=now - timezone.timedelta(hours=2),
                invited_participants=parent_user
            ).select_related('host').order_by('scheduled_start')[:5]
    except Exception:
        active_video_calls = []
        upcoming_video_calls = []

    return render(request, 'parents/parent_portal.html', {
        'parent_profile': parent_profile,
        'all_parents': all_parents,
        'children': children,
        'selected_child': selected_child,
        'enrollment': enrollment,
        'all_enrollments': all_enrollments,
        'attendance_records': recent_attendance,
        'total_days': total_days,
        'absent_count': absent_count,
        'attendance_percentage': attendance_percentage,
        'published_marks': published_marks,
        'subject_summary_list': subject_summary_list,
        'period_results': period_results_qs,
        'subject_list': subject_list,
        'latest_conduct': latest_conduct,
        'invoices': invoices,
        'outstanding_balance': outstanding_balance,
        'announcements': announcements,
        'active_borrows': active_borrows,
        'active_video_calls': active_video_calls,
        'upcoming_video_calls': upcoming_video_calls,
    })

