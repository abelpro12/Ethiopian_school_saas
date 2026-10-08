from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from decimal import Decimal

from apps.tenants.utils import get_school
from apps.accounts.models import User, UserRole
from apps.assessments.views import check_admin_access, get_active_term
from apps.academics.models import Grade, Section, Subject, AcademicPeriod
from apps.assessments.models import (
    AcademicIntervention, InterventionType, InterventionStatus,
    AssessmentComponent, StudentMark, GradingScale
)
from apps.assessments.intervention_service import AcademicInterventionService
from apps.audit.services import AuditService


@login_required
def intervention_dashboard(request):
    """
    Executive Academic Performance Monitoring & Intervention Hub.
    Automatically detects below-average results (<60%), enables targeted
    interventions, tutorial enrollments, and parent SMS alerts.
    """
    school = get_school(request)
    ay, sem = get_active_term(request)

    grade_id = request.GET.get('grade_id')
    section_id = request.GET.get('section_id')
    subject_id = request.GET.get('subject_id')
    status_filter = request.GET.get('status')

    # Effective scale and thresholds
    scale = GradingScale.get_effective_scale(school)
    threshold = float(scale.below_average_threshold) if scale else 60.0
    high_threshold = float(scale.high_performance_threshold) if scale else 90.0

    # 1. Detected Below-Average Students
    below_avg_list = AcademicInterventionService.detect_below_average_students(
        school=school,
        period=sem,
        academic_year=ay,
        grade_id=int(grade_id) if grade_id else None,
        section_id=int(section_id) if section_id else None,
        subject_id=int(subject_id) if subject_id else None,
        threshold=threshold
    )

    # 2. Existing Interventions Query
    interventions_qs = AcademicIntervention.objects.filter(school=school).select_related(
        'student', 'subject', 'assessment_component', 'assigned_teacher', 'created_by', 'period'
    )
    if ay:
        interventions_qs = interventions_qs.filter(academic_year=ay)
    if grade_id:
        interventions_qs = interventions_qs.filter(enrollment__grade_id=grade_id)
    if section_id:
        interventions_qs = interventions_qs.filter(enrollment__section_id=section_id)
    if subject_id:
        interventions_qs = interventions_qs.filter(subject_id=subject_id)
    if status_filter:
        interventions_qs = interventions_qs.filter(status=status_filter)

    # High performance count (> 90%)
    high_perf_count = StudentMark.objects.filter(
        school=school,
        assessment_component__period=sem,
        mark_value__gte=Decimal(str(high_threshold))
    ).count() if sem else 0

    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    sections = Section.objects.filter(school=school).order_by('grade__level', 'name')
    subjects = Subject.objects.filter(school=school).order_by('name')
    teachers = User.objects.filter(school=school, role=UserRole.TEACHER).order_by('first_name', 'last_name')

    total_detected = len(below_avg_list)
    total_active_int = interventions_qs.filter(status__in=[InterventionStatus.IDENTIFIED, InterventionStatus.IN_PROGRESS]).count()
    total_resolved = interventions_qs.filter(status=InterventionStatus.RESOLVED).count()

    return render(request, 'assessments/intervention_dashboard.html', {
        'below_avg_list': below_avg_list,
        'interventions': interventions_qs[:100],
        'total_detected': total_detected,
        'total_active_int': total_active_int,
        'total_resolved': total_resolved,
        'high_perf_count': high_perf_count,
        'threshold': threshold,
        'high_threshold': high_threshold,
        'grades': grades,
        'sections': sections,
        'subjects': subjects,
        'teachers': teachers,
        'InterventionType': InterventionType,
        'InterventionStatus': InterventionStatus,
        'selected_grade_id': grade_id,
        'selected_section_id': section_id,
        'selected_subject_id': subject_id,
        'selected_status': status_filter,
        'ay': ay,
        'sem': sem,
    })


@login_required
def create_intervention_view(request):
    """POST endpoint to register an academic intervention."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    school = get_school(request)
    student_id = request.POST.get('student_id')
    enrollment_id = request.POST.get('enrollment_id')
    subject_id = request.POST.get('subject_id')
    component_id = request.POST.get('component_id') or None
    trigger_score = request.POST.get('trigger_score', '0.0')
    intervention_type = request.POST.get('intervention_type', InterventionType.TUTORIAL)
    action_plan = request.POST.get('action_plan', '').strip()
    scheduled_date = request.POST.get('scheduled_date') or None
    teacher_id = request.POST.get('assigned_teacher_id') or None
    notify_parent = request.POST.get('notify_parent') == 'on' or request.POST.get('notify_parent') == 'true'

    try:
        intervention = AcademicInterventionService.create_intervention(
            school=school,
            student_id=student_id,
            enrollment_id=int(enrollment_id),
            subject_id=int(subject_id),
            component_id=int(component_id) if component_id else None,
            trigger_score=float(trigger_score),
            intervention_type=intervention_type,
            action_plan=action_plan,
            scheduled_date=scheduled_date,
            assigned_teacher_id=int(teacher_id) if teacher_id else None,
            notify_parent=notify_parent,
            user=request.user,
            ip_address=AuditService.get_client_ip(request)
        )
        msg = f"Intervention registered for {intervention.student.full_name} ({intervention.get_intervention_type_display()})."
        if notify_parent:
            msg += " Parent SMS notification dispatched."
        messages.success(request, msg)
    except Exception as e:
        messages.error(request, f"Error creating intervention: {e}")

    referer = request.POST.get('referer') or request.META.get('HTTP_REFERER')
    return redirect(referer or 'assessments:interventions')


@login_required
def update_intervention_view(request, pk):
    """POST endpoint to update intervention status and record retest outcomes."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    school = get_school(request)
    status = request.POST.get('status')
    follow_up_date = request.POST.get('follow_up_date') or None
    follow_up_score = request.POST.get('follow_up_score')
    outcome_notes = request.POST.get('outcome_notes', '').strip()

    try:
        intervention = AcademicInterventionService.update_intervention(
            intervention_id=pk,
            school=school,
            status=status,
            follow_up_date=follow_up_date,
            follow_up_score=float(follow_up_score) if follow_up_score else None,
            outcome_notes=outcome_notes,
            user=request.user,
            ip_address=AuditService.get_client_ip(request)
        )
        messages.success(request, f"Intervention status updated: {intervention.get_status_display()}.")
    except Exception as e:
        messages.error(request, f"Error updating intervention: {e}")

    return redirect('assessments:interventions')


@login_required
def send_parent_sms_view(request, pk):
    """Sends / re-sends SMS reminder to the parent for an existing intervention."""
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    school = get_school(request)
    intervention = get_object_or_404(AcademicIntervention, id=pk, school=school)

    success = AcademicInterventionService.dispatch_parent_notification(intervention, school=school)
    if success:
        messages.success(request, f"SMS alert sent successfully to parent of {intervention.student.full_name}.")
    else:
        messages.warning(request, f"SMS dispatched in simulation/mock mode for {intervention.student.full_name}.")

    return redirect('assessments:interventions')
