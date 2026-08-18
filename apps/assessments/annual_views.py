from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Exists, OuterRef

from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Section, Subject
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import AcademicPeriodResult, AnnualResult, PromotionStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus

import json


def get_school(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)

def get_active_year(request, school):
    ay = getattr(request, 'academic_year', None)
    if not ay and school:
        ay = AcademicYear.objects.filter(school=school, is_active=True).first()
        if not ay:
            ay = AcademicYear.objects.filter(school=school).first()
    return ay

@login_required
def annual_dashboard(request):
    """
    Dashboard for Annual Promotion Engine.
    Lists sections to perform calculation or rollover.
    """
    school = get_school(request)
    active_year = get_active_year(request, school)
    
    locked_results = AnnualResult.objects.filter(
        enrollment__section=OuterRef('pk'),
        is_locked=True
    )
    
    sections = Section.objects.filter(school=school).select_related('grade').annotate(
        is_rolled_over=Exists(locked_results)
    ).order_by('grade__level', 'name')

    
    # Quick stats
    total_annual_results = AnnualResult.objects.filter(school=school, academic_year=active_year).count()
    promoted = AnnualResult.objects.filter(school=school, academic_year=active_year, promotion_status=PromotionStatus.PROMOTED).count()
    repeated = AnnualResult.objects.filter(school=school, academic_year=active_year, promotion_status=PromotionStatus.REPEATED).count()
    pending = AnnualResult.objects.filter(school=school, academic_year=active_year, promotion_status=PromotionStatus.PENDING_REVIEW).count()
    
    context = {
        'active_year': active_year,
        'sections': sections,
        'stats': {
            'total': total_annual_results,
            'promoted': promoted,
            'repeated': repeated,
            'pending': pending
        }
    }
    return render(request, 'assessments/annual_dashboard.html', context)


