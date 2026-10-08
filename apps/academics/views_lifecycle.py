import json
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    PeriodStatus,
    SemesterArchive,
    PeriodType
)
from apps.academics.lifecycle_service import AcademicPeriodLifecycleService
from apps.academics.ethiopian_date import format_school_date, format_ethiopian_date
from apps.assessments.models import AcademicPeriodResult


def _get_active_school(request):
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school and (request.user.is_superuser or getattr(request.user, 'role', None) == 'SUPER_ADMIN'):
        from apps.schools.models import School
        active_code = request.session.get('active_school_code', 'SEA')
        school = School.objects.filter(code=active_code).first() or School.objects.first()
    return school


def _can_manage_lifecycle(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, 'role', None) in [
        UserRole.SUPER_ADMIN,
        UserRole.SCHOOL_ADMIN,
        UserRole.PRINCIPAL,
        UserRole.REGISTRAR,
        'ACADEMIC_DIRECTOR'
    ]


@login_required
def semester_lifecycle_dashboard(request):
    """
    Command Center for Term/Semester Lifecycle Management.
    Displays active term status, lock states, transition wizards,
    supplementary exam schedules, and historical snapshot archives.
    """
    if not _can_manage_lifecycle(request.user):
        messages.error(request, "Access restricted to School Administration.")
        return redirect('index')

    school = _get_active_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('index')

    # Selected or active academic year
    ay_id = request.GET.get('academic_year_id')
    current_ay = None
    if ay_id:
        current_ay = AcademicYear.objects.filter(school=school, id=ay_id).first()
    if not current_ay:
        current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
        if not current_ay:
            current_ay = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year').first()

    academic_years = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year')

    periods_data = []
    active_period = None
    if current_ay:
        periods = AcademicPeriod.objects.filter(school=school, academic_year=current_ay).order_by('start_date')
        for p in periods:
            if p.is_current:
                active_period = p

            results_count = AcademicPeriodResult.objects.filter(school=school, period=p).count()
            has_archive = SemesterArchive.objects.filter(school=school, period=p).exists()

            periods_data.append({
                'period': p,
                'eth_start': format_ethiopian_date(p.start_date),
                'eth_end': format_ethiopian_date(p.end_date),
                'results_count': results_count,
                'has_archive': has_archive,
            })

    # Historical Archives
    archives = SemesterArchive.objects.filter(school=school).select_related('period', 'academic_year', 'archived_by').order_by('-archived_at')

    return render(request, 'academics/semester_lifecycle.html', {
        'school': school,
        'current_ay': current_ay,
        'academic_years': academic_years,
        'periods_data': periods_data,
        'active_period': active_period,
        'archives': archives,
        'period_types': PeriodType.choices,
        'period_statuses': PeriodStatus.choices,
    })


@login_required
@require_POST
def set_active_semester_view(request, period_id):
    """POST action to designate active semester."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)

    res = AcademicPeriodLifecycleService.set_active_semester(period, user=request.user)
    if res.get('success'):
        messages.success(request, res['message'])
    else:
        messages.error(request, res.get('error', 'Failed to activate semester.'))

    return redirect(f"{request.META.get('HTTP_REFERER') or '/academics/lifecycle/'}")


@login_required
@require_POST
def lock_semester_view(request, period_id):
    """POST action to lock a semester."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)
    reason = request.POST.get('reason', '').strip()

    res = AcademicPeriodLifecycleService.lock_semester(period, user=request.user, reason=reason)
    messages.success(request, res['message'])
    return redirect(f"{request.META.get('HTTP_REFERER') or '/academics/lifecycle/'}")


@login_required
@require_POST
def reopen_semester_view(request, period_id):
    """POST action to reopen a locked/closed semester with mandatory reason."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)
    reason = request.POST.get('reason', '').strip()

    res = AcademicPeriodLifecycleService.reopen_semester(period, user=request.user, reason=reason)
    if res.get('success'):
        messages.success(request, res['message'])
    else:
        messages.error(request, res.get('error', 'Failed to reopen semester.'))

    return redirect(f"{request.META.get('HTTP_REFERER') or '/academics/lifecycle/'}")


@login_required
@require_POST
def close_and_archive_semester_view(request, period_id):
    """POST action to run end-of-term calculation, lock period, and generate archive."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)
    notes = request.POST.get('notes', '').strip()

    res = AcademicPeriodLifecycleService.execute_semester_close_workflow(
        period=period,
        user=request.user,
        notes=notes
    )

    if res.get('success'):
        messages.success(request, res['message'])
    else:
        messages.error(request, res.get('error', 'Failed to close semester.'))

    return redirect(f"{request.META.get('HTTP_REFERER') or '/academics/lifecycle/'}")


@login_required
@require_POST
def rollover_semester_view(request):
    """POST action to transition from one semester to another."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    curr_id = request.POST.get('current_period_id')
    next_id = request.POST.get('next_period_id')

    if not curr_id or not next_id:
        messages.error(request, "Both current and next semester must be selected for rollover.")
        return redirect('academics:semester_lifecycle')

    current_period = get_object_or_404(AcademicPeriod, id=curr_id, school=school)
    next_period = get_object_or_404(AcademicPeriod, id=next_id, school=school)

    res = AcademicPeriodLifecycleService.transition_to_next_semester(
        current_period=current_period,
        next_period=next_period,
        user=request.user
    )

    if res.get('success'):
        messages.success(request, res['message'])
    else:
        messages.error(request, res.get('error', 'Rollover failed.'))

    return redirect('academics:semester_lifecycle')


@login_required
@require_POST
def schedule_supplementary_view(request, period_id):
    """POST action to schedule supplementary examination window."""
    if not _can_manage_lifecycle(request.user):
        return HttpResponseForbidden("Permission denied.")

    school = _get_active_school(request)
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)
    start_date = request.POST.get('supplementary_start_date')
    end_date = request.POST.get('supplementary_end_date')

    if not start_date or not end_date:
        messages.error(request, "Both start date and end date are required for supplementary exams.")
        return redirect('academics:semester_lifecycle')

    res = AcademicPeriodLifecycleService.configure_supplementary_exams(
        period=period,
        start_date=start_date,
        end_date=end_date,
        user=request.user
    )

    if res.get('success'):
        messages.success(request, res['message'])
    else:
        messages.error(request, res.get('error', 'Failed to schedule supplementary exams.'))

    return redirect('academics:semester_lifecycle')


@login_required
def archive_detail_json_view(request, archive_id):
    """Returns JSON snapshot payload of a historical semester archive."""
    school = _get_active_school(request)
    archive = get_object_or_404(SemesterArchive, id=archive_id, school=school)

    return JsonResponse({
        'id': archive.id,
        'period_name': archive.period.name,
        'academic_year': archive.academic_year.name,
        'archived_at': archive.archived_at.strftime('%Y-%m-%d %H:%M'),
        'archived_by': archive.archived_by.username if archive.archived_by else 'Admin',
        'total_students': archive.total_students,
        'passed_students': archive.passed_students,
        'failed_students': archive.failed_students,
        'overall_average': float(archive.overall_average),
        'notes': archive.notes or '',
        'snapshot_data': archive.snapshot_data or {}
    })
