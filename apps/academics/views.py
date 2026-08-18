import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError

from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject, PeriodSlot, TimetableSlot, ETHIOPIAN_GRADES
from apps.teachers.models import TeacherProfile

@login_required
@csrf_exempt
def academics_config_view(request):
    """
    Centralized configuration dashboard for Academic Years, AcademicPeriods, Grades, Streams, Sections, and Subjects.
    Only accessible to School Admins and Super Admins.
    """
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Unauthorized access to academics configuration.")
        return redirect('index')

    school = getattr(request, 'school', None)
    if not school and request.user.school:
        school = request.user.school

    if request.method == 'POST':
        action = request.POST.get('action')

        # Platform super-admin has no school — block all write actions
        if school is None:
            messages.error(request, "No school is linked to your account. Please log in as a School Admin or select a school first.")
            return redirect('academics:config')

        if action == 'add_academic_year':
            name = request.POST.get('name')
            eth_year = request.POST.get('ethiopian_year')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            from apps.academics.ethiopian_date import ethiopian_to_gregorian, gregorian_to_ethiopian

            eth_s_m = request.POST.get('eth_start_month')
            eth_s_d = request.POST.get('eth_start_day')
            eth_s_y = eth_year or request.POST.get('eth_start_year')
            eth_e_m = request.POST.get('eth_end_month')
            eth_e_d = request.POST.get('eth_end_day')
            eth_e_y = eth_year or request.POST.get('eth_end_year')

            if eth_s_m and eth_s_d and eth_s_y:
                calc_start = ethiopian_to_gregorian(eth_s_y, eth_s_m, eth_s_d)
                if calc_start:
                    start_date = calc_start.isoformat()
            if eth_e_m and eth_e_d and eth_e_y:
                calc_end = ethiopian_to_gregorian(eth_e_y, eth_e_m, eth_e_d)
                if calc_end:
                    end_date = calc_end.isoformat()

            if eth_year and not start_date:
                try:
                    ey = int(eth_year)
                    calc_start = ethiopian_to_gregorian(ey, 1, 1)
                    calc_end = ethiopian_to_gregorian(ey, 10, 30)
                    if calc_start and calc_end:
                        start_date = calc_start.isoformat()
                        end_date = calc_end.isoformat()
                except Exception:
                    pass
            elif start_date and not eth_year:
                try:
                    ey, em, ed = gregorian_to_ethiopian(datetime.date.fromisoformat(start_date))
                    eth_year = ey
                except Exception:
                    pass

            try:
                ay = AcademicYear.objects.create(
                    school=school,
                    name=name,
                    ethiopian_year=eth_year if eth_year else 2016,
                    gregorian_start_date=start_date,
                    gregorian_end_date=end_date,
                    is_active=True
                )
                messages.success(request, f"Academic Year '{name}' added successfully and set as active!")
            except ValidationError as ve:
                err_msg = ", ".join(ve.messages) if hasattr(ve, 'messages') else str(ve)
                messages.error(request, f"Cannot add Academic Year: {err_msg}")
            except Exception as e:
                messages.error(request, f"Error adding Academic Year: {e}")
            return redirect('academics:config')

        elif action == 'update_calendar_preference':
            pref = request.POST.get('calendar_preference', 'ETHIOPIAN')
            if pref in ['ETHIOPIAN', 'GREGORIAN']:
                school.calendar_preference = pref
                school.save(update_fields=['calendar_preference'])
                messages.success(request, f"School Calendar Preference updated to {school.get_calendar_preference_display()}!")
            return redirect('academics:config')
            
        elif action in ['add_period', 'add_semester']:
            ay_id = request.POST.get('academic_year_id')
            name = request.POST.get('name')
            import datetime
            from apps.academics.ethiopian_date import ethiopian_to_gregorian

            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')

            eth_s_m = request.POST.get('eth_start_month')
            eth_s_d = request.POST.get('eth_start_day')
            eth_s_y = request.POST.get('eth_start_year')
            eth_e_m = request.POST.get('eth_end_month')
            eth_e_d = request.POST.get('eth_end_day')
            eth_e_y = request.POST.get('eth_end_year')

            if eth_s_m and eth_s_d and eth_s_y:
                calc_start = ethiopian_to_gregorian(eth_s_y, eth_s_m, eth_s_d)
                if calc_start:
                    start_date_str = calc_start.isoformat()
            if eth_e_m and eth_e_d and eth_e_y:
                calc_end = ethiopian_to_gregorian(eth_e_y, eth_e_m, eth_e_d)
                if calc_end:
                    end_date_str = calc_end.isoformat()

            start_date = datetime.date.fromisoformat(start_date_str) if start_date_str else None
            end_date = datetime.date.fromisoformat(end_date_str) if end_date_str else None
            
            ay = get_object_or_404(AcademicYear, id=ay_id, school=school)
            is_curr = bool(request.POST.get('is_current'))
            # If making this current, unset others
            if is_curr:
                AcademicPeriod.objects.filter(school=school).update(is_current=False)
                
            try:
                AcademicPeriod.objects.create(
                    school=school,
                    academic_year=ay,
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    is_current=is_curr
                )
                messages.success(request, f"Semester '{name}' added successfully!")
            except ValidationError as e:
                err_msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
                messages.error(request, f"Could not create semester: {err_msg}")
            return redirect('academics:config')

        elif action == 'add_grade':
            level = int(request.POST.get('level'))
            name = request.POST.get('name')
            stream_type = request.POST.get('stream_type', 'GEN')
            Grade.objects.create(school=school, level=level, name=name, stream_type=stream_type)
            messages.success(request, f"Grade '{name}' added successfully!")
            return redirect('academics:config')
            
        elif action == 'add_stream':
            name = request.POST.get('name')
            code = request.POST.get('code')
            Stream.objects.create(school=school, name=name, code=code)
            messages.success(request, f"Stream '{name}' added successfully!")
            return redirect('academics:config')
            
        elif action == 'seed_ethiopian_grades':
            # Auto-seed the 6 standard Ethiopian high school grades
            created = 0
            for g in ETHIOPIAN_GRADES:
                _, was_created = Grade.objects.get_or_create(
                    school=school,
                    level=g['level'],
                    stream_type=g['stream_type'],
                    defaults={'name': g['name']}
                )
                if was_created:
                    created += 1
            if created:
                messages.success(request, f"Seeded {created} Ethiopian grade(s): Grade 9, 10, 11(NS), 11(SS), 12(NS), 12(SS).")
            else:
                messages.info(request, "All Ethiopian grades already exist.")
            return redirect('academics:config')

        elif action == 'copy_previous_grades_sections':
            # 1. Ensure all 6 standard Ethiopian grades exist
            grades_created = 0
            for g in ETHIOPIAN_GRADES:
                _, was_created = Grade.objects.get_or_create(
                    school=school,
                    level=g['level'],
                    stream_type=g['stream_type'],
                    defaults={'name': g['name']}
                )
                if was_created:
                    grades_created += 1

            # 2. Get user section count preference (A, B, C, D)
            section_letters_input = request.POST.get('section_letters', 'A,B,C')
            section_letters = [s.strip().upper() for s in section_letters_input.split(',') if s.strip()]
            if not section_letters:
                section_letters = ['A', 'B']

            capacity = int(request.POST.get('capacity', 45))
            shift = request.POST.get('shift', 'FULL_DAY')

            sections_created = 0
            all_grades = Grade.objects.filter(school=school)
            for grade in all_grades:
                stream, _ = Stream.objects.get_or_create(
                    school=school,
                    code=grade.stream_type,
                    defaults={'name': dict(Grade.STREAM_TYPE_CHOICES).get(grade.stream_type, grade.stream_type)}
                )
                for sec_name in section_letters:
                    _, was_sec_created = Section.objects.get_or_create(
                        school=school,
                        grade=grade,
                        stream=stream,
                        name=sec_name,
                        defaults={'capacity': capacity, 'shift': shift}
                    )
                    if was_sec_created:
                        sections_created += 1

            messages.success(
                request,
                f"Academic structure updated successfully! {grades_created} new grade(s) and {sections_created} section(s) ({', '.join(section_letters)}) initialized."
            )
            return redirect('academics:config')

        elif action == 'add_section':
            grade_id = request.POST.get('grade_id')
            name = request.POST.get('name')
            capacity = int(request.POST.get('capacity', 45))
            shift = request.POST.get('shift', 'FULL_DAY')

            grade = get_object_or_404(Grade, id=grade_id, school=school)

            # Automatically resolve or create the stream from the grade's stream_type
            stream, _ = Stream.objects.get_or_create(
                school=school,
                code=grade.stream_type,
                defaults={'name': dict(Grade.STREAM_TYPE_CHOICES).get(grade.stream_type, grade.stream_type)}
            )

            Section.objects.create(
                school=school, grade=grade, stream=stream,
                name=name, capacity=capacity, shift=shift
            )
            messages.success(request, f"Section '{name}' added to {grade.name} successfully!")
            return redirect('academics:config')
            
        elif action == 'add_subject':
            code = request.POST.get('code')
            name = request.POST.get('name')
            amharic_name = request.POST.get('amharic_name')
            grade_id = request.POST.get('grade_id')
            
            grade = get_object_or_404(Grade, id=grade_id, school=school)
            stream, _ = Stream.objects.get_or_create(
                school=school, code=grade.stream_type,
                defaults={'name': dict(Grade.STREAM_TYPE_CHOICES).get(grade.stream_type, grade.stream_type)}
            )
            
            Subject.objects.create(
                school=school, code=code, name=name, amharic_name=amharic_name,
                grade=grade, stream=stream
            )
            messages.success(request, f"Subject '{name}' added successfully!")
            return redirect('academics:config')

        elif action == 'set_active_academic_year':
            year_id = request.POST.get('year_id')
            ay = get_object_or_404(AcademicYear, id=year_id, school=school)
            AcademicYear.objects.filter(school=school).update(is_active=False)
            ay.is_active = True
            ay.save()
            messages.success(request, f"'{ay.name}' is now the Active Academic Year!")
            return redirect('academics:config')

        elif action == 'delete_academic_year':
            year_id = request.POST.get('year_id')
            ay = get_object_or_404(AcademicYear, id=year_id, school=school)
            name = ay.name
            ay.delete()
            messages.success(request, f"Academic Year '{name}' deleted successfully.")
            return redirect('academics:config')

        elif action in ['delete_period', 'delete_semester']:
            sem_id = request.POST.get('semester_id') or request.POST.get('period_id')
            sem = get_object_or_404(AcademicPeriod, id=sem_id, school=school)
            name = sem.name
            sem.delete()
            messages.success(request, f"Semester '{name}' deleted successfully.")
            return redirect('academics:config')

        elif action == 'set_current_semester':
            sem_id = request.POST.get('semester_id') or request.POST.get('period_id')
            sem = get_object_or_404(AcademicPeriod, id=sem_id, school=school)
            AcademicPeriod.objects.filter(school=school).update(is_current=False)
            sem.is_current = True
            sem.save()
            messages.success(request, f"'{sem.name}' set as active current semester!")
            return redirect('academics:config')

        elif action == 'delete_grade':
            grade_id = request.POST.get('grade_id')
            grade = get_object_or_404(Grade, id=grade_id, school=school)
            name = grade.name
            grade.delete()
            messages.success(request, f"Grade '{name}' deleted successfully.")
            return redirect('academics:config')

        elif action == 'delete_section':
            sec_id = request.POST.get('section_id')
            sec = get_object_or_404(Section, id=sec_id, school=school)
            name = sec.name
            sec.delete()
            messages.success(request, f"Section '{name}' deleted successfully.")
            return redirect('academics:config')

        elif action == 'delete_subject':
            sub_id = request.POST.get('subject_id')
            sub = get_object_or_404(Subject, id=sub_id, school=school)
            name = sub.name
            sub.delete()
            messages.success(request, f"Subject '{name}' deleted successfully.")
            return redirect('academics:config')

    academic_years = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year')
    periods = AcademicPeriod.objects.filter(school=school).order_by('-start_date')
    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    streams = Stream.objects.filter(school=school)
    sections = Section.objects.filter(school=school).select_related('grade', 'stream', 'class_teacher', 'tutorial_teacher')
    subjects = Subject.objects.filter(school=school).select_related('grade', 'stream')
    teachers = User.objects.filter(school=school, is_active=True).order_by('first_name', 'last_name')

    # Build grades_with_sections: list of (grade, sections_qs) for the Sections tab
    active_year = academic_years.filter(is_active=True).first()
    grades_with_sections = []
    for grade in grades:
        grade_sections = sections.filter(grade=grade)
        grades_with_sections.append({'grade': grade, 'sections': grade_sections})

    return render(request, 'academics/config.html', {
        'academic_years': academic_years,
        'periods': periods,
        'semesters': periods,
        'grades': grades,
        'streams': streams,
        'sections': sections,
        'subjects': subjects,
        'teachers': teachers,
        'grades_with_sections': grades_with_sections,
        'active_year': active_year,
    })

