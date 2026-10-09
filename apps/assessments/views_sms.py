import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.views.decorators.http import require_POST

from apps.accounts.models import User, UserRole
from apps.academics.models import Grade, Section, Subject, AcademicYear, AcademicPeriod
from apps.assessments.models import AssessmentComponent, StudentMark
from apps.assessments.views import get_school, get_active_term, check_admin_access
from apps.communication.models import SMSTemplate, SMSTemplateType, ExamResultSMSLog
from apps.communication.services import ExamResultSMSService, ensure_default_sms_templates
from apps.teachers.models import TeacherAssignment
from apps.audit.services import AuditService


def check_can_dispatch_sms(user, section=None, subject=None, school=None):
    """
    Checks if user is authorized to dispatch SMS for the given class/subject.
    Admins/Principals/Registrars have global permissions; teachers can dispatch for assigned classes.
    """
    if user.is_superuser or user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        return True
    if user.role == UserRole.TEACHER:
        if not section or not subject or not school:
            return True  # Allow accessing dashboard, per-action checks will validate
        return TeacherAssignment.objects.filter(
            school=school, teacher__user=user, section=section, subject=subject
        ).exists()
    return False


@login_required
def exam_results_sms_dashboard(request):
    """
    Dedicated Exam & Test Results SMS Dispatcher Center.
    Allows administrators and teachers to select any test/assessment (e.g. Test 1, Midterm Exam),
    review student scores and parent contact details, preview bilingual SMS messages, and
    dispatch with one click.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('index')

    if not check_can_dispatch_sms(request.user):
        messages.error(request, "Unauthorized access to SMS Results Center.")
        return redirect('assessments:mark_entry')

    ensure_default_sms_templates(school)
    ay, sem = get_active_term(request)

    # Filter parameters
    grade_id = request.GET.get('grade_id') or ''
    section_id = request.GET.get('section_id') or ''
    subject_id = request.GET.get('subject_id') or ''
    component_id = request.GET.get('component_id') or ''

    # Teacher assignment restrictions
    teacher_assignments = None
    if request.user.role == UserRole.TEACHER:
        teacher_assignments = TeacherAssignment.objects.filter(
            school=school, teacher__user=request.user
        ).select_related('section__grade', 'subject')

    # Available Grades
    grades = Grade.objects.filter(school=school).order_by('level', 'name')
    if teacher_assignments:
        assigned_grade_ids = teacher_assignments.values_list('section__grade_id', flat=True).distinct()
        grades = grades.filter(id__in=assigned_grade_ids)

    # Available Sections
    sections = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name')
    if grade_id:
        sections = sections.filter(grade_id=grade_id)
    if teacher_assignments:
        assigned_section_ids = teacher_assignments.values_list('section_id', flat=True).distinct()
        sections = sections.filter(id__in=assigned_section_ids)

    # Available Subjects
    subjects = Subject.objects.filter(school=school).order_by('name')
    if grade_id:
        subjects = subjects.filter(Q(grade_id=grade_id) | Q(grade__isnull=True))
    if teacher_assignments:
        assigned_subj_ids = teacher_assignments.values_list('subject_id', flat=True).distinct()
        subjects = subjects.filter(id__in=assigned_subj_ids)

    # Available Assessment Components (e.g. Test 1, Midterm Exam, Quiz 1, Final Exam)
    components_qs = AssessmentComponent.objects.filter(school=school)
    if ay:
        components_qs = components_qs.filter(academic_year=ay)
    if sem:
        components_qs = components_qs.filter(period=sem)
    if subject_id:
        components_qs = components_qs.filter(subject_id=subject_id)
    elif grade_id:
        components_qs = components_qs.filter(subject__grade_id=grade_id)

    components = components_qs.select_related('subject__grade').order_by('subject__name', 'name')

    selected_component = None
    selected_section = None
    selected_subject = None
    recipients = []
    stats = {
        'total_students': 0,
        'with_marks': 0,
        'with_phone': 0,
        'already_sent': 0,
    }

    if component_id:
        selected_component = components_qs.filter(id=component_id).select_related('subject', 'period').first()
        if selected_component:
            selected_subject = selected_component.subject
            if not subject_id and selected_subject:
                subject_id = str(selected_subject.id)

    if section_id:
        selected_section = sections.filter(id=section_id).first()

    # If component is chosen, prepare data
    if selected_component:
        recipients = ExamResultSMSService.get_component_results_for_dispatch(
            school=school,
            component=selected_component,
            section=selected_section
        )
        stats['total_students'] = len(recipients)
        stats['with_marks'] = sum(1 for r in recipients if r['has_mark'])
        stats['with_phone'] = sum(1 for r in recipients if r['has_phone'])
        stats['already_sent'] = sum(1 for r in recipients if r['already_sent'])

    # Default template preview
    template = SMSTemplate.objects.filter(school=school, template_type=SMSTemplateType.EXAM_RESULT, is_active=True).first()
    template_body_en = template.body_en if template else "Dear Parent, {student_name} scored {score}/{max_score} ({percentage}%) in {subject_name} ({test_name}) at {school_name}. Grade: {grade_letter}. Thank you."
    template_body_am = template.body_am if template else "ክቡር ወላጅ፣ {student_name} በ {subject_name} ({test_name}) ፈተና {score}/{max_score} ({percentage}%) በ {school_name} አስመዝግቧል/ለች:: ደረጃ: {grade_letter}:: እናመሰግናለን::"

    # Recent dispatches log
    recent_logs = ExamResultSMSLog.objects.filter(school=school).select_related(
        'student', 'parent__user', 'assessment_component__subject', 'sent_by'
    ).order_by('-sent_at')[:20]

    return render(request, 'assessments/exam_results_sms.html', {
        'school': school,
        'ay': ay,
        'sem': sem,
        'grades': grades,
        'sections': sections,
        'subjects': subjects,
        'components': components,
        'selected_grade_id': grade_id,
        'selected_section_id': section_id,
        'selected_subject_id': subject_id,
        'selected_component_id': component_id,
        'selected_component': selected_component,
        'selected_section': selected_section,
        'selected_subject': selected_subject,
        'recipients': recipients,
        'stats': stats,
        'template_body_en': template_body_en,
        'template_body_am': template_body_am,
        'recent_logs': recent_logs,
    })


@login_required
@require_POST
def exam_results_sms_send_api(request):
    """
    POST API to dispatch exam results via SMS to parents.
    Supports sending to all students in class or a selected subset.
    """
    school = get_school(request)
    if not school:
        return JsonResponse({'success': False, 'error': 'School context missing.'}, status=400)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except Exception:
        data = request.POST

    component_id = data.get('component_id')
    section_id = data.get('section_id')
    student_ids_raw = data.get('student_ids')
    custom_message = data.get('custom_message', '').strip()
    lang = data.get('lang', 'pref')  # 'am', 'en', or 'pref'

    if not component_id:
        return JsonResponse({'success': False, 'error': 'Assessment component / Test ID is required.'}, status=400)

    component = get_object_or_404(AssessmentComponent, id=component_id, school=school)
    section = Section.objects.filter(id=section_id, school=school).first() if section_id else None

    # Permission verification
    if not check_can_dispatch_sms(request.user, section=section, subject=component.subject, school=school):
        return JsonResponse({'success': False, 'error': 'You do not have permission to dispatch SMS for this subject/section.'}, status=403)

    student_ids = None
    if student_ids_raw:
        if isinstance(student_ids_raw, str):
            student_ids = [s.strip() for s in student_ids_raw.split(',') if s.strip()]
        elif isinstance(student_ids_raw, list):
            student_ids = [str(s).strip() for s in student_ids_raw if str(s).strip()]

    summary = ExamResultSMSService.bulk_dispatch_results(
        school=school,
        component=component,
        section=section,
        student_ids=student_ids,
        custom_message=custom_message if custom_message else None,
        lang_override=lang,
        sender_user=request.user
    )

    msg = f"Dispatched {summary['dispatched']} SMS alert{'s' if summary['dispatched'] != 1 else ''} to parents for '{component.name}'."
    if summary['skipped_no_phone'] > 0:
        msg += f" ({summary['skipped_no_phone']} skipped due to missing parent phone number)."
    if summary['failed'] > 0:
        msg += f" ({summary['failed']} failed)."

    return JsonResponse({
        'success': True,
        'message': msg,
        'summary': summary
    })


@login_required
def exam_results_sms_preview_modal_api(request, component_id, section_id):
    """
    JSON API returning student marks, parent details, and rendered messages for the Gradebook modal.
    Enables instant one-click 'Send Test 1 SMS' right inside the Mark Entry Grid without full page reload.
    """
    school = get_school(request)
    if not school:
        return JsonResponse({'success': False, 'error': 'School context missing.'}, status=400)

    component = get_object_or_404(AssessmentComponent, id=component_id, school=school)
    section = get_object_or_404(Section, id=section_id, school=school)

    if not check_can_dispatch_sms(request.user, section=section, subject=component.subject, school=school):
        return JsonResponse({'success': False, 'error': 'Unauthorized.'}, status=403)

    recipients = ExamResultSMSService.get_component_results_for_dispatch(
        school=school,
        component=component,
        section=section
    )

    stats = {
        'total': len(recipients),
        'with_marks': sum(1 for r in recipients if r['has_mark']),
        'with_phone': sum(1 for r in recipients if r['has_phone']),
        'already_sent': sum(1 for r in recipients if r['already_sent']),
    }

    # Fetch default template
    template = SMSTemplate.objects.filter(school=school, template_type=SMSTemplateType.EXAM_RESULT, is_active=True).first()
    template_body_en = template.body_en if template else "Dear Parent, {student_name} scored {score}/{max_score} ({percentage}%) in {subject_name} ({test_name}) at {school_name}. Grade: {grade_letter}. Thank you."
    template_body_am = template.body_am if template else "ክቡር ወላጅ፣ {student_name} በ {subject_name} ({test_name}) ፈተና {score}/{max_score} ({percentage}%) በ {school_name} አስመዝግቧል/ለች:: ደረጃ: {grade_letter}:: እናመሰግናለን::"

    return JsonResponse({
        'success': True,
        'component': {
            'id': component.id,
            'name': component.name,
            'max_marks': float(component.max_marks or 100.0),
            'weight': float(component.weight or 0.0),
            'subject_name': component.subject.name if component.subject else 'Subject',
            'grade_name': section.grade.name if section.grade else '',
            'section_name': section.name,
        },
        'stats': stats,
        'template_body_en': template_body_en,
        'template_body_am': template_body_am,
        'recipients': recipients
    })


@login_required
def exam_results_sms_history(request):
    """
    Audit and history view of all exam result SMS dispatches across the school.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('index')

    if not check_can_dispatch_sms(request.user):
        messages.error(request, "Unauthorized.")
        return redirect('assessments:mark_entry')

    logs_qs = ExamResultSMSLog.objects.filter(school=school).select_related(
        'student', 'parent__user', 'assessment_component__subject', 'sent_by'
    ).order_by('-sent_at')

    # Status / search filter
    status = request.GET.get('status')
    if status:
        logs_qs = logs_qs.filter(status=status)

    q = request.GET.get('q', '').strip()
    if q:
        logs_qs = logs_qs.filter(
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q) |
            Q(student__student_id__icontains=q) |
            Q(recipient_phone__icontains=q) |
            Q(assessment_component__name__icontains=q)
        )

    return render(request, 'assessments/exam_results_sms_history.html', {
        'school': school,
        'logs': logs_qs[:200],
        'total_count': logs_qs.count(),
        'selected_status': status,
        'query': q,
    })
