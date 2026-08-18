from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.teachers.models import TeacherProfile, EmploymentStatus
from apps.accounts.models import User, UserRole

@login_required
def management_dashboard(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.HR_MANAGER]:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    from apps.academics.models import Section

    teachers = TeacherProfile.objects.filter(school=school).select_related('user').prefetch_related(
        'user__managed_sections__grade',
        'assignments__subject',
        'assignments__section'
    ).order_by('user__first_name', 'user__last_name')
    
    sections = Section.objects.filter(school=school, is_active=True).select_related('grade').order_by('grade__name', 'name')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_status':
            teacher_id = request.POST.get('teacher_id')
            new_status = request.POST.get('status')
            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                if new_status in dict(EmploymentStatus.choices):
                    teacher.employment_status = new_status
                    teacher.save()
                    messages.success(request, f"Updated {teacher.user.get_full_name()}'s status to {teacher.get_employment_status_display()}.")
            except TeacherProfile.DoesNotExist:
                messages.error(request, "Teacher not found.")
            return redirect('teachers:management')

        elif action == 'edit_teacher':
            teacher_id = request.POST.get('teacher_id')
            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                fname = request.POST.get('first_name', '').strip()
                lname = request.POST.get('last_name', '').strip()
                dept = request.POST.get('department', '').strip()
                spec = request.POST.get('specialization', '').strip()
                status = request.POST.get('employment_status', teacher.employment_status)
                homeroom_sec_id = request.POST.get('homeroom_section_id', '').strip()

                if fname:
                    teacher.user.first_name = fname
                if lname:
                    teacher.user.last_name = lname
                teacher.user.save()

                teacher.department = dept
                teacher.specialization = spec
                if status in dict(EmploymentStatus.choices):
                    teacher.employment_status = status
                teacher.save()

                # Handle homeroom assignment
                if homeroom_sec_id == 'none':
                    Section.objects.filter(school=school, class_teacher=teacher.user).update(class_teacher=None)
                elif homeroom_sec_id:
                    target_sec = Section.objects.filter(id=homeroom_sec_id, school=school).first()
                    if target_sec:
                        Section.objects.filter(school=school, class_teacher=teacher.user).update(class_teacher=None)
                        target_sec.class_teacher = teacher.user
                        target_sec.save()

                messages.success(request, f"Teacher profile for '{teacher.user.get_full_name()}' updated successfully!")
            except TeacherProfile.DoesNotExist:
                messages.error(request, "Teacher not found.")
            return redirect('teachers:management')

        elif action == 'assign_homeroom':
            teacher_id = request.POST.get('teacher_id')
            section_id = request.POST.get('section_id')
            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                if section_id == 'none':
                    Section.objects.filter(school=school, class_teacher=teacher.user).update(class_teacher=None)
                    messages.success(request, f"Removed homeroom class assignment from {teacher.user.get_full_name()}.")
                else:
                    section = Section.objects.get(id=section_id, school=school)
                    Section.objects.filter(school=school, class_teacher=teacher.user).update(class_teacher=None)
                    section.class_teacher = teacher.user
                    section.save()
                    messages.success(request, f"Assigned {teacher.user.get_full_name()} as Homeroom Teacher for Section {section.grade.name} - {section.name}.")
            except Exception as e:
                messages.error(request, f"Error updating homeroom assignment: {e}")
            return redirect('teachers:management')

        elif action == 'add_teacher':
            from apps.subscriptions.services import SubscriptionService
            SubscriptionService.check_teacher_limit(school)
            emp_id = request.POST.get('employee_id', '').strip()
            fname = request.POST.get('first_name', '').strip()
            lname = request.POST.get('last_name', '').strip()
            dept = request.POST.get('department', '').strip()
            spec = request.POST.get('specialization', '').strip()
            homeroom_sec_id = request.POST.get('homeroom_section_id', '').strip()

            if not emp_id or not fname or not lname:
                messages.error(request, "Employee ID, First Name, and Last Name are required.")
                return redirect('teachers:management')

            if User.objects.filter(username=emp_id.lower()).exists():
                messages.error(request, f"User with ID/Username '{emp_id}' already exists.")
                return redirect('teachers:management')

            user = User.objects.create_user(
                username=emp_id.lower(),
                school=school,
                role=UserRole.TEACHER,
                first_name=fname,
                last_name=lname
            )
            user.set_password("teacher123")
            user.must_change_password = True
            user.save()

            teacher_profile = TeacherProfile.objects.create(
                school=school,
                user=user,
                employee_id=emp_id,
                department=dept or spec,
                specialization=spec
            )

            if homeroom_sec_id and homeroom_sec_id != 'none':
                sec = Section.objects.filter(id=homeroom_sec_id, school=school).first()
                if sec:
                    sec.class_teacher = user
                    sec.save()

            messages.success(request, f"Teacher '{fname} {lname}' (ID: {emp_id}) added successfully! Default password is 'teacher123'.")
            return redirect('teachers:management')

        return redirect('teachers:management')

    suggested_teacher_id = TeacherProfile.generate_next_employee_id(school) if hasattr(TeacherProfile, 'generate_next_employee_id') else f"{getattr(school, 'code', 'TEA')}-TCH-0001"

    # Compute school stats for the dashboard header
    total_teachers = teachers.count()
    full_time_count = sum(1 for t in teachers if t.employment_status == EmploymentStatus.FULL_TIME)
    homeroom_count = sum(1 for t in teachers if t.homeroom_section is not None)

    return render(request, 'teachers/management_dashboard.html', {
        'teachers': teachers,
        'sections': sections,
        'suggested_teacher_id': suggested_teacher_id,
        'total_teachers': total_teachers,
        'full_time_count': full_time_count,
        'homeroom_count': homeroom_count,
    })