def perform_section_annual_calculation(school, section, active_year):
    """Internal helper to calculate annual results for a section."""

    enrollments = StudentEnrollment.objects.filter(section=section)
    if active_year and enrollments.filter(academic_year=active_year).exists():
        enrollments = enrollments.filter(academic_year=active_year)

    with transaction.atomic():
        for enrollment in enrollments:
            from apps.assessments.models import StudentMark
            period_results = AcademicPeriodResult.objects.filter(enrollment=enrollment)
            
            grade_subject_codes = set(Subject.objects.filter(school=school, grade=enrollment.grade).values_list('code', flat=True))
            subject_scores = {}

            if period_results.exists():
                for pr in period_results:
                    results_json = pr.formatted_results
                    for sub in results_json:
                        code = sub.get('code')
                        if grade_subject_codes and code not in grade_subject_codes:
                            continue
                        name = sub.get('name')
                        score = float(sub.get('normalized', sub.get('raw_score', 0)))
                        
                        if code not in subject_scores:
                            subject_scores[code] = {'name': name, 'scores': [], 'code': code}
                        subject_scores[code]['scores'].append(score)
            else:
                # Fallback directly to StudentMark entries for this enrollment
                student_marks = StudentMark.objects.filter(
                    enrollment=enrollment
                ).select_related('assessment_component__subject')

                by_subject = {}
                for m in student_marks:
                    comp = m.assessment_component
                    sub = comp.subject
                    if grade_subject_codes and sub.code not in grade_subject_codes:
                        continue
                    if sub.code not in by_subject:
                        by_subject[sub.code] = {'name': sub.name, 'code': sub.code, 'total_earned': 0.0, 'total_weight': 0.0}

                    max_m = float(comp.max_marks) if hasattr(comp, 'max_marks') and comp.max_marks and comp.max_marks > 0 else 100.0
                    weight = float(comp.weight) if hasattr(comp, 'weight') and comp.weight and comp.weight > 0 else 100.0
                    earned = (float(m.mark_value) / max_m) * weight
                    
                    by_subject[sub.code]['total_earned'] += earned
                    by_subject[sub.code]['total_weight'] += weight

                for code, sdata in by_subject.items():
                    if sdata['total_weight'] > 0:
                        final_score = (sdata['total_earned'] / sdata['total_weight']) * 100.0
                    else:
                        final_score = sdata['total_earned']
                    
                    subject_scores[code] = {
                        'name': sdata['name'],
                        'scores': [final_score],
                        'code': code
                    }

            # Calculate annual averages per subject
            annual_subject_results = []
            total_sum = 0
            math_score = 100
            english_score = 100
            
            for code, data in subject_scores.items():
                if data['scores']:
                    avg = sum(data['scores']) / len(data['scores'])
                else:
                    avg = 0
                
                annual_subject_results.append({
                    'code': code,
                    'name': data['name'],
                    'annual_average': round(avg, 2)
                })
                total_sum += avg
                
                # Check for Math or English specifically
                name_lower = data['name'].lower()
                if 'math' in name_lower:
                    math_score = avg
                if 'english' in name_lower:
                    english_score = avg
                    
            overall_average = (total_sum / len(annual_subject_results)) if annual_subject_results else 0
            
            # Apply Promotion Policy
            if enrollment.grade and enrollment.grade.level >= 12:
                status = PromotionStatus.PROMOTED  # Grade 12s force promote to Graduate
            elif overall_average < 50:
                status = PromotionStatus.REPEATED
            elif math_score < 50 or english_score < 50:
                status = PromotionStatus.PENDING_REVIEW
            else:
                status = PromotionStatus.PROMOTED
                
            # Calculate Annual Attendance
            annual_attendance = AttendanceRecord.objects.filter(
                school=school,
                student=enrollment.student,
                date__gte=active_year.gregorian_start_date if active_year else None,
                date__lte=active_year.gregorian_end_date if active_year else None
            ) if active_year and active_year.gregorian_start_date else []
            
            att_present = annual_attendance.filter(status=AttendanceStatus.PRESENT).count() if hasattr(annual_attendance, 'filter') else 0
            att_absent = annual_attendance.filter(status=AttendanceStatus.ABSENT).count() if hasattr(annual_attendance, 'filter') else 0
            att_late = annual_attendance.filter(status=AttendanceStatus.LATE).count() if hasattr(annual_attendance, 'filter') else 0
            
            AnnualResult.objects.update_or_create(
                school=school,
                enrollment=enrollment,
                academic_year=enrollment.academic_year or active_year,
                defaults={
                    'total_score': total_sum,
                    'average_score': overall_average,
                    'promotion_status': status,
                    'results_json': annual_subject_results,
                    'attendance_present': att_present,
                    'attendance_absent': att_absent,
                    'attendance_late': att_late
                }
            )


@login_required
def calculate_annual_results(request, section_id):
    """Calculates the annual result for all students in a section."""
    school = get_school(request)
    section = get_object_or_404(Section, id=section_id, school=school)
    active_year = get_active_year(request, school)
    
    if not active_year:
        messages.error(request, "No active academic year found.")
        return redirect('assessments:annual_dashboard')

    perform_section_annual_calculation(school, section, active_year)
    messages.success(request, f"Successfully calculated annual results for {section.name}.")
    return redirect('assessments:annual_review', section_id=section_id)



