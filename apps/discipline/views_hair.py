import os
import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone
from apps.accounts.models import UserRole
from apps.academics.models import AcademicYear, Grade, Section
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment
from apps.parents.models import GuardianRelationship
from apps.communication.models import TelegramAccountLink
from apps.discipline.models import HairCheckRecord, HairCheckStatus
from apps.discipline.hair_ai_service import HairCheckAIService
from apps.discipline.hair_notification_service import HairNotificationService


@login_required
def hair_check_scanner_view(request):
    """
    Interactive camera & AI Hair Grooming Scanner view.
    Designed for morning gatekeepers, discipline officers, and teachers.
    """
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
    user = request.user

    if user.role not in [
        UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL,
        UserRole.REGISTRAR, UserRole.TEACHER
    ]:
        messages.error(request, "Unauthorized access to Discipline Grooming Scanner.")
        return redirect('discipline:list')

    # Fetch active enrollments for instant auto-complete
    enrollments = StudentEnrollment.objects.filter(school=school)
    if current_ay:
        enrollments = enrollments.filter(academic_year=current_ay)

    enrollments = enrollments.select_related(
        'student__user', 'grade', 'section'
    ).order_by('grade__level', 'section__name', 'student__first_name', 'student__last_name')

    students_list = []
    for en in enrollments:
        stu = en.student
        grd = en.grade
        sec = en.section
        class_str = f"Grade {grd.level}" if grd else ""
        if sec:
            class_str += f" - {sec.name}"

        # Check guardian link status
        guardians = GuardianRelationship.objects.filter(student=stu, school=school).select_related('parent__user')
        has_tg = False
        has_phone = False
        has_email = False
        for g in guardians:
            p_user = g.parent.user if g.parent else None
            if g.parent and (getattr(g.parent, 'phone', None) or getattr(g.parent, 'phone_number', None)):
                has_phone = True

            if p_user and p_user.email:
                has_email = True
            if p_user and TelegramAccountLink.objects.filter(user=p_user, is_verified=True).exists():
                has_tg = True

        students_list.append({
            'id': str(stu.id),
            'full_name': stu.full_name,
            'student_id': stu.student_id or stu.user.username,
            'class_str': class_str,
            'gender': stu.gender,
            'has_telegram': has_tg,
            'has_phone': has_phone,
            'has_email': has_email,
        })

    # Summary metrics for today
    today = timezone.now().date()
    today_checks = HairCheckRecord.objects.filter(school=school, created_at__date=today)
    total_today = today_checks.count()
    prohibited_today = today_checks.filter(status=HairCheckStatus.PROHIBITED).count()
    allowed_today = today_checks.filter(status=HairCheckStatus.ALLOWED).count()
    notified_today = today_checks.filter(parent_notified=True).count()

    # Bot config status
    telegram_bot_configured = bool(os.environ.get('TELEGRAM_BOT_TOKEN') or getattr(request, 'school', None))
    gemini_ai_configured = bool(HairCheckAIService.get_gemini_api_key())

    context = {
        'students_json': json.dumps(students_list),
        'students_count': len(students_list),
        'current_ay': current_ay,
        'total_today': total_today,
        'prohibited_today': prohibited_today,
        'allowed_today': allowed_today,
        'notified_today': notified_today,
        'telegram_bot_configured': telegram_bot_configured,
        'gemini_ai_configured': gemini_ai_configured,
        'today_date': today.strftime('%b %d, %Y'),
    }
    return render(request, 'discipline/hair_check_scanner.html', context)


@login_required
@require_POST
def hair_check_analyze_api(request):
    """
    API endpoint: Analyzes an uploaded or camera-captured haircut photo.
    Returns AI verdict, confidence, detected violations, and student/parent info.
    """
    school = getattr(request, 'school', None)
    photo_file = request.FILES.get('photo')
    if not photo_file:
        return JsonResponse({'success': False, 'error': 'No photo provided for analysis.'}, status=400)

    student_id = request.POST.get('student_id', '').strip()
    student = None
    student_info = None

    if student_id:
        student = StudentProfile.objects.filter(id=student_id, school=school).first()
        if student:
            recipients = HairNotificationService.get_parent_contacts(student, school)
            has_tg = any(r.get('telegram_chat_id') for r in recipients)
            has_phone = any(r.get('phone') for r in recipients)
            has_email = any(r.get('email') for r in recipients)
            
            student_info = {
                'id': str(student.id),
                'full_name': student.full_name,
                'student_id': student.student_id,
                'has_telegram': has_tg,
                'has_phone': has_phone,
                'has_email': has_email,
                'recipients_count': len(recipients),
                'recipients': [
                    {
                        'name': r['name'],
                        'phone': r['phone'],
                        'email': r['email'],
                        'has_telegram': bool(r.get('telegram_chat_id')),
                        'is_primary': r['is_primary']
                    }
                    for r in recipients
                ]
            }

    student_name = student.full_name if student else ""
    analysis = HairCheckAIService.analyze_hair_image(photo_file, student_name=student_name)

    return JsonResponse({
        'success': True,
        'analysis': analysis,
        'student': student_info
    })


