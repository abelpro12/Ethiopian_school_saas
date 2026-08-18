from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from apps.students.models import StudentProfile, StudentApplication, ApplicationStatus, StudentStatus
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark, MarkStatus, AcademicPeriodResult
from apps.academics.models import Section
from apps.rankings.models import StudentRanking
from apps.communication.models import Announcement
from apps.documents.models import SchoolDocument
from apps.library.models import BorrowRecord


@login_required
def student_dashboard_view(request):
    """
    Student Portal Dashboard.
    Displays published/authorized marks, attendance, section ranking, timetable, announcements.
    """
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    user = request.user
    student_id = request.GET.get('student_id')

    if student_id and getattr(user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'TEACHER', 'REGISTRAR']:
        try:
            student = StudentProfile.objects.get(id=student_id, school=school)
        except (StudentProfile.DoesNotExist, ValueError):
            student = None
    else:
        try:
            student = StudentProfile.objects.get(user=user, school=school)
        except StudentProfile.DoesNotExist:
            if getattr(user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']:
                student = StudentProfile.objects.filter(school=school).first()
            else:
                student = None

    if not student and getattr(user, 'role', None) not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']:
        messages.error(request, "Student profile not found.")
        return redirect('index')

    from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
    from apps.academics.models import TimetableSlot, AcademicYear

    current_ay = getattr(request, 'academic_year', None)
    if not current_ay and school:
        current_ay = AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date').first()

    # Current Enrollment (Active Academic Year Only)
    enrollment_qs = StudentEnrollment.objects.filter(school=school, student=student)
    if current_ay:
        active_enrollment = enrollment_qs.filter(academic_year=current_ay).select_related('section', 'grade', 'stream', 'academic_year').first()
    else:
        active_enrollment = enrollment_qs.filter(status=EnrollmentStatus.ACTIVE).select_related('section', 'grade', 'stream', 'academic_year').first()

    target_ay = current_ay or (active_enrollment.academic_year if active_enrollment else None)

    # All student marks assigned by teachers for ACTIVE academic year ONLY
    published_marks = StudentMark.objects.filter(
        school=school,
        enrollment__student=student
    ).select_related('assessment_component__subject', 'assessment_component__period').order_by('-created_at')
    
    if target_ay:
        published_marks = published_marks.filter(
            Q(enrollment__academic_year=target_ay) | Q(assessment_component__academic_year=target_ay)
        )

    from apps.academics.models import AcademicPeriod
    period_qs = AcademicPeriod.objects.filter(school=school)
    if target_ay:
        period_qs = period_qs.filter(academic_year=target_ay)
    period_list = list(period_qs.order_by('-start_date'))

    published_statuses = {'PUBLISHED', 'APPROVED', 'LOCKED'}
    subject_list = []
    seen_subjects = set()

    for m in published_marks:
        sub = m.assessment_component.subject
        if sub and sub.id not in seen_subjects:
            seen_subjects.add(sub.id)
            subject_list.append(sub)

    period_marks_groups = []
    processed_mark_ids = set()

    for period in period_list:
        p_marks = [m for m in published_marks if m.assessment_component.period_id == period.id]
        if not p_marks:
            continue

        for m in p_marks:
            processed_mark_ids.add(m.id)

        subject_marks_dict = {}
        for m in p_marks:
            sub = m.assessment_component.subject
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

        sub_summary_list = []
        for sub_id, data in subject_marks_dict.items():
            tot = round(data['total_score'], 2)
            max_tot = round(data['max_total'], 2) if data['max_total'] > 0 else 100.0
            pct = round((tot / max_tot * 100), 1) if max_tot > 0 else tot
            
            if pct >= 90: letter = 'A+'
            elif pct >= 83: letter = 'A'
            elif pct >= 75: letter = 'B'
            elif pct >= 65: letter = 'C'
            elif pct >= 50: letter = 'D'
            else: letter = 'F'

            marks_statuses = [m.status for m in data['marks']]
            is_published = len(marks_statuses) > 0 and all(st in published_statuses for st in marks_statuses)

            sub_summary_list.append({
                'subject': data['subject'],
                'marks': data['marks'],
                'total_score': tot,
                'max_total': max_tot,
                'percentage': pct,
                'letter_grade': letter,
                'count': data['count'],
                'is_published': is_published,
            })

        period_marks_groups.append({
            'period': period,
            'subject_summaries': sub_summary_list,
            'all_marks': p_marks
        })

    # Catch any remaining marks with missing or unlisted period
    other_marks = [m for m in published_marks if m.id not in processed_mark_ids]
    if other_marks:
        sub_dict_other = {}
        for m in other_marks:
            sub = m.assessment_component.subject
            if sub.id not in sub_dict_other:
                sub_dict_other[sub.id] = {'subject': sub, 'marks': [], 'total_score': 0.0, 'max_total': 0.0, 'count': 0}
            try:
                val = float(m.mark_value)
                mx = float(m.assessment_component.max_marks)
            except (ValueError, TypeError):
                val = 0.0; mx = 100.0
            sub_dict_other[sub.id]['marks'].append(m)
            sub_dict_other[sub.id]['total_score'] += val
            sub_dict_other[sub.id]['max_total'] += mx
            sub_dict_other[sub.id]['count'] += 1

        sub_sum_other = []
        for sub_id, data in sub_dict_other.items():
            tot = round(data['total_score'], 2)
            max_tot = round(data['max_total'], 2) if data['max_total'] > 0 else 100.0
            pct = round((tot / max_tot * 100), 1) if max_tot > 0 else tot
            if pct >= 90: letter = 'A+'
            elif pct >= 83: letter = 'A'
            elif pct >= 75: letter = 'B'
            elif pct >= 65: letter = 'C'
            elif pct >= 50: letter = 'D'
            else: letter = 'F'
            sub_sum_other.append({
                'subject': data['subject'], 'marks': data['marks'], 'total_score': tot,
                'max_total': max_tot, 'percentage': pct, 'letter_grade': letter,
                'count': data['count'], 'is_published': False
            })

        class DummyPeriod:
            name = "Other / Unassigned"
            is_current = False
            academic_year = None
        period_marks_groups.append({
            'period': DummyPeriod(),
            'subject_summaries': sub_sum_other,
            'all_marks': other_marks
        })

    # Ranking for active academic year only
    ranking_qs = StudentRanking.objects.filter(school=school, student=student)
    if target_ay:
        ranking_qs = ranking_qs.filter(academic_year=target_ay)
    ranking = ranking_qs.order_by('-id').first()
    rank_display = ranking.section_rank if ranking else "Not Computed"

    # Attendance for active academic year only
    attendance_qs = AttendanceRecord.objects.filter(school=school, student=student)
    if target_ay:
        attendance_qs = attendance_qs.filter(date__gte=target_ay.gregorian_start_date, date__lte=target_ay.gregorian_end_date)
    total_days = attendance_qs.count()
    absent_count = attendance_qs.filter(status='ABSENT').count()
    present_count = attendance_qs.filter(status='PRESENT').count()
    late_count = attendance_qs.filter(status='LATE').count()
    attendance_records = attendance_qs.order_by('-date')[:10]

    attendance_percentage = round(((present_count + late_count) / total_days * 100), 1) if total_days > 0 else 100.0

    # Timetable
    timetable_slots = []
    if active_enrollment and active_enrollment.section:
        timetable_slots = TimetableSlot.objects.filter(
            school=school,
            section=active_enrollment.section
        ).select_related('subject', 'period_slot', 'teacher__user').order_by('day_of_week', 'period_slot__start_time')

    # Announcements
    announcements = Announcement.objects.filter(
        school=school
    ).filter(
        target_type__in=['SCHOOL', 'STUDENTS']
    ).order_by('-created_at')[:5]

    # Library active borrows
    try:
        from apps.library.models import BorrowRecord
        active_borrows = BorrowRecord.objects.filter(
            school=school,
            borrower_student=student,
            return_date__isnull=True
        ).select_related('book_copy__book')
    except Exception:
        active_borrows = []

    # Active Academic Year Enrollment Details Only (No Past Years)
    all_enrollments = StudentEnrollment.objects.filter(
        school=school, student=student
    ).select_related('academic_year', 'grade', 'stream', 'section', 'promotion_decision')
    if target_ay:
        all_enrollments = all_enrollments.filter(academic_year=target_ay)

    # Official Computed & Published Evaluation Period Results / Report Cards (Active Academic Year Only)
    period_results_qs = AcademicPeriodResult.objects.filter(
        school=school,
        enrollment__student=student,
        is_published=True
    ).select_related('period', 'period__academic_year').order_by('-period__academic_year__gregorian_start_date', '-period__start_date')
    if target_ay:
        period_results_qs = period_results_qs.filter(period__academic_year=target_ay)

    all_students = []
    if getattr(user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR', 'TEACHER']:
        all_students = StudentProfile.objects.filter(school=school).select_related('user')[:200]

    return render(request, 'students/student_portal.html', {
        'student': student,
        'all_students': all_students,
        'enrollment': active_enrollment,
        'all_enrollments': all_enrollments,
        'published_marks': published_marks,
        'period_marks_groups': period_marks_groups,
        'period_list': period_list,
        'period_results': period_results_qs,
        'subject_list': subject_list,
        'rank_display': rank_display,
        'attendance_records': attendance_records,
        'total_days': total_days,
        'absent_count': absent_count,
        'present_count': present_count,
        'late_count': late_count,
        'attendance_percentage': attendance_percentage,
        'timetable_slots': timetable_slots,
        'announcements': announcements,
        'active_borrows': active_borrows,
    })


@login_required
def admissions_dashboard(request):
    """
    Dashboard for admission officers to review new student applications.
    """
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school
        
    applications = StudentApplication.objects.filter(school=school).order_by('-created_at')
    
    return render(request, 'students/admissions_dashboard.html', {
        'applications': applications,
    })

@login_required
def review_application(request, application_id):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school
        
    application = get_object_or_404(StudentApplication, id=application_id, school=school)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'accept':
            application.status = ApplicationStatus.ACCEPTED
            application.reviewed_by = request.user
            application.save()
            messages.success(request, f"Application {application.application_number} approved!")
            return redirect('students:review_application', application_id=application.id)
        elif action == 'reject':
            application.status = ApplicationStatus.REJECTED
            application.reviewed_by = request.user
            application.save()
            messages.info(request, f"Application {application.application_number} rejected.")
            return redirect('students:review_application', application_id=application.id)
        elif action == 'register':
            from apps.accounts.models import User, UserRole
            from apps.parents.models import ParentProfile, GuardianRelationship
            from apps.academics.models import Section, AcademicYear
            from apps.enrollment.models import StudentEnrollment, EnrollmentStatus

            st_id = request.POST.get('student_id', f"STU-{application.school.code}-{application.id}").strip()
            sec_id = request.POST.get('section_id')
            parent_option = request.POST.get('parent_option', 'new')
            existing_parent_id = request.POST.get('existing_parent_id')
            parent_phone = request.POST.get('parent_phone', '').strip()
            parent_relationship = request.POST.get('parent_relationship', 'Father')

            # Create Student User — generate a secure random initial password
            import secrets
            student_initial_pwd = secrets.token_urlsafe(10)

            student_user, student_created = User.objects.get_or_create(
                username=st_id.lower(),
                defaults={'school': school, 'role': UserRole.STUDENT, 'first_name': application.first_name, 'last_name': application.last_name}
            )
            student_user.school = school
            student_user.role = UserRole.STUDENT
            if student_created:
                student_user.set_password(student_initial_pwd)
                student_user.must_change_password = True
            student_user.save()

            student, _ = StudentProfile.objects.get_or_create(
                user=student_user,
                defaults={
                    'school': school,
                    'student_id': st_id,
                    'first_name': application.first_name,
                    'middle_name': application.middle_name,
                    'last_name': application.last_name,
                    'gender': application.gender
                }
            )
            student.save()

            # Parent Linking / Account Creation
            parent_profile = None
            if parent_option == 'existing' and existing_parent_id:
                parent_profile = ParentProfile.objects.filter(id=existing_parent_id, school=school).first()

            if not parent_profile and parent_phone:
                parent_profile = ParentProfile.objects.filter(school=school, phone=parent_phone).first()

            if parent_profile:
                GuardianRelationship.objects.get_or_create(
                    school=school, parent=parent_profile, student=student, defaults={'is_primary': True}
                )
                parent_msg = f"Linked to existing family account '{parent_profile.user.username}'."
            else:
                parent_user, parent_created = User.objects.get_or_create(
                    username=f"p_{st_id.lower()}",
                    defaults={'school': school, 'role': UserRole.PARENT, 'first_name': application.last_name, 'last_name': 'Guardian'}
                )
                if parent_created:
                    parent_initial_pwd = secrets.token_urlsafe(10)
                    parent_user.set_password(parent_initial_pwd)
                    parent_user.must_change_password = True
                    parent_user.save()

                parent_profile, _ = ParentProfile.objects.get_or_create(
                    user=parent_user,
                    defaults={'school': school, 'phone': parent_phone or '+251911000000', 'relationship': parent_relationship}
                )
                GuardianRelationship.objects.get_or_create(
                    school=school, parent=parent_profile, student=student, defaults={'is_primary': True}
                )
                parent_msg = f"Parent login username: {parent_user.username}" + (f" | Password: {parent_initial_pwd} (must change on login)" if parent_created else " (existing account).") + "."

            if sec_id:
                sec = Section.objects.get(id=sec_id, school=school)
                active_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
                StudentEnrollment.objects.get_or_create(
                    school=school, academic_year=active_ay, student=student,
                    defaults={'grade': sec.grade, 'stream': sec.stream, 'section': sec, 'status': EnrollmentStatus.ACTIVE}
                )

            application.status = ApplicationStatus.REGISTERED
            application.reviewed_by = request.user
            application.save()

            messages.success(request, f"Registered student {student.full_name}! {parent_msg}")
            return redirect('students:admissions')
    
    from apps.academics.models import Section
    from apps.parents.models import ParentProfile
    sections = Section.objects.filter(school=school)
    existing_parents = ParentProfile.objects.filter(school=school).select_related('user').prefetch_related(
        'guardianships__student__enrollments__grade',
        'guardianships__student__enrollments__section'
    )
    suggested_student_id = StudentProfile.generate_next_student_id(school)

    return render(request, 'students/review_application.html', {
        'application': application,
        'sections': sections,
        'existing_parents': existing_parents,
        'suggested_student_id': suggested_student_id,
    })

@login_required
def lifecycle_dashboard(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    sections = Section.objects.filter(school=school)
    
    selected_status = request.GET.get('status', 'ALL').upper()
    query = request.GET.get('q', '').strip()

    base_qs = StudentProfile.objects.filter(school=school).select_related('user').prefetch_related(
        'enrollments__grade', 'enrollments__section', 'enrollments__academic_year'
    ).order_by('first_name')

    # Calculate status counts
    counts = {
        'ALL': base_qs.count(),
        'ACTIVE': base_qs.filter(status=StudentStatus.ACTIVE).count(),
        'PROMOTED': base_qs.filter(status=StudentStatus.PROMOTED).count(),
        'GRADUATED': base_qs.filter(status=StudentStatus.GRADUATED).count(),
        'RETAINED': base_qs.filter(status=StudentStatus.RETAINED).count(),
        'WITHDRAWN': base_qs.filter(status=StudentStatus.WITHDRAWN).count(),
    }

    students_qs = base_qs

    if selected_status != 'ALL':
        students_qs = students_qs.filter(status=selected_status)

    if query:
        students_qs = students_qs.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(student_id__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query)
        )

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'bulk_promote':
            from apps.assessments.models import AnnualResult, PromotionStatus
            students_to_evaluate = base_qs.filter(status='ACTIVE')
            
            promoted = 0
            retained = 0
            for stu in students_to_evaluate:
                # Find the most recent official AnnualResult
                annual_result = AnnualResult.objects.filter(
                    enrollment__student=stu
                ).order_by('-academic_year__gregorian_start_date').first()
                
                if annual_result:
                    if annual_result.promotion_status == PromotionStatus.PROMOTED:
                        stu.status = StudentStatus.PROMOTED
                        promoted += 1
                    elif annual_result.promotion_status == PromotionStatus.REPEATED:
                        stu.status = StudentStatus.RETAINED
                        retained += 1
                stu.save()
            messages.success(request, f"Bulk Promotion Complete. Promoted: {promoted}, Retained: {retained}.")
            return redirect('students:lifecycle')

        student_id = request.POST.get('student_id')
        
        try:
            student = StudentProfile.objects.get(id=student_id, school=school)
            
            if action == 'update_status':
                new_status = request.POST.get('status')
                if new_status in dict(StudentStatus.choices):
                    student.status = new_status
                    student.save()
                    messages.success(request, f"Status for {student.full_name} updated to {student.get_status_display()}.")
                    
            elif action == 'transfer_section':
                from apps.enrollment.models import StudentEnrollment
                new_section_id = request.POST.get('section_id')
                new_section = Section.objects.get(id=new_section_id, school=school)
                
                enrollment = StudentEnrollment.objects.filter(student=student, status='ACTIVE').first()
                if enrollment:
                    enrollment.section = new_section
                    enrollment.grade = new_section.grade
                    enrollment.save()
                    messages.success(request, f"Transferred {student.full_name} to {new_section.name}.")
                else:
                    messages.error(request, "No active enrollment found for this student.")
                    
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
        return redirect('students:lifecycle')

    return render(request, 'students/lifecycle_dashboard.html', {
        'students': students_qs,
        'sections': sections,
        'selected_status': selected_status,
        'query': query,
        'counts': counts,
    })

@login_required
def at_risk_students(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'COUNSELOR', 'TEACHER']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    active_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    # Flag criteria in the chosen academic year: > 3 absences OR average mark < 50
    from django.db.models import Q

    # Absences in chosen academic year
    absence_filter = Q(school=school, status='ACTIVE', attendance_records__status='ABSENT')
    if active_ay and active_ay.gregorian_start_date and active_ay.gregorian_end_date:
        absence_filter &= Q(
            attendance_records__date__gte=active_ay.gregorian_start_date,
            attendance_records__date__lte=active_ay.gregorian_end_date
        )

    students_with_absences = StudentProfile.objects.filter(absence_filter).annotate(
        absence_count=Count('attendance_records')
    ).filter(absence_count__gte=3)

    # Average mark in chosen academic year
    mark_filter = Q(
        school=school,
        status='ACTIVE',
        enrollments__marks__status__in=[MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]
    )
    if active_ay:
        mark_filter &= Q(enrollments__academic_year=active_ay)

    students_with_low_marks = StudentProfile.objects.filter(mark_filter).annotate(
        avg_mark=Avg('enrollments__marks__mark_value')
    ).filter(avg_mark__lt=50)

    # Combine the sets
    at_risk_dict = {}
    
    for student in students_with_absences:
        at_risk_dict[student.id] = {
            'student': student,
            'absences': student.absence_count,
            'avg_mark': None,
            'reasons': ['High Absenteeism']
        }
        
    for student in students_with_low_marks:
        if student.id in at_risk_dict:
            at_risk_dict[student.id]['avg_mark'] = round(student.avg_mark, 2)
            at_risk_dict[student.id]['reasons'].append('Low Academic Performance')
        else:
            at_risk_dict[student.id] = {
                'student': student,
                'absences': 0,
                'avg_mark': round(student.avg_mark, 2),
                'reasons': ['Low Academic Performance']
            }

    at_risk_list = list(at_risk_dict.values())
    
    return render(request, 'students/at_risk_dashboard.html', {
        'at_risk_list': at_risk_list,
        'current_academic_year': active_ay
    })

@login_required
def student_profile_admin_view(request, student_id):
    """
    View a student's full profile details. Accessible to admins and staff.
    """
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR', 'COUNSELOR', 'TEACHER']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    student = get_object_or_404(StudentProfile, id=student_id, school=school)
    
    from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
    from apps.academics.models import Section, AcademicYear

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'edit_profile':
            fname = request.POST.get('first_name', '').strip()
            mname = request.POST.get('middle_name', '').strip()
            lname = request.POST.get('last_name', '').strip()
            amharic_name = request.POST.get('amharic_name', '').strip()
            gender = request.POST.get('gender', student.gender).strip()
            dob = request.POST.get('date_of_birth', '').strip()
            phone = request.POST.get('phone', '').strip()
            address = request.POST.get('address', '').strip()
            region = request.POST.get('region', '').strip()
            woreda = request.POST.get('woreda', '').strip()
            kebele = request.POST.get('kebele', '').strip()
            national_id = request.POST.get('national_id', '').strip()
            emergency = request.POST.get('emergency_contact', '').strip()
            status = request.POST.get('status', student.status).strip()

            if fname:
                student.first_name = fname
                student.user.first_name = fname
            if mname:
                student.middle_name = mname
            if lname:
                student.last_name = lname
                student.user.last_name = lname
            student.user.save()

            student.amharic_name = amharic_name
            if gender in ['M', 'F']:
                student.gender = gender
            if dob:
                try:
                    student.date_of_birth = dob
                except Exception:
                    pass
            student.phone = phone
            student.address = address
            student.region = region
            student.woreda = woreda
            student.kebele = kebele
            student.national_id = national_id
            student.emergency_contact = emergency
            if status in dict(StudentStatus.choices):
                student.status = status

            # Handle photo upload if present
            if 'photo' in request.FILES:
                student.photo = request.FILES['photo']

            student.save()
            messages.success(request, f"Student profile for '{student.full_name}' updated successfully!")
            return redirect('students:admin_profile', student_id=student.id)

        elif action == 'reset_account_password':
            target_type = request.POST.get('target_type')
            new_password = request.POST.get('new_password', '').strip()
            if new_password and len(new_password) >= 6:
                if target_type == 'STUDENT':
                    student.user.set_password(new_password)
                    student.user.must_change_password = True
                    student.user.save()
                    student.current_password_display = new_password
                    student.save()
                    messages.success(request, f"Password for student '{student.full_name}' ({student.user.username}) updated to '{new_password}'.")
                elif target_type == 'PARENT':
                    parent = student.primary_guardian
                    if parent:
                        parent.user.set_password(new_password)
                        parent.user.must_change_password = True
                        parent.user.save()
                        parent.current_password_display = new_password
                        parent.save()
                        messages.success(request, f"Password for parent '{parent.user.username}' updated to '{new_password}'.")
                    else:
                        messages.error(request, "No parent profile linked to this student.")
            else:
                messages.error(request, "Password must be at least 6 characters.")
            return redirect('students:admin_profile', student_id=student.id)

        elif action == 'manual_enroll':
            section_id = request.POST.get('section_id')
            year_id = request.POST.get('academic_year_id')
            
            if section_id and year_id:
                section = get_object_or_404(Section, id=section_id, school=school)
                academic_year = get_object_or_404(AcademicYear, id=year_id, school=school)
                
                StudentEnrollment.objects.get_or_create(
                    student=student,
                    school=school,
                    academic_year=academic_year,
                    defaults={
                        'grade': section.grade,
                        'stream': section.stream,
                        'section': section,
                        'status': EnrollmentStatus.ACTIVE
                    }
                )
                messages.success(request, f"Successfully enrolled {student.first_name} into {section.grade.name} - {section.name}.")
                return redirect('students:admin_profile', student_id=student.id)
            else:
                messages.error(request, "Section and Academic Year are required for enrollment.")
                return redirect('students:admin_profile', student_id=student.id)
                
        elif action == 'add_historical_transcript':
            from apps.reports.models import HistoricalTranscriptYear
            
            grade_name = request.POST.get('grade_name')
            grade_level = int(request.POST.get('grade_level', 0))
            academic_year_name = request.POST.get('academic_year_name')
            
            subject_names = request.POST.getlist('subject_name[]')
            sem1_scores = request.POST.getlist('sem1_score[]')
            sem2_scores = request.POST.getlist('sem2_score[]')
            
            subjects_data = []
            for i in range(len(subject_names)):
                sub_name = subject_names[i].strip()
                if not sub_name:
                    continue
                
                try:
                    s1 = float(sem1_scores[i]) if sem1_scores[i].strip() else 0.0
                except ValueError:
                    s1 = 0.0
                try:
                    s2 = float(sem2_scores[i]) if sem2_scores[i].strip() else 0.0
                except ValueError:
                    s2 = 0.0
                    
                if s1 > 0 and s2 > 0:
                    avg = round((s1 + s2) / 2.0, 1)
                else:
                    avg = round(s1 or s2, 1)
                    
                letter = 'A' if avg >= 85 else ('B' if avg >= 75 else ('C' if avg >= 50 else 'F'))
                
                subjects_data.append({
                    'name': sub_name,
                    'sem1': round(s1, 1) if s1 else '-',
                    'sem2': round(s2, 1) if s2 else '-',
                    'avg': avg,
                    'letter': letter
                })
                
            if subjects_data and grade_name and grade_level > 0 and academic_year_name:
                HistoricalTranscriptYear.objects.create(
                    school=school,
                    student=student,
                    grade_name=grade_name,
                    grade_level=grade_level,
                    academic_year_name=academic_year_name,
                    subjects_json=subjects_data,
                    created_by=request.user
                )
                messages.success(request, f"Successfully added historical transcript for {grade_name}.")
            else:
                messages.error(request, "Invalid data provided for historical transcript.")
                
            return redirect('students:admin_profile', student_id=student.id)
            
    active_enrollment = StudentEnrollment.objects.filter(student=student, status='ACTIVE').first()
    
    attendance_qs = AttendanceRecord.objects.filter(student=student)
    total_days = attendance_qs.count()
    absent_count = attendance_qs.filter(status='ABSENT').count()
    attendance_percentage = round(((total_days - absent_count) / total_days * 100), 1) if total_days > 0 else 100.0

    all_sections = Section.objects.filter(school=school).order_by('grade__level', 'name')
    all_academic_years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')

    from apps.reports.models import HistoricalTranscriptYear
    historical_records = HistoricalTranscriptYear.objects.filter(student=student, school=school)

    return render(request, 'students/admin_student_profile.html', {
        'student': student,
        'active_enrollment': active_enrollment,
        'attendance_percentage': attendance_percentage,
        'absent_count': absent_count,
        'total_days': total_days,
        'all_sections': all_sections,
        'all_academic_years': all_academic_years,
        'historical_records': historical_records,
    })


# ─── CSV Column Reference ───────────────────────────────────────────────────
BULK_IMPORT_COLUMNS = [
    {'name': 'first_name',       'description': 'Student first name',              'required': True,  'example': 'Abebe'},
    {'name': 'middle_name',      'description': 'Father\'s name (patronymic)',     'required': True,  'example': 'Girma'},
    {'name': 'last_name',        'description': 'Grandfather\'s name (optional)',  'required': False, 'example': 'Tadesse'},
    {'name': 'gender',           'description': 'M or F',                          'required': True,  'example': 'M'},
    {'name': 'date_of_birth',    'description': 'Gregorian date YYYY-MM-DD',       'required': False, 'example': '2007-03-15'},
    {'name': 'phone',            'description': 'Student/guardian phone',          'required': False, 'example': '+251911234567'},
    {'name': 'region',           'description': 'Ethiopian region',                'required': False, 'example': 'Addis Ababa'},
    {'name': 'woreda',           'description': 'Woreda',                          'required': False, 'example': 'Bole'},
    {'name': 'kebele',           'description': 'Kebele',                          'required': False, 'example': '07'},
    {'name': 'national_id',      'description': 'National/Fayda ID (optional)',    'required': False, 'example': 'ETH-NAT-12345'},
    {'name': 'admission_number', 'description': 'Admission number (auto if blank)', 'required': False, 'example': 'ADM-2017-001'},
    {'name': 'grade_level',      'description': 'Grade number (9, 10, 11, 12)',    'required': False, 'example': '9'},
    {'name': 'section_name',     'description': 'Section name (e.g. A, B)',        'required': False, 'example': 'A'},
    {'name': 'amharic_name',     'description': 'Full name in Amharic (Geez)',     'required': False, 'example': 'አበበ ጊርማ'},
]

CSV_TEMPLATE_HEADER = ','.join(col['name'] for col in BULK_IMPORT_COLUMNS)


@login_required
def bulk_import_template(request):
    """Serve a ready-to-download CSV template."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="student_import_template.csv"'
    # BOM for Excel compatibility
    response.write('\ufeff')
    response.write(CSV_TEMPLATE_HEADER + '\n')
    # Example row
    example = 'Abebe,Girma,Tadesse,M,2007-03-15,+251911234567,Addis Ababa,Bole,07,,ADM-2017-001,9,A,አበበ ጊርማ'
    response.write(example + '\n')
    return response


@login_required
def bulk_import_students(request):
    """
    Bulk Student CSV Import view.
    GET  — renders upload form with column guide.
    POST — processes CSV, creates users + student profiles, returns import results.
    """
    import csv
    import io
    from django.db import transaction
    from django.contrib.auth import get_user_model
    from apps.academics.models import AcademicYear, Grade, Section
    from apps.enrollment.models import StudentEnrollment

    User = get_user_model()
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school:
        messages.error(request, 'No school context found.')
        return redirect('admin_dashboard')

    academic_years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')
    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    sections = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name')

    if request.method != 'POST':
        return render(request, 'students/bulk_import.html', {
            'academic_years': academic_years,
            'grades': grades,
            'sections': sections,
            'column_reference': BULK_IMPORT_COLUMNS,
        })


    # --- Process uploaded CSV ---
    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        messages.error(request, 'Please select a CSV file to upload.')
        return render(request, 'students/bulk_import.html', {
            'academic_years': academic_years,
            'grades': grades,
            'column_reference': BULK_IMPORT_COLUMNS,
        })

    if not csv_file.name.endswith('.csv'):
        messages.error(request, 'Only .csv files are accepted.')
        return render(request, 'students/bulk_import.html', {
            'academic_years': academic_years,
            'grades': grades,
            'column_reference': BULK_IMPORT_COLUMNS,
        })

    academic_year_id = request.POST.get('academic_year')
    default_grade_id  = request.POST.get('default_grade')

    try:
        academic_year = AcademicYear.objects.get(id=academic_year_id, school=school)
    except AcademicYear.DoesNotExist:
        messages.error(request, 'Selected academic year not found.')
        return redirect('students:bulk_import')

    default_grade = None
    if default_grade_id:
        try:
            default_grade = Grade.objects.get(id=default_grade_id, school=school)
        except Grade.DoesNotExist:
            pass

    # Decode file
    try:
        raw = csv_file.read().decode('utf-8-sig')  # handles BOM
    except UnicodeDecodeError:
        try:
            csv_file.seek(0)
            raw = csv_file.read().decode('latin-1')
        except Exception:
            messages.error(request, 'Could not decode the CSV file. Please save it as UTF-8.')
            return redirect('students:bulk_import')

    reader = csv.DictReader(io.StringIO(raw))
    required_cols = {'first_name', 'middle_name', 'gender'}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        messages.error(request, f'CSV must have at minimum these columns: {", ".join(required_cols)}. Got: {reader.fieldnames}')
        return render(request, 'students/bulk_import.html', {
            'academic_years': academic_years,
            'grades': grades,
            'column_reference': BULK_IMPORT_COLUMNS,
        })

    results = {'created': 0, 'skipped': 0, 'errors': [], 'preview_rows': []}

    for row_num, row in enumerate(reader, start=2):
        first_name  = (row.get('first_name',  '') or '').strip()
        middle_name = (row.get('middle_name', '') or '').strip()
        last_name   = (row.get('last_name',   '') or '').strip()
        gender      = (row.get('gender',      '') or '').strip().upper()

        if not first_name or not middle_name:
            results['errors'].append({'row': row_num, 'message': 'first_name and middle_name are required.'})
            results['skipped'] += 1
            continue

        if gender not in ('M', 'F'):
            results['errors'].append({'row': row_num, 'message': f'Invalid gender "{gender}" — must be M or F.'})
            results['skipped'] += 1
            continue

        # Resolve grade
        grade = default_grade
        grade_level_str = (row.get('grade_level', '') or '').strip()
        if grade_level_str:
            try:
                grade = Grade.objects.filter(school=school, level=int(grade_level_str)).first()
            except ValueError:
                pass

        # Resolve section
        section = None
        section_name = (row.get('section_name', '') or '').strip()
        if section_name and grade:
            section = Section.objects.filter(school=school, grade=grade, name__iexact=section_name).first()

        try:
            with transaction.atomic():
                # Auto-generate student_id
                student_id = StudentProfile.generate_next_student_id(school)

                # Build username: firstname.middlename_<shortid>
                base_username = f"{first_name.lower()}.{middle_name.lower()}".replace(' ', '')[:20]
                username = base_username
                suffix = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{suffix}"
                    suffix += 1

                import secrets
                password = secrets.token_urlsafe(10)

                user_obj = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=f"{middle_name} {last_name}".strip(),
                    role='STUDENT',
                    school=school,
                    must_change_password=True,
                )

                dob = None
                dob_str = (row.get('date_of_birth', '') or '').strip()
                if dob_str:
                    from datetime import datetime
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                        try:
                            dob = datetime.strptime(dob_str, fmt).date()
                            break
                        except ValueError:
                            continue

                student = StudentProfile.objects.create(
                    school=school,
                    user=user_obj,
                    student_id=student_id,
                    admission_number=(row.get('admission_number', '') or '').strip() or None,
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    gender=gender,
                    date_of_birth=dob,
                    phone=(row.get('phone', '') or '').strip() or None,
                    region=(row.get('region', '') or '').strip() or None,
                    woreda=(row.get('woreda', '') or '').strip() or None,
                    kebele=(row.get('kebele', '') or '').strip() or None,
                    national_id=(row.get('national_id', '') or '').strip() or None,
                    amharic_name=(row.get('amharic_name', '') or '').strip() or None,
                    status='ACTIVE',
                )

                # Auto-enroll if grade and section provided
                if grade and section:
                    StudentEnrollment.objects.get_or_create(
                        school=school,
                        student=student,
                        academic_year=academic_year,
                        defaults={
                            'grade': grade,
                            'section': section,
                            'stream': section.stream,
                            'status': 'ACTIVE',
                        }
                    )

                results['created'] += 1
                if len(results['preview_rows']) < 20:
                    results['preview_rows'].append({
                        'student_id': student_id,
                        'full_name': student.full_name,
                        'gender': gender,
                        'grade': f"Grade {grade.level}" if grade else '—',
                        'username': username,
                    })

        except Exception as exc:
            results['errors'].append({'row': row_num, 'message': str(exc)})
            results['skipped'] += 1

    if results['created'] > 0:
        messages.success(request, f"Successfully imported {results['created']} student(s).")

    return render(request, 'students/bulk_import.html', {
        'academic_years': academic_years,
        'grades': grades,
        'column_reference': BULK_IMPORT_COLUMNS,
        'import_results': results,
    })