def sync_annual_result_promotion(result, new_status, admin_user=None):
    """
    Syncs manual promotion status overrides (e.g. resolving PENDING_REVIEW -> PROMOTED or REPEATED)
    with student enrollments for the target next Academic Year.
    """
    result.promotion_status = new_status
    result.save(update_fields=['promotion_status'])

    school = result.school
    current_ay = result.academic_year
    student = result.enrollment.student

    # Find the next academic year (either active target year or next chronological year)
    next_ay = AcademicYear.objects.filter(school=school, is_active=True).exclude(id=current_ay.id).first()
    if not next_ay:
        next_ay = AcademicYear.objects.filter(
            school=school, gregorian_start_date__gt=current_ay.gregorian_start_date
        ).order_by('gregorian_start_date').first()

    if not next_ay:
        next_ay = AcademicYear.objects.filter(school=school).exclude(id=current_ay.id).order_by('-gregorian_start_date').first()

    if not next_ay:
        return

    curr_enrollment = result.enrollment
    curr_grade = curr_enrollment.grade

    if new_status == PromotionStatus.PROMOTED:
        curr_enrollment.status = EnrollmentStatus.PROMOTED
        curr_enrollment.save(update_fields=['status'])

        if curr_grade and curr_grade.level >= 12:
            student.status = EnrollmentStatus.GRADUATED
            student.save(update_fields=['status'])
            StudentEnrollment.objects.filter(school=school, student=student, academic_year=next_ay).delete()
        else:
            next_grade = Grade.objects.filter(school=school, level__gt=curr_grade.level).order_by('level').first() if curr_grade else None
            if not next_grade:
                next_grade = curr_grade

            target_section = None
            if curr_enrollment.section:
                target_section = Section.objects.filter(
                    school=school, grade=next_grade, name=curr_enrollment.section.name
                ).first()
            if not target_section and next_grade:
                target_section = Section.objects.filter(school=school, grade=next_grade).first()

            if next_grade and not target_section:
                target_section, _ = Section.objects.get_or_create(
                    school=school, grade=next_grade, name="A", defaults={'capacity': 50}
                )

            if next_grade:
                StudentEnrollment.objects.update_or_create(
                    school=school,
                    student=student,
                    academic_year=next_ay,
                    defaults={
                        'grade': next_grade,
                        'stream': curr_enrollment.stream,
                        'section': target_section,
                        'status': EnrollmentStatus.ACTIVE,
                        'admission_type': curr_enrollment.admission_type
                    }
                )
                result.is_locked = True
                result.save(update_fields=['is_locked'])

    elif new_status == PromotionStatus.REPEATED:
        if curr_grade and curr_grade.level >= 12:
            # Grade 12s cannot repeat. Force graduate them instead.
            curr_enrollment.status = EnrollmentStatus.GRADUATED
            curr_enrollment.save(update_fields=['status'])
            StudentEnrollment.objects.filter(school=school, student=student, academic_year=next_ay).delete()
        else:
            curr_enrollment.status = EnrollmentStatus.RETAINED
            curr_enrollment.save(update_fields=['status'])

            target_grade = curr_grade
            target_section = curr_enrollment.section or Section.objects.filter(school=school, grade=target_grade).first()
            if target_grade and not target_section:
                target_section, _ = Section.objects.get_or_create(
                    school=school, grade=target_grade, name="A", defaults={'capacity': 50}
                )

            if target_grade:
                StudentEnrollment.objects.update_or_create(
                    school=school,
                    student=student,
                    academic_year=next_ay,
                    defaults={
                        'grade': target_grade,
                        'stream': curr_enrollment.stream,
                        'section': target_section,
                        'status': EnrollmentStatus.ACTIVE,
                        'admission_type': curr_enrollment.admission_type
                    }
                )
                result.is_locked = True
                result.save(update_fields=['is_locked'])

    elif new_status == PromotionStatus.PENDING_REVIEW:
        curr_enrollment.status = EnrollmentStatus.ACTIVE
        curr_enrollment.save(update_fields=['status'])
        StudentEnrollment.objects.filter(school=school, student=student, academic_year=next_ay).delete()