@login_required
def teacher_assignments_view(request):
    """
    Admin management view to assign teachers to multiple subjects across different grade sections,
    and set Homeroom Class Teachers.
    """
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Unauthorized access to teacher assignments.")
        return redirect('index')

    from apps.academics.models import Subject, Section
    from apps.teachers.models import TeacherAssignment

    current_ay = getattr(request, 'academic_year', None)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'assign_subject':
            teacher_id = request.POST.get('teacher_id')
            subject_id = request.POST.get('subject_id')
            section_id = request.POST.get('section_id')

            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                subject = Subject.objects.get(id=subject_id, school=school)
                section = Section.objects.get(id=section_id, school=school)

                _, created = TeacherAssignment.objects.get_or_create(
                    school=school,
                    academic_year=current_ay,
                    teacher=teacher,
                    subject=subject,
                    section=section
                )

                if created:
                    messages.success(request, f"Assigned {teacher.user.get_full_name()} to teach {subject.name} in Section {section.name} ({section.grade.name}).")
                else:
                    messages.info(request, f"{teacher.user.get_full_name()} is already assigned to {subject.name} in Section {section.name}.")
            except Exception as e:
                messages.error(request, f"Error creating assignment: {e}")

            return redirect('teachers:assignments')

        elif action == 'remove_assignment':
            assignment_id = request.POST.get('assignment_id')
            try:
                assignment = TeacherAssignment.objects.get(id=assignment_id, school=school)
                t_name = assignment.teacher.user.get_full_name()
                sub_name = assignment.subject.name
                sec_name = assignment.section.name
                assignment.delete()
                messages.success(request, f"Removed assignment: {t_name} from {sub_name} (Section {sec_name}).")
            except TeacherAssignment.DoesNotExist:
                messages.error(request, "Assignment not found.")

            return redirect('teachers:assignments')

        elif action == 'assign_homeroom':
            teacher_id = request.POST.get('teacher_id')
            section_id = request.POST.get('section_id')

            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                section = Section.objects.get(id=section_id, school=school)
                section.class_teacher = teacher.user
                section.save()
                messages.success(request, f"Assigned {teacher.user.get_full_name()} as Homeroom Class Teacher for Section {section.name} ({section.grade.name}).")
            except Exception as e:
                messages.error(request, f"Error setting homeroom teacher: {e}")

            return redirect('teachers:assignments')

        elif action == 'remove_homeroom':
            section_id = request.POST.get('section_id')
            try:
                section = Section.objects.get(id=section_id, school=school)
                prev_teacher = section.class_teacher.get_full_name() if section.class_teacher else "Teacher"
                section.class_teacher = None
                section.save()
                messages.success(request, f"Removed {prev_teacher} as Homeroom Teacher for Section {section.name} ({section.grade.name}).")
            except Section.DoesNotExist:
                messages.error(request, "Section not found.")

            return redirect('teachers:assignments')

        elif action == 'assign_tutorial':
            teacher_id = request.POST.get('teacher_id')
            section_id = request.POST.get('section_id')

            try:
                teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
                section = Section.objects.get(id=section_id, school=school)
                section.tutorial_teacher = teacher.user
                section.save()
                messages.success(request, f"Assigned {teacher.user.get_full_name()} as Tutorial Controller for Section {section.name} ({section.grade.name}).")
            except Exception as e:
                messages.error(request, f"Error setting tutorial controller: {e}")

            return redirect('teachers:assignments')

        elif action == 'remove_tutorial':
            section_id = request.POST.get('section_id')
            try:
                section = Section.objects.get(id=section_id, school=school)
                prev_teacher = section.tutorial_teacher.get_full_name() if section.tutorial_teacher else "Teacher"
                section.tutorial_teacher = None
                section.save()
                messages.success(request, f"Removed {prev_teacher} as Tutorial Controller for Section {section.name} ({section.grade.name}).")
            except Section.DoesNotExist:
                messages.error(request, "Section not found.")

            return redirect('teachers:assignments')

    teachers = TeacherProfile.objects.filter(school=school).select_related('user').order_by('user__first_name')
    subjects = Subject.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'code')
    sections = Section.objects.filter(school=school).select_related('grade', 'class_teacher', 'tutorial_teacher').order_by('grade__level', 'name')
    assignments = TeacherAssignment.objects.filter(school=school).select_related('teacher__user', 'subject__grade', 'section__grade', 'academic_year')
    if current_ay:
        assignments = assignments.filter(academic_year=current_ay)

    # Group assignments per teacher
    teacher_loads = []
    for teacher in teachers:
        t_assignments = assignments.filter(teacher=teacher)
        homeroom_sections = sections.filter(class_teacher=teacher.user)
        tutorial_sections = sections.filter(tutorial_teacher=teacher.user)
        teacher_loads.append({
            'teacher': teacher,
            'assignments': t_assignments,
            'homeroom_sections': homeroom_sections,
            'tutorial_sections': tutorial_sections,
            'total_sections': t_assignments.values('section_id').distinct().count(),
            'total_subjects': t_assignments.values('subject_id').distinct().count(),
        })

    return render(request, 'teachers/assignments.html', {
        'teachers': teachers,
        'subjects': subjects,
        'sections': sections,
        'assignments': assignments,
        'teacher_loads': teacher_loads,
        'current_ay': current_ay,
    })