@login_required
@require_POST
def hair_check_dispatch_api(request):
    """
    API endpoint: Saves inspection record and dispatches notice to parent.
    Supports Telegram photo + SMS + Email in one click.
    """
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
    user = request.user

    student_id = request.POST.get('student_id', '').strip()
    if not student_id:
        return JsonResponse({'success': False, 'error': 'Student must be selected.'}, status=400)

    student = get_object_or_404(StudentProfile, id=student_id, school=school)
    photo_file = request.FILES.get('photo')

    status = request.POST.get('status', 'PROHIBITED')
    confidence = int(request.POST.get('confidence', 90))
    recommendation = request.POST.get('recommendation', '').strip()
    reason = request.POST.get('reason', '').strip()
    reason_am = request.POST.get('reason_am', '').strip()
    summary = request.POST.get('summary', '').strip()
    ai_engine = request.POST.get('ai_engine', 'Gemini Vision / Smart Heuristics')
    custom_note = request.POST.get('custom_note', '').strip()
    notify_parent = request.POST.get('notify_parent', 'true' if status == 'PROHIBITED' else 'false').lower() in ['true', '1', 'yes']

    # Raw violations array
    violations_raw = request.POST.get('violations', '[]')
    try:
        violations = json.loads(violations_raw)
        if isinstance(violations, str):
            violations = [violations]
    except Exception:
        violations = [v.strip() for v in violations_raw.split(',') if v.strip()]

    # Channels
    channels_raw = request.POST.get('channels', 'TELEGRAM,SMS,EMAIL')
    channels = [c.strip().upper() for c in channels_raw.split(',') if c.strip()]

    # Deadline date
    deadline_days = int(request.POST.get('deadline_days', 2))
    deadline_date = timezone.now().date() + datetime.timedelta(days=deadline_days)

    # Ensure persuasive reason is populated
    if not reason:
        reason = HairCheckAIService._build_persuasive_reason(
            status=status,
            is_fade=any('fade' in str(v).lower() for v in violations),
            is_too_long=any('long' in str(v).lower() or 'bushy' in str(v).lower() for v in violations),
            student_name=student.full_name,
            lang='en'
        )
    if not reason_am:
        reason_am = HairCheckAIService._build_persuasive_reason(
            status=status,
            is_fade=any('fade' in str(v).lower() for v in violations),
            is_too_long=any('long' in str(v).lower() or 'bushy' in str(v).lower() for v in violations),
            student_name=student.full_name,
            lang='am'
        )

    # Create HairCheckRecord
    hair_record = HairCheckRecord.objects.create(
        school=school,
        academic_year=current_ay,
        student=student,
        checked_by=user,
        photo=photo_file,
        status=status,
        confidence=confidence,
        violations=violations,
        recommendation=recommendation,
        reason=reason,
        reason_am=reason_am,
        summary=summary,
        ai_engine=ai_engine,
        deadline_date=deadline_date,
    )

    dispatch_res = {}
    if notify_parent:
        dispatch_res = HairNotificationService.dispatch_hair_notice(
            hair_record=hair_record,
            channels=channels,
            custom_note=custom_note,
            operator_user=user
        )
    else:
        hair_record.parent_notified = False
        hair_record.save(update_fields=['parent_notified'])

    if hair_record.parent_notified:
        msg = (
            f"Inspection saved. Grooming violation notice sent to {student.full_name}'s parents via {', '.join(channels)}!"
            if status == HairCheckStatus.PROHIBITED else
            f"Inspection saved. Commendation notice sent to {student.full_name}'s parents via {', '.join(channels)}!"
        )
    else:
        msg = f"Inspection saved as Approved. No disciplinary action needed."

    return JsonResponse({
        'success': True,
        'record_id': hair_record.id,
        'status': hair_record.status,
        'parent_notified': hair_record.parent_notified,
        'dispatch_result': dispatch_res,
        'message': msg
    })


@login_required
def hair_check_history_view(request):
    """
    Audit log & gallery view of past hair checks.
    """
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None)

    records = HairCheckRecord.objects.filter(school=school).select_related(
        'student', 'checked_by', 'academic_year', 'linked_incident'
    ).order_by('-created_at')

    # Status filter
    status_filter = request.GET.get('status')
    if status_filter:
        records = records.filter(status=status_filter)

    # Date filter
    date_filter = request.GET.get('date')
    if date_filter:
        try:
            filter_date = datetime.datetime.strptime(date_filter, '%Y-%m-%d').date()
            records = records.filter(created_at__date=filter_date)
        except ValueError:
            pass

    context = {
        'records': records[:100],  # Show up to 100 recent
        'total_count': records.count(),
        'status_choices': HairCheckStatus.choices,
        'selected_status': status_filter,
        'current_ay': current_ay,
    }
    return render(request, 'discipline/hair_check_history.html', context)