@login_required
def annual_review(request, section_id):
    """
    Displays the calculated annual results for a section and allows admins
    to manually override statuses (e.g. resolve PENDING_REVIEW).
    Synchronizes updated PROMOTED/REPEATED decisions with the next academic year enrollments ONLY if already rolled over.
    """
    school = get_school(request)
    section = get_object_or_404(Section, id=section_id, school=school)
    active_year = get_active_year(request, school)
    
    if request.method == 'POST':
        # Check if the section has already been rolled over
        section_rolled_over = AnnualResult.objects.filter(
            school=school, 
            academic_year=active_year, 
            enrollment__section=section, 
            is_locked=True
        ).exists()

        # Handle manual overrides
        updated_count = 0
        sync_count = 0
        for key, value in request.POST.items():
            if key.startswith('status_'):
                result_id = key.split('_')[1]
                res = AnnualResult.objects.filter(id=result_id, school=school).first()
                if res and res.promotion_status != value:
                    res.promotion_status = value
                    res.save(update_fields=['promotion_status'])
                    updated_count += 1
                    
                    # Synchronize to next year if the section was already rolled over
                    if section_rolled_over or res.is_locked:
                        sync_annual_result_promotion(res, value, admin_user=request.user)
                        sync_count += 1
                        
        messages.success(request, f"Manual overrides saved for {updated_count} student(s). (Synchronized {sync_count} students to next academic year).")
        return redirect('assessments:annual_review', section_id=section_id)
        
    results = AnnualResult.objects.filter(
        school=school, 
        enrollment__section=section
    ).order_by('-average_score')
    if active_year and results.filter(academic_year=active_year).exists():
        results = results.filter(academic_year=active_year)

    
    context = {
        'section': section,
        'active_year': active_year,
        'results': results,
        'PromotionStatus': PromotionStatus
    }
    return render(request, 'assessments/annual_review.html', context)