@login_required
def homeroom_portal(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    from apps.academics.models import Section
    current_ay = getattr(request, 'academic_year', None)

    try:
        teacher_profile = request.user.teacher_profile
    except TeacherProfile.DoesNotExist:
        if request.user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
            teacher_profile = None
        else:
            messages.error(request, "Only teachers can access the homeroom portal.")
            return redirect('index')

    homeroom = Section.objects.filter(school=school, class_teacher=request.user).first()
    if not homeroom:
        messages.warning(request, "You are not assigned as a homeroom teacher for the current academic year.")
        return redirect('index')

    from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
    from apps.attendance.models import AttendanceRecord, AttendanceStatus
    from apps.assessments.models import StudentConduct, ConductGrade
    import datetime

    enrollments = StudentEnrollment.objects.filter(
        school=school,
        section=homeroom,
        status=EnrollmentStatus.ACTIVE
    )
    if current_ay:
        enrollments = enrollments.filter(academic_year=current_ay)
    enrollments = enrollments.select_related('student')

    today = datetime.date.today()
    if current_ay and current_ay.gregorian_start_date and current_ay.gregorian_end_date:
        if current_ay.gregorian_start_date <= today <= current_ay.gregorian_end_date:
            default_date = today
        else:
            default_date = current_ay.gregorian_start_date
    else:
        default_date = today

    selected_date_str = request.GET.get('date') or request.POST.get('date')
    if selected_date_str:
        try:
            selected_date = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = default_date
    else:
        selected_date = default_date

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_attendance':
            # Save bulk attendance for selected_date
            for enrollment in enrollments:
                status_value = request.POST.get(f'attendance_{enrollment.student.id}')
                if status_value in dict(AttendanceStatus.choices):
                    AttendanceRecord.objects.update_or_create(
                        school=school,
                        section=homeroom,
                        student=enrollment.student,
                        date=selected_date,
                        defaults={
                            'status': status_value,
                            'recorded_by': request.user
                        }
                    )
            messages.success(request, f"Attendance for {selected_date.strftime('%b %d, %Y')} saved successfully.")
            return redirect(f"{reverse('teachers:homeroom')}?date={selected_date.strftime('%Y-%m-%d')}")
            
        elif action == 'save_conduct':
            student_id = request.POST.get('student_id')
            grade = request.POST.get('grade')
            remarks = request.POST.get('remarks', '')
            try:
                enrollment = enrollments.get(student_id=student_id)
                # Need academic_year and period
                academic_year = enrollment.academic_year
                from apps.academics.models import AcademicPeriod
                # Assuming current period
                current_period = AcademicPeriod.objects.filter(academic_year=academic_year, is_current=True).first()
                if not current_period:
                    current_period = AcademicPeriod.objects.filter(academic_year=academic_year).first()
                
                if current_period and grade in dict(ConductGrade.choices):
                    StudentConduct.objects.create(
                        school=school,
                        enrollment=enrollment,
                        academic_year=academic_year,
                        period=current_period,
                        grade=grade,
                        remarks=remarks,
                        recorded_by=request.user
                    )
                    messages.success(request, f"Conduct recorded for {enrollment.student.full_name}.")
                else:
                    messages.error(request, "Could not determine current period or invalid grade.")
            except StudentEnrollment.DoesNotExist:
                messages.error(request, "Student not found in this homeroom.")
            return redirect(f"{reverse('teachers:homeroom')}?date={selected_date.strftime('%Y-%m-%d')}")

    attendances = AttendanceRecord.objects.filter(
        school=school,
        section=homeroom,
        date=selected_date
    ).select_related('student')
    
    attendance_dict = {att.student_id: att.status for att in attendances}
    
    for enrollment in enrollments:
        enrollment.student.current_attendance_status = attendance_dict.get(enrollment.student_id, 'PRESENT')
    
    # Get latest conduct for each student
    conducts = StudentConduct.objects.filter(
        school=school,
        enrollment__in=enrollments
    ).order_by('-created_at')
    
    # We want only the most recent conduct for the dictionary
    conduct_dict = {}
    for c in conducts:
        if c.enrollment.student_id not in conduct_dict:
            conduct_dict[c.enrollment.student_id] = c

    from apps.academics.ethiopian_date import get_attendance_calendar_context
    cal_ctx = get_attendance_calendar_context(selected_date, school, homeroom, current_ay)
    selected_date = cal_ctx['selected_date']

    export = request.GET.get('export')
    if export in ['excel', 'csv', 'pdf'] and homeroom:
        rec_rows = []
        for en in enrollments:
            st = en.student
            rec_rows.append({
                'student_id': st.student_id,
                'student_name': st.full_name,
                'status': getattr(st, 'current_attendance_status', 'PRESENT'),
                'reason': ''
            })

        if export in ['excel', 'csv']:
            import csv
            from django.http import HttpResponse
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = f"Homeroom_Attendance_{homeroom.name}_{selected_date.strftime('%Y-%m-%d')}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            writer = csv.writer(response)
            writer.writerow([f"School: {school.name if school else 'N/A'}", f"Homeroom Section: {homeroom.grade.name} - {homeroom.name}", f"Date: {selected_date}"])
            writer.writerow([f"Homeroom Teacher: {request.user.get_full_name()}"])
            writer.writerow([])
            writer.writerow(["Student ID", "Student Name", "Attendance Status", "Remarks"])

            for rr in rec_rows:
                writer.writerow([rr['student_id'], rr['student_name'], rr['status'], rr['reason']])
            return response

        elif export == 'pdf':
            from utils.pdf_utils import generate_attendance_pdf
            from django.http import HttpResponse
            pdf_bytes = generate_attendance_pdf(
                school_name=school.name if school else "School",
                title="HOMEROOM DAILY ATTENDANCE SHEET",
                section_name=f"{homeroom.grade.name} - {homeroom.name}",
                date_str=selected_date.strftime('%b %d, %Y'),
                controller_name=request.user.get_full_name(),
                records=rec_rows
            )
            filename = f"Homeroom_Attendance_{homeroom.name}_{selected_date.strftime('%Y-%m-%d')}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    context = {
        'homeroom': homeroom,
        'enrollments': enrollments,
        'attendance_dict': attendance_dict,
        'conduct_dict': conduct_dict,
        'attendance_choices': AttendanceStatus.choices,
        'conduct_grades': ConductGrade.choices,
    }
    context.update(cal_ctx)

    return render(request, 'teachers/homeroom_portal.html', context)

