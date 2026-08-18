from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.academics.models import AcademicYear, Section
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.enrollment.services import PromotionService, AcademicYearRolloverService


@login_required
def academic_year_rollover_view(request):
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)

    if getattr(request.user, 'role', None) not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'REGISTRAR', 'PRINCIPAL']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    academic_years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')
    active_ay = academic_years.filter(is_active=True).first()
    
    source_ay_id = request.GET.get('source_ay_id') or (active_ay.id if active_ay else None)
    target_ay_id = request.GET.get('target_ay_id')

    source_ay = AcademicYear.objects.filter(id=source_ay_id, school=school).first() if source_ay_id else None
    target_ay = AcademicYear.objects.filter(id=target_ay_id, school=school).first() if target_ay_id else None

    preview_data = None
    if source_ay and target_ay:
        preview_data = AcademicYearRolloverService.preview_rollover(school, source_ay, target_ay)

    if request.method == 'POST':
        post_source_id = request.POST.get('source_ay_id')
        post_target_id = request.POST.get('target_ay_id')
        allocation_strategy = request.POST.get('allocation_strategy', 'BALANCED_CAPACITY')

        source_ay = get_object_or_404(AcademicYear, id=post_source_id, school=school)
        target_ay = get_object_or_404(AcademicYear, id=post_target_id, school=school)

        if source_ay == target_ay:
            messages.error(request, "Source and Target Academic Years must be different.")
            return redirect(request.path)

        try:
            res = AcademicYearRolloverService.execute_rollover(
                school=school,
                current_academic_year=source_ay,
                target_academic_year=target_ay,
                admin_user=request.user,
                default_allocation_strategy=allocation_strategy
            )
            messages.success(
                request,
                f"🎉 Academic Year Rollover Completed Successfully! Promoted {res['promoted_count']} students, "
                f"retained {res['retained_count']} students, and graduated {res['graduated_count']} seniors. "
                f"Active Academic Year is now set to {target_ay.name}."
            )
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Rollover Failed: {str(e)}")
            return redirect(request.path + f"?source_ay_id={source_ay.id}&target_ay_id={target_ay.id}")

    context = {
        'academic_years': academic_years,
        'source_ay': source_ay,
        'target_ay': target_ay,
        'preview_data': preview_data,
    }
    return render(request, 'enrollment/rollover_wizard.html', context)



@login_required
def bulk_promote_students_view(request):
    # Determine the school
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    # Only superadmin, school admin, registrar, or principal should access this
    if getattr(request.user, 'role', None) not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'REGISTRAR', 'PRINCIPAL']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    academic_years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')
    
    source_ay_id = request.GET.get('source_ay_id')
    source_section_id = request.GET.get('source_section_id')
    target_ay_id = request.GET.get('target_ay_id')
    target_section_id = request.GET.get('target_section_id')

    source_sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    if source_ay_id:
        from django.db.models import Count, Q
        source_sections = source_sections.annotate(
            enrolled_students_count=Count(
                'enrollments', 
                filter=Q(enrollments__academic_year_id=source_ay_id, enrollments__status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.PROMOTED])
            )
        )

    target_sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    students = []
    selected_source_sec = None

    if source_section_id:
        selected_source_sec = Section.objects.filter(id=source_section_id, school=school).select_related('grade').first()
        if selected_source_sec and selected_source_sec.grade.level < 12:
            target_sections = Section.objects.filter(
                school=school, grade__level=selected_source_sec.grade.level + 1
            ).select_related('grade', 'stream').order_by('grade__stream_type', 'name')

    if source_ay_id and source_section_id:
        students = StudentEnrollment.objects.filter(
            school=school,
            academic_year_id=source_ay_id,
            section_id=source_section_id,
            status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.PROMOTED]
        ).select_related('student', 'grade')

    if request.method == 'POST':
        selected_students = request.POST.getlist('students')
        target_ay_id = request.POST.get('target_ay_id')
        target_section_id = request.POST.get('target_section_id')
        
        if target_ay_id == 'None': target_ay_id = None
        if target_section_id == 'None': target_section_id = None

        target_ay = get_object_or_404(AcademicYear, id=target_ay_id, school=school) if target_ay_id else None
        target_section = Section.objects.filter(id=target_section_id, school=school).first() if target_section_id else None

        if selected_source_sec and selected_source_sec.grade.level < 12 and not target_section:
            messages.error(request, "Target Section (Grade level + 1) is required for promotion.")
            return redirect(request.path + '?' + request.META.get('QUERY_STRING', ''))

        success_count = 0
        grad_count = 0
        for enrollment_id in selected_students:
            try:
                enrollment = StudentEnrollment.objects.get(id=enrollment_id, school=school)
                PromotionService.promote_student(
                    school=school,
                    current_enrollment=enrollment,
                    next_academic_year=target_ay,
                    next_section=target_section,
                    promoted_by_user=request.user
                )
                if enrollment.grade.level >= 12:
                    grad_count += 1
                else:
                    success_count += 1
            except Exception as e:
                messages.error(request, f"Failed to promote {enrollment.student.full_name}: {str(e)}")

        if grad_count > 0:
            messages.success(request, f"Successfully graduated {grad_count} Grade 12 student(s)!")
        if success_count > 0:
            messages.success(request, f"Successfully promoted {success_count} student(s) to Grade {selected_source_sec.grade.level + 1}!")
        
        return redirect(request.path + f"?source_ay_id={source_ay_id}&source_section_id={source_section_id}")

    context = {
        'academic_years': academic_years,
        'source_ay_id': int(source_ay_id) if source_ay_id else None,
        'source_section_id': int(source_section_id) if source_section_id else None,
        'target_ay_id': int(target_ay_id) if target_ay_id else None,
        'target_section_id': int(target_section_id) if target_section_id else None,
        'source_sections': source_sections,
        'target_sections': target_sections,
        'students': students,
        'selected_source_sec': selected_source_sec,
    }
    
    return render(request, 'enrollment/promote_students.html', context)


@login_required
def period_close_wizard_view(request):
    """
    AcademicPeriod-Close Wizard:
    Step 1 (GET): Preview – show summary of marks status for selected period.
    Step 2 (POST confirm): Execute close – compute results, assign ranks, publish.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)

    if getattr(request.user, 'role', None) not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL']:
        messages.error(request, "Unauthorized access. Only Admin/Principal can close a period.")
        return redirect('index')

    from apps.academics.models import AcademicPeriod
    from apps.enrollment.services_period import AcademicPeriodCloseService

    current_ay = getattr(request, 'academic_year', None)
    periods = AcademicPeriod.objects.filter(school=school)
    if current_ay:
        periods = periods.filter(academic_year=current_ay)

    period_id = request.GET.get('period_id') or request.POST.get('period_id')
    selected_period = None
    preview = None

    if period_id:
        selected_period = get_object_or_404(AcademicPeriod, id=period_id, school=school)
        preview = AcademicPeriodCloseService.preview_period_close(selected_period, school)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'confirm_close' and selected_period:
            success, message, count = AcademicPeriodCloseService.execute_period_close(
                period=selected_period,
                school=school,
                published_by=request.user
            )
            if success:
                messages.success(request, message)
            else:
                messages.error(request, message)
            return redirect('enrollment:period_close')

    return render(request, 'enrollment/period_close.html', {
        'periods': periods,
        'selected_period': selected_period,
        'preview': preview,
        'current_ay': current_ay,
    })