@login_required
def execute_rollover(request, section_id):
    """
    Generates new StudentEnrollments for the next academic year based on approved AnnualResults.
    PROMOTED -> Next grade (Unassigned section)
    REPEATED -> Same grade (Unassigned section)
    """
    school = get_school(request)
    section = get_object_or_404(Section, id=section_id, school=school)
    active_year = get_active_year(request, school)
    
    if request.method == 'POST':
        if section.grade.level >= 12:
            # Handle Grade 12 Graduation
            results = AnnualResult.objects.filter(
                school=school, 
                academic_year=active_year, 
                enrollment__section=section,
                is_locked=False
            )
            graduated_count = 0
            with transaction.atomic():
                for result in results:
                    result.is_locked = True
                    result.save(update_fields=['is_locked'])
                    curr_enrollment = result.enrollment
                    curr_enrollment.status = EnrollmentStatus.GRADUATED
                    curr_enrollment.save(update_fields=['status'])
                    graduated_count += 1
            messages.success(request, f"Successfully graduated {graduated_count} Grade 12 students.")
            return redirect('assessments:annual_dashboard')

        if section.grade.level == 10:
            # Handle Grade 10 Stream Selection requirement (Promoted, but manual stream registration for Grade 11)
            results = AnnualResult.objects.filter(
                school=school, 
                academic_year=active_year, 
                enrollment__section=section
            )
            processed_count = 0
            with transaction.atomic():
                for result in results:
                    result.is_locked = True
                    result.save(update_fields=['is_locked'])
                    curr_enrollment = result.enrollment
                    if result.promotion_status == PromotionStatus.PROMOTED:
                        curr_enrollment.status = EnrollmentStatus.PROMOTED
                    elif result.promotion_status == PromotionStatus.REPEATED:
                        curr_enrollment.status = EnrollmentStatus.RETAINED
                    curr_enrollment.save(update_fields=['status'])
                    processed_count += 1
            messages.success(request, f"Successfully processed promotion status for {processed_count} Grade 10 students. Students can now be enrolled in Grade 11 with their chosen stream during registration.")
            return redirect('assessments:annual_dashboard')

        next_year_id = request.POST.get('next_year_id')
        if not next_year_id:
            messages.error(request, "Please select the target academic year for rollover.")
            return redirect('assessments:annual_dashboard')
            
        try:
            target_section_count = int(request.POST.get('target_section_count', 1))
            if target_section_count < 1:
                target_section_count = 1
        except (ValueError, TypeError):
            target_section_count = 1
            
        next_year = get_object_or_404(AcademicYear, id=next_year_id, school=school)
        results = AnnualResult.objects.filter(
            school=school, 
            enrollment__section=section,
            promotion_status__in=[PromotionStatus.PROMOTED, PromotionStatus.REPEATED]
        )
        if active_year and results.filter(academic_year=active_year).exists():
            results = results.filter(academic_year=active_year)

        if not results.exists():
            perform_section_annual_calculation(school, section, active_year)
            results = AnnualResult.objects.filter(
                school=school, 
                enrollment__section=section,
                promotion_status__in=[PromotionStatus.PROMOTED, PromotionStatus.REPEATED]
            )
            if active_year and results.filter(academic_year=active_year).exists():
                results = results.filter(academic_year=active_year)


        
        created_count = 0
        with transaction.atomic():
            # Phase 1: Collect and group by target grade and stream
            placements = {}
            for result in results:
                current_grade = result.enrollment.grade
                curr_enrollment = result.enrollment
                
                if result.promotion_status == PromotionStatus.PROMOTED:
                    curr_enrollment.status = EnrollmentStatus.PROMOTED
                    curr_enrollment.save(update_fields=['status'])
                    
                    if current_grade.level == 10:
                        # Grade 10s moving to Grade 11 need a stream choice.
                        # Do NOT auto-enroll. Just lock the result.
                        result.is_locked = True
                        result.save(update_fields=['is_locked'])
                        continue
                        
                    next_level = current_grade.level + 1
                    next_grade = Grade.objects.filter(school=school, level=next_level).order_by('level').first()
                    if not next_grade:
                        next_grade, _ = Grade.objects.get_or_create(
                            school=school,
                            level=next_level,
                            defaults={
                                'name': f"Grade {next_level}",
                                'stream_type': 'GEN'
                            }
                        )

                else:
                    if current_grade.level >= 12:
                        continue # Grade 12s cannot repeat, skip creating next year enrollment
                    
                    curr_enrollment.status = EnrollmentStatus.RETAINED
                    curr_enrollment.save(update_fields=['status'])
                    next_grade = current_grade
                
                next_stream = result.enrollment.stream
                key = (next_grade, next_stream)
                if key not in placements:
                    placements[key] = []
                placements[key].append(result)
                
            # Phase 2: Distribute alphabetically and round-robin across available sections
            import string
            letters = list(string.ascii_uppercase)
            
            for (next_grade, next_stream), group_results in placements.items():
                # Sort alphabetically by student first name
                group_results.sort(key=lambda r: (r.enrollment.student.user.first_name, r.enrollment.student.user.last_name))
                
                # Get existing sections for this grade and stream
                existing_sections = list(Section.objects.filter(grade=next_grade, stream=next_stream).order_by('name'))
                sections = existing_sections[:target_section_count]
                
                # If we don't have enough sections, create them
                current_names = [s.name for s in existing_sections]
                while len(sections) < target_section_count:
                    # Find next available letter
                    new_name = None
                    for letter in letters:
                        if letter not in current_names:
                            new_name = letter
                            break
                    if not new_name:
                        new_name = f"Sec {len(sections) + 1}"
                        
                    new_sec, _ = Section.objects.get_or_create(
                        school=school, grade=next_grade, stream=next_stream, name=new_name, defaults={'capacity': 50}
                    )
                    sections.append(new_sec)
                    current_names.append(new_name)
                
                # Distribute students
                for i, result in enumerate(group_results):
                    next_section = sections[i % len(sections)]
                    
                    # Create next year enrollment
                    StudentEnrollment.objects.get_or_create(
                        school=school,
                        student=result.enrollment.student,
                        academic_year=next_year,
                        defaults={
                            'grade': next_grade,
                            'stream': next_stream,
                            'section': next_section,
                            'status': EnrollmentStatus.ACTIVE
                        }
                    )
                    created_count += 1
                    
                    # Mark result as locked/rolled over
                    result.is_locked = True
                    result.save(update_fields=['is_locked'])
            
            # Ensure all results for this section are locked so the dashboard badge updates
            AnnualResult.objects.filter(school=school, enrollment__section=section).update(is_locked=True)

                    
        messages.success(request, f"Rollover completed: Generated {created_count} enrollments for {next_year.display_name}. Students were automatically distributed across available sections.")
        return redirect('assessments:annual_dashboard')

    next_years = AcademicYear.objects.filter(school=school).exclude(id=active_year.id)
    return render(request, 'assessments/annual_rollover_modal.html', {'section': section, 'next_years': next_years})