@login_required
def my_subjects(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    try:
        teacher_profile = request.user.teacher_profile
    except TeacherProfile.DoesNotExist:
        if request.user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
            teacher_profile = None
        else:
            messages.error(request, "Only teachers can access the subjects portal.")
            return redirect('index')
        
    from apps.teachers.models import TeacherAssignment
    
    current_ay = getattr(request, 'academic_year', None)
    
    # Get the subjects the teacher is assigned to
    if teacher_profile:
        assignments = TeacherAssignment.objects.filter(
            school=school,
            teacher=teacher_profile
        ).select_related('academic_year', 'subject', 'section')
    else:
        assignments = TeacherAssignment.objects.none()
    
    if current_ay:
        assignments = assignments.filter(academic_year=current_ay)

    return render(request, 'teachers/my_subjects.html', {
        'assignments': assignments,
    })

@login_required
def manage_marks(request, assignment_id):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    from apps.teachers.models import TeacherAssignment

    try:
        assignment = TeacherAssignment.objects.get(
            id=assignment_id,
            school=school
        )
    except TeacherAssignment.DoesNotExist:
        messages.error(request, "Assignment not found or unauthorized.")
        return redirect('teachers:subjects')

    return redirect('assessments:mark_entry_grid', section_id=assignment.section.id, subject_id=assignment.subject.id)