@login_required
@csrf_exempt
def timetable_config_view(request):
    """
    Timetable scheduling interface for periods and assignments.
    """
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = getattr(request, 'school', None)
    if not school and request.user.school:
        school = request.user.school

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_period':
            name = request.POST.get('name')
            start = request.POST.get('start_time')
            end = request.POST.get('end_time')
            shift = request.POST.get('shift', 'FULL_DAY')
            PeriodSlot.objects.create(school=school, name=name, start_time=start, end_time=end, shift=shift)
            messages.success(request, f"Period '{name}' added.")
            return redirect('academics:timetable')
            
        elif action == 'add_slot':
            section_id = request.POST.get('section_id')
            subject_id = request.POST.get('subject_id')
            teacher_id = request.POST.get('teacher_id')
            day = request.POST.get('day_of_week')
            period_id = request.POST.get('period_id')
            room = request.POST.get('room')
            
            try:
                TimetableSlot.objects.create(
                    school=school,
                    section_id=section_id,
                    subject_id=subject_id,
                    teacher_id=teacher_id or None,
                    day_of_week=day,
                    period_slot_id=period_id,
                    room=room
                )
                messages.success(request, "Timetable slot scheduled successfully.")
            except Exception as e:
                messages.error(request, f"Scheduling Conflict/Error: {str(e)}")
            return redirect('academics:timetable')

    periods = PeriodSlot.objects.filter(school=school).order_by('start_time')
    sections = Section.objects.filter(school=school).select_related('grade', 'stream')
    subjects = Subject.objects.filter(school=school)
    teachers = TeacherProfile.objects.filter(school=school).select_related('user')
    slots = TimetableSlot.objects.filter(school=school).select_related('section', 'subject', 'teacher__user', 'period_slot').order_by('day_of_week', 'period_slot__start_time')

    return render(request, 'academics/timetable.html', {
        'periods': periods,
        'sections': sections,
        'subjects': subjects,
        'teachers': teachers,
        'slots': slots,
    })

