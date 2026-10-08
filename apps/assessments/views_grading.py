from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from decimal import Decimal

from apps.tenants.utils import get_school
from apps.accounts.models import UserRole
from apps.assessments.views import check_admin_access
from apps.academics.models import Grade
from apps.assessments.models import GradingScale, GradingScaleRule, GradingScaleType
from apps.audit.services import AuditService


@login_required
def grading_scale_list(request):
    """
    Dashboard for managing flexible grading systems, letter grade rules,
    pass/fail thresholds, and below-average/high-performance cutoffs.
    """
    school = get_school(request)
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access: Grading configuration is restricted to Administrators.")
        return redirect('assessments:components')

    scales = GradingScale.objects.filter(school=school).prefetch_related('rules').select_related('grade')
    if not scales.exists():
        GradingScale.create_default_ethiopian_scale(school)
        scales = GradingScale.objects.filter(school=school).prefetch_related('rules').select_related('grade')

    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')

    return render(request, 'assessments/grading_scales.html', {
        'scales': scales,
        'grades': grades,
        'GradingScaleType': GradingScaleType,
        'school': school,
    })


@login_required
def save_grading_scale(request):
    """Create or edit a GradingScale definition."""
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    scale_id = request.POST.get('scale_id')
    name = request.POST.get('name', '').strip()
    scale_type = request.POST.get('scale_type', GradingScaleType.NUMERICAL)
    grade_id = request.POST.get('grade_id') or None
    is_default = request.POST.get('is_default') == 'on' or request.POST.get('is_default') == 'true'
    min_pass = request.POST.get('min_passing_mark', '50.00')
    below_avg = request.POST.get('below_average_threshold', '60.00')
    high_perf = request.POST.get('high_performance_threshold', '90.00')

    grade = Grade.objects.filter(id=grade_id, school=school).first() if grade_id else None

    if is_default:
        # Unset previous default
        GradingScale.objects.filter(school=school, is_default=True).update(is_default=False)

    if scale_id:
        scale = get_object_or_404(GradingScale, id=scale_id, school=school)
        scale.name = name
        scale.scale_type = scale_type
        scale.grade = grade
        scale.is_default = is_default
        scale.min_passing_mark = Decimal(str(min_pass))
        scale.below_average_threshold = Decimal(str(below_avg))
        scale.high_performance_threshold = Decimal(str(high_perf))
        scale.save()
        msg = f"Grading scale '{scale.name}' updated successfully."
    else:
        scale = GradingScale.objects.create(
            school=school,
            name=name,
            scale_type=scale_type,
            grade=grade,
            is_default=is_default,
            min_passing_mark=Decimal(str(min_pass)),
            below_average_threshold=Decimal(str(below_avg)),
            high_performance_threshold=Decimal(str(high_perf)),
        )
        msg = f"New grading scale '{scale.name}' created."

    AuditService.log_action(
        school=school,
        user=request.user,
        action="GRADING_SCALE_SAVED",
        object_type="GradingScale",
        object_id=str(scale.id),
        after_val={'name': scale.name, 'scale_type': scale.scale_type},
        ip_address=AuditService.get_client_ip(request)
    )

    messages.success(request, msg)
    return redirect('assessments:grading_scales')


@login_required
def save_grading_rule(request):
    """Add or edit an individual grade rule (e.g. A+: 90-100%, 4.0 GPA)."""
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    scale_id = request.POST.get('scale_id')
    rule_id = request.POST.get('rule_id')
    scale = get_object_or_404(GradingScale, id=scale_id, school=school)

    letter_grade = request.POST.get('letter_grade', '').strip().upper()
    min_score = request.POST.get('min_score', '0.0')
    max_score = request.POST.get('max_score', '100.0')
    gpa_point = request.POST.get('gpa_point', '0.0')
    description = request.POST.get('description', '').strip()
    is_passing = request.POST.get('is_passing') == 'on' or request.POST.get('is_passing') == 'true'

    if rule_id:
        rule = get_object_or_404(GradingScaleRule, id=rule_id, school=school, scale=scale)
        rule.letter_grade = letter_grade
        rule.min_score = Decimal(str(min_score))
        rule.max_score = Decimal(str(max_score))
        rule.gpa_point = Decimal(str(gpa_point))
        rule.description = description
        rule.is_passing = is_passing
        rule.save()
        messages.success(request, f"Grade rule '{rule.letter_grade}' updated.")
    else:
        rule = GradingScaleRule.objects.create(
            school=school,
            scale=scale,
            letter_grade=letter_grade,
            min_score=Decimal(str(min_score)),
            max_score=Decimal(str(max_score)),
            gpa_point=Decimal(str(gpa_point)),
            description=description,
            is_passing=is_passing,
        )
        messages.success(request, f"New grade boundary '{rule.letter_grade}' added.")

    return redirect('assessments:grading_scales')


@login_required
def delete_grading_rule(request, rule_id):
    """Deletes an individual grade rule."""
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    rule = get_object_or_404(GradingScaleRule, id=rule_id, school=school)
    rule.delete()
    messages.success(request, "Grade rule deleted successfully.")
    return redirect('assessments:grading_scales')


@login_required
def set_default_grading_scale(request, scale_id):
    """Sets a grading scale as the school-wide default."""
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    scale = get_object_or_404(GradingScale, id=scale_id, school=school)
    GradingScale.objects.filter(school=school, is_default=True).update(is_default=False)
    scale.is_default = True
    scale.save(update_fields=['is_default'])

    messages.success(request, f"'{scale.name}' is now the default grading scale for {school.name}.")
    return redirect('assessments:grading_scales')