@login_required
def switch_academic_year_view(request):
    """
    Handles switching the contextual academic year.
    Takes year_id via POST and saves it in the session.
    Only allows switching for Admin/Super Admin roles.
    Students, Parents, and Teachers are locked to the active academic year.
    """
    if request.method == 'POST':
        user = request.user
        is_admin_or_super = user.is_authenticated and (user.is_superuser or user.role in ['SCHOOL_ADMIN', 'SUPER_ADMIN', 'PRINCIPAL', 'REGISTRAR'])
        
        if not is_admin_or_super:
            messages.error(request, "Students, parents, and teachers are locked to the active academic year.")
            referer = request.META.get('HTTP_REFERER')
            return redirect(referer or 'index')

        year_id = request.POST.get('year_id')
        if year_id:
            try:
                school = getattr(request, 'school', getattr(request.user, 'school', None))
                target_ay = AcademicYear.objects.filter(id=year_id, school=school).first()
                active_ay = AcademicYear.objects.filter(school=school, is_active=True).first()

                if target_ay:
                    if active_ay and target_ay.gregorian_start_date > active_ay.gregorian_start_date and not target_ay.is_active:
                        messages.error(request, "Cannot switch context to a future academic year that has not been activated via Rollover.")
                    else:
                        request.session['selected_academic_year_id'] = year_id
                        messages.success(request, f"Academic year context switched to {target_ay.name}.")
            except Exception as e:
                pass
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
    return redirect('index')


@login_required
@csrf_exempt
def switch_calendar_preference_view(request):
    """
    Switches the active calendar preference for the session and school.
    Available to all roles (Admin, Teacher, Student, Parent).
    """
    if request.method == 'POST':
        pref = request.POST.get('calendar_preference')
        if pref in ['ETHIOPIAN', 'GREGORIAN']:
            request.session['calendar_preference'] = pref
            
            user = request.user
            school = getattr(request, 'school', getattr(user, 'school', None))
            if school and (user.is_superuser or getattr(user, 'role', None) in ['SCHOOL_ADMIN', 'SUPER_ADMIN']):
                school.calendar_preference = pref
                school.save(update_fields=['calendar_preference'])

            display_name = 'Ethiopian Calendar (E.C.)' if pref == 'ETHIOPIAN' else 'Gregorian Calendar (G.C.)'
            messages.success(request, f"Calendar mode switched to {display_name}. System dates updated across all views!")
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
    return redirect('index')
