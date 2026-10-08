import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View, TemplateView, ListView
from django.contrib import messages
from django.db.models import Count, Q

from apps.academics.models import Section
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord, StaffAttendanceRecord, AttendanceStatus, StaffAttendanceStatus, TutorialAttendanceRecord
from apps.attendance.forms import StudentAttendanceFormSet, StaffAttendanceFormSet
from apps.accounts.models import User, UserRole
from apps.enrollment.models import StudentEnrollment
from apps.messaging.models import Conversation, Message
from apps.platform_management.decorators import school_context_required
from django.utils.decorators import method_decorator


def get_school(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)


class SectionAttendanceView(LoginRequiredMixin, View):
    template_name = 'attendance/take_attendance.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == 'TEACHER':
            messages.info(request, "Daily class attendance for teachers is managed in the Homeroom Portal.")
            return redirect('teachers:homeroom')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, section_id):
        school = get_school(request)
        section = get_object_or_404(Section, id=section_id, school=school)
        date_str = request.GET.get('date', datetime.date.today().isoformat())
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        current_ay = getattr(request, 'academic_year', None)

        active_enrollment_q = {'school': school, 'section': section, 'status': 'ACTIVE'}
        if current_ay:
            active_enrollment_q['academic_year'] = current_ay

        active_student_ids = StudentEnrollment.objects.filter(**active_enrollment_q).values_list('student_id', flat=True)
        students = StudentProfile.objects.filter(id__in=active_student_ids).order_by('first_name', 'last_name')

        from apps.academics.ethiopian_date import get_attendance_calendar_context
        cal_ctx = get_attendance_calendar_context(date, school, section, current_ay)
        date = cal_ctx['selected_date']

        existing_records = AttendanceRecord.objects.filter(
            school=school, section=section, date=date, student_id__in=active_student_ids
        ).select_related('student').order_by('student__first_name', 'student__last_name')

        rec_dict = {rec.student_id: rec for rec in existing_records}

        student_rows = []
        for student in students:
            existing_rec = rec_dict.get(student.id)
            student_rows.append({
                'student': student,
                'status': existing_rec.status if existing_rec else AttendanceStatus.PRESENT,
                'reason': existing_rec.reason if existing_rec else '',
            })

        # Calculate monthly student statistics
        month_start = cal_ctx['month_days'][0]['date']
        month_end = cal_ctx['month_days'][-1]['date']

        month_records = AttendanceRecord.objects.filter(
            school=school, section=section, date__gte=month_start, date__lte=month_end, student_id__in=active_student_ids
        )
        student_monthly_stats = {}
        for st_id in active_student_ids:
            st_recs = month_records.filter(student_id=st_id)
            total_st = st_recs.count()
            pres_st = st_recs.filter(status=AttendanceStatus.PRESENT).count()
            abs_st = st_recs.filter(status=AttendanceStatus.ABSENT).count()
            rate_st = round((pres_st / total_st * 100), 1) if total_st > 0 else 100.0
            student_monthly_stats[st_id] = {
                'total': total_st,
                'present': pres_st,
                'absent': abs_st,
                'rate': rate_st
            }

        for row in student_rows:
            row['monthly_stats'] = student_monthly_stats.get(row['student'].id)

        prev_date = date - datetime.timedelta(days=1)
        next_date = date + datetime.timedelta(days=1)

        if request.GET.get('export') in ['excel', 'csv']:
            import csv
            from django.http import HttpResponse
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            filename = f"Attendance_{section.name}_{date.strftime('%Y-%m-%d')}.csv"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            writer = csv.writer(response)
            writer.writerow([f"School: {school.name if school else 'N/A'}", f"Section: {section.name}", f"Date: {date}"])
            writer.writerow([])
            writer.writerow(["Student ID", "Student Name", "Attendance Status", "Reason / Remarks", "Monthly Attendance Rate (%)"])

            for row in student_rows:
                st = row['student']
                m_stat = row.get('monthly_stats') or {}
                rate_str = f"{m_stat.get('rate', 100.0)}%" if m_stat else "100.0%"
                writer.writerow([
                    st.student_id,
                    st.full_name,
                    row['status'],
                    row['reason'],
                    rate_str
                ])
            return response

        context = {
            'section': section,
            'date': date,
            'prev_date': prev_date.strftime('%Y-%m-%d'),
            'next_date': next_date.strftime('%Y-%m-%d'),
            'student_rows': student_rows,
            'attendance_status_choices': AttendanceStatus.choices,
            'active_students_count': len(active_student_ids),
            'title': f'Attendance for {section.name} on {date}'
        }
        context.update(cal_ctx)
        return render(request, self.template_name, context)

    def post(self, request, section_id):
        school = get_school(request)
        section = get_object_or_404(Section, id=section_id, school=school)
        date_str = request.POST.get('date', datetime.date.today().isoformat())
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        current_ay = getattr(request, 'academic_year', None)

        # Enforce locked period protection for attendance records
        from apps.academics.models import AcademicPeriod, PeriodStatus
        locked_period = AcademicPeriod.objects.filter(
            school=school,
            start_date__lte=date,
            end_date__gte=date,
            status__in=[PeriodStatus.LOCKED, PeriodStatus.CLOSED, PeriodStatus.ARCHIVED]
        ).first()

        can_override = getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL']
        if locked_period and not can_override:
            status_desc = locked_period.get_status_display() if hasattr(locked_period, 'get_status_display') else locked_period.status
            messages.error(request, f"Attendance for {date} is locked because '{locked_period.name}' is {status_desc}. Contact administration.")
            return redirect(f"{request.path}?date={date.isoformat()}")
        active_enrollment_q = {'school': school, 'section': section, 'status': 'ACTIVE'}
        if current_ay:
            active_enrollment_q['academic_year'] = current_ay

        active_student_ids = StudentEnrollment.objects.filter(**active_enrollment_q).values_list('student_id', flat=True)
        students = StudentProfile.objects.filter(id__in=active_student_ids)

        for student in students:
            status_val = request.POST.get(f'status_{student.id}', AttendanceStatus.PRESENT)
            reason_val = request.POST.get(f'reason_{student.id}', '')
            if status_val in dict(AttendanceStatus.choices):
                rec, created = AttendanceRecord.objects.update_or_create(
                    school=school,
                    section=section,
                    student=student,
                    date=date,
                    defaults={
                        'status': status_val,
                        'reason': reason_val,
                        'recorded_by': request.user
                    }
                )
                
                # Check for absence to send notification via Messaging
                if rec.status == AttendanceStatus.ABSENT:
                    parents = student.parents.all()
                    for parent in parents:
                        convo = Conversation.objects.filter(
                            school=school,
                            subject=f"Attendance Alert: {student.first_name}"
                        ).first()
                        
                        if not convo:
                            convo = Conversation.objects.create(
                                school=school,
                                subject=f"Attendance Alert: {student.first_name}",
                                created_by=request.user
                            )
                            convo.participants.add(request.user, parent.user)
                            
                        Message.objects.create(
                            conversation=convo,
                            sender=request.user,
                            content=f"Attendance Alert: {student.full_name} was marked ABSENT on {date.strftime('%Y-%m-%d')}. Reason: {reason_val or 'No reason provided'}."
                        )

        messages.success(request, f"Attendance records for {section.name} on {date.strftime('%b %d, %Y')} saved successfully.")
        return redirect(f"/attendance/section/{section.id}/?date={date.strftime('%Y-%m-%d')}")


class StaffAttendanceView(LoginRequiredMixin, View):
    template_name = 'attendance/staff_attendance.html'

    def get_staff_users(self, school, staff_category='all'):
        from apps.teachers.models import StaffProfile
        teaching_users = User.objects.filter(school=school, role=UserRole.TEACHER)
        non_teaching_roles = [UserRole.SCHOOL_ADMIN, UserRole.REGISTRAR, UserRole.ACCOUNTANT]
        staff_profile_user_ids = StaffProfile.objects.filter(school=school).values_list('user_id', flat=True)
        non_teaching_users = User.objects.filter(school=school).filter(
            Q(role__in=non_teaching_roles) | Q(id__in=staff_profile_user_ids)
        )

        if staff_category == 'teaching':
            return teaching_users.distinct().order_by('first_name', 'last_name')
        elif staff_category == 'non_teaching':
            return non_teaching_users.exclude(role=UserRole.TEACHER).distinct().order_by('first_name', 'last_name')
        else:
            all_user_ids = set(teaching_users.values_list('id', flat=True)).union(set(non_teaching_users.values_list('id', flat=True)))
            return User.objects.filter(id__in=all_user_ids, school=school).order_by('first_name', 'last_name')

    def get(self, request):
        if request.user.role not in [UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN, UserRole.PRINCIPAL]:
            messages.error(request, 'You do not have permission to record staff attendance.')
            return redirect('core:home')

        school = get_school(request)
        date_str = request.GET.get('date', datetime.date.today().isoformat())
        staff_category = request.GET.get('category', 'all').strip().lower()
        if staff_category not in ['all', 'teaching', 'non_teaching']:
            staff_category = 'all'

        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        staff_members = self.get_staff_users(school, staff_category)

        for staff in staff_members:
            StaffAttendanceRecord.objects.get_or_create(
                school=school,
                staff_user=staff,
                date=date,
                defaults={'status': StaffAttendanceStatus.PRESENT, 'recorded_by': request.user}
            )

        queryset = StaffAttendanceRecord.objects.filter(
            school=school, date=date, staff_user__in=staff_members
        ).select_related('staff_user', 'staff_user__staff_profile').order_by('staff_user__first_name', 'staff_user__last_name')

        formset = StaffAttendanceFormSet(queryset=queryset)

        # Monthly metrics for modal/export helper
        today = datetime.date.today()
        context = {
            'date': date,
            'formset': formset,
            'staff_category': staff_category,
            'current_month': today.month,
            'current_year': today.year,
            'title': f'Staff Attendance for {date}'
        }
        return render(request, self.template_name, context)

    def post(self, request):
        if request.user.role not in [UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN, UserRole.PRINCIPAL]:
            messages.error(request, 'You do not have permission to record staff attendance.')
            return redirect('core:home')

        school = get_school(request)
        date_str = request.POST.get('date', datetime.date.today().isoformat())
        staff_category = request.POST.get('category', 'all').strip().lower()
        if staff_category not in ['all', 'teaching', 'non_teaching']:
            staff_category = 'all'

        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        staff_members = self.get_staff_users(school, staff_category)
        queryset = StaffAttendanceRecord.objects.filter(school=school, date=date, staff_user__in=staff_members)
        formset = StaffAttendanceFormSet(request.POST, queryset=queryset)

        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.recorded_by = request.user
                instance.save()

            messages.success(request, f'Staff attendance for {date.strftime("%b %d, %Y")} saved successfully.')
            return redirect(f"{request.path}?date={date.isoformat()}&category={staff_category}")

        context = {
            'date': date,
            'formset': formset,
            'staff_category': staff_category,
            'title': f'Staff Attendance for {date}'
        }
        return render(request, self.template_name, context)


class StaffAttendanceExportView(LoginRequiredMixin, View):
    """
    Exports monthly staff attendance records for teaching & non-teaching staff in CSV or Excel format.
    """
    def get(self, request):
        if request.user.role not in [UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
            messages.error(request, 'Permission denied.')
            return redirect('core:home')

        school = get_school(request)
        month_str = request.GET.get('month')
        year_str = request.GET.get('year')
        category = request.GET.get('category', 'all').strip().lower()
        fmt = request.GET.get('format', 'csv').lower()

        today = datetime.date.today()
        month = int(month_str) if month_str and month_str.isdigit() else today.month
        year = int(year_str) if year_str and year_str.isdigit() else today.year

        import calendar
        _, last_day = calendar.monthrange(year, month)
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, last_day)

        staff_helper = StaffAttendanceView()
        staff_members = staff_helper.get_staff_users(school, category).select_related('staff_profile')

        records = StaffAttendanceRecord.objects.filter(
            school=school,
            date__gte=start_date,
            date__lte=end_date,
            staff_user__in=staff_members
        )

        summary_rows = []
        for s in staff_members:
            user_recs = records.filter(staff_user=s)
            total = user_recs.count()
            pres = user_recs.filter(status=StaffAttendanceStatus.PRESENT).count()
            absent = user_recs.filter(status=StaffAttendanceStatus.ABSENT).count()
            late = user_recs.filter(status=StaffAttendanceStatus.LATE).count()
            leave = user_recs.filter(status=StaffAttendanceStatus.LEAVE).count()
            excused = user_recs.filter(status=StaffAttendanceStatus.EXCUSED).count()

            pct = round(((pres + (late * 0.5) + excused) / total) * 100, 1) if total > 0 else 100.0

            emp_id = "N/A"
            position = s.get_role_display() if hasattr(s, 'get_role_display') else s.role
            staff_type = "Teaching" if s.role == UserRole.TEACHER else "Non-Teaching"

            # Check teacher profile
            t_prof = getattr(s, 'teacher_profile', None)
            s_prof = getattr(s, 'staff_profile', None)
            if t_prof:
                emp_id = t_prof.employee_id
                position = f"Teacher ({t_prof.department or 'Academics'})"
            elif s_prof:
                emp_id = s_prof.employee_id
                position = s_prof.get_position_display()
                staff_type = "Non-Teaching"

            summary_rows.append({
                'employee_id': emp_id,
                'name': s.get_full_name() or s.username,
                'staff_type': staff_type,
                'position': position,
                'total_days': total,
                'present': pres,
                'absent': absent,
                'late': late,
                'leave': leave,
                'excused': excused,
                'rate': f"{pct}%"
            })

        month_label = f"{calendar.month_name[month]}_{year}"
        filename = f"Staff_Attendance_Report_{month_label}_{category}"

        if fmt == 'xlsx':
            import openpyxl
            from django.http import HttpResponse

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Staff Attendance"

            ws.append([f"Staff Attendance Monthly Report - {school.name if school else 'School'}"])
            ws.append([f"Month: {calendar.month_name[month]} {year} | Staff Category: {category.upper()}"])
            ws.append([])
            headers = ["Employee ID", "Staff Name", "Staff Type", "Department / Position", "Logged Days", "Present", "Absent", "Late", "On Leave", "Excused", "Attendance %"]
            ws.append(headers)

            for r in summary_rows:
                ws.append([
                    r['employee_id'], r['name'], r['staff_type'], r['position'],
                    r['total_days'], r['present'], r['absent'], r['late'], r['leave'], r['excused'], r['rate']
                ])

            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            wb.save(response)
            return response
        else:
            import csv
            from django.http import HttpResponse

            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
            writer = csv.writer(response)

            writer.writerow([f"Staff Attendance Monthly Report - {school.name if school else 'School'}"])
            writer.writerow([f"Month: {calendar.month_name[month]} {year}", f"Category: {category.upper()}"])
            writer.writerow([])
            writer.writerow(["Employee ID", "Staff Name", "Staff Type", "Department / Position", "Logged Days", "Present", "Absent", "Late", "On Leave", "Excused", "Attendance %"])

            for r in summary_rows:
                writer.writerow([
                    r['employee_id'], r['name'], r['staff_type'], r['position'],
                    r['total_days'], r['present'], r['absent'], r['late'], r['leave'], r['excused'], r['rate']
                ])
            return response


@method_decorator(school_context_required, name='dispatch')
class AttendanceReportSummaryView(LoginRequiredMixin, TemplateView):
    template_name = 'attendance/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = get_school(self.request)
        pref = getattr(school, 'calendar_preference', 'ETHIOPIAN') if school else 'ETHIOPIAN'

        from apps.academics.ethiopian_date import (
            gregorian_to_ethiopian,
            ethiopian_to_gregorian,
            ETHIOPIAN_MONTHS,
            ETHIOPIAN_MONTHS_AMHARIC
        )

        today = datetime.date.today()
        selected_section_id = self.request.GET.get('section_id', '')

        raw_month = self.request.GET.get('month')
        raw_year = self.request.GET.get('year')

        eth_today_y, eth_today_m, _ = gregorian_to_ethiopian(today)

        current_ay = getattr(self.request, 'academic_year', None)

        if pref == 'ETHIOPIAN':
            def_year = current_ay.ethiopian_year if (current_ay and hasattr(current_ay, 'ethiopian_year')) else eth_today_y
            def_month = eth_today_m
            if current_ay and current_ay.gregorian_start_date and current_ay.gregorian_end_date:
                if not (current_ay.gregorian_start_date <= today <= current_ay.gregorian_end_date):
                    def_month = 1

            try:
                year = int(raw_year) if raw_year else def_year
                month = int(raw_month) if raw_month else def_month
            except (ValueError, TypeError):
                year = def_year
                month = def_month

            # Smart translation: Only convert if year is clearly Gregorian (>= 2025)
            if year >= 2025:
                calc_g_month = max(1, min(12, month))
                conv = gregorian_to_ethiopian(datetime.date(year, calc_g_month, 15))
                if conv:
                    year, month, _ = conv

            month = max(1, min(13, month))

            # Compute Gregorian bounds for Ethiopian month
            start_date = ethiopian_to_gregorian(year, month, 1)
            end_day = 5 if month == 13 else 30
            end_date = ethiopian_to_gregorian(year, month, end_day)

            month_name = ETHIOPIAN_MONTHS[month] if 1 <= month <= 13 else str(month)
            month_label = f"{month_name} ({year} E.C.)"

            month_choices = [(i, f"{ETHIOPIAN_MONTHS[i]} ({i})") for i in range(1, 14)]
        else:
            def_year = current_ay.gregorian_start_date.year if (current_ay and current_ay.gregorian_start_date) else today.year
            def_month = today.month
            if current_ay and current_ay.gregorian_start_date and current_ay.gregorian_end_date:
                if not (current_ay.gregorian_start_date <= today <= current_ay.gregorian_end_date):
                    def_month = current_ay.gregorian_start_date.month

            try:
                year = int(raw_year) if raw_year else def_year
                month = int(raw_month) if raw_month else def_month
            except (ValueError, TypeError):
                year = def_year
                month = def_month

            # Smart translation: Only convert if year is clearly Ethiopian (< 2025)
            if year < 2025:
                calc_e_month = max(1, min(13, month))
                conv_g = ethiopian_to_gregorian(year, calc_e_month, 15)
                if conv_g:
                    year = conv_g.year
                    month = conv_g.month

            month = max(1, min(12, month))

            import calendar
            _, last_day = calendar.monthrange(year, month)
            start_date = datetime.date(year, month, 1)
            end_date = datetime.date(year, month, last_day)

            m_name = calendar.month_name[month]
            month_label = f"{m_name} {year} G.C."

            month_choices = [(i, calendar.month_name[i]) for i in range(1, 13)]

        current_ay = getattr(self.request, 'academic_year', None)

        # Only include attendance records for students actively enrolled this year
        active_student_ids = StudentEnrollment.objects.filter(
            school=school, status='ACTIVE',
            **({'academic_year': current_ay} if current_ay else {})
        ).values_list('student_id', flat=True).distinct() if school else []

        records = AttendanceRecord.objects.filter(
            school=school,
            date__gte=start_date,
            date__lte=end_date,
            student_id__in=active_student_ids
        ) if school else AttendanceRecord.objects.none()

        if selected_section_id:
            records = records.filter(section_id=selected_section_id)

        total_records = records.count()
        present = records.filter(status=AttendanceStatus.PRESENT).count()
        absent = records.filter(status=AttendanceStatus.ABSENT).count()
        late = records.filter(status=AttendanceStatus.LATE).count()
        excused = records.filter(status=AttendanceStatus.EXCUSED).count()

        if total_records > 0:
            percentage = round(((present + (late * 0.5) + excused) / total_records) * 100, 1)
        else:
            percentage = 100.0

        staff_records = StaffAttendanceRecord.objects.filter(
            school=school,
            date__gte=start_date,
            date__lte=end_date
        ) if school else StaffAttendanceRecord.objects.none()

        staff_total = staff_records.count()
        staff_present = staff_records.filter(status=StaffAttendanceStatus.PRESENT).count()
        staff_absent = staff_records.filter(status=StaffAttendanceStatus.ABSENT).count()
        staff_late = staff_records.filter(status=StaffAttendanceStatus.LATE).count()
        staff_leave = staff_records.filter(status=StaffAttendanceStatus.LEAVE).count()
        staff_excused = staff_records.filter(status=StaffAttendanceStatus.EXCUSED).count()

        if staff_total > 0:
            staff_percentage = round(((staff_present + (staff_late * 0.5) + staff_excused + staff_leave) / staff_total) * 100, 1)
        else:
            staff_percentage = 100.0

        at_risk = StudentProfile.objects.filter(
            school=school,
            id__in=active_student_ids,
            attendance_records__status=AttendanceStatus.ABSENT,
            attendance_records__date__gte=start_date,
            attendance_records__date__lte=end_date
        ).annotate(
            absence_count=Count('attendance_records')
        ).filter(absence_count__gte=3).order_by('-absence_count')[:15] if school else []

        # Only show sections that have enrollments in the active academic year
        sections_qs = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name') if school else []
        if current_ay:
            active_section_ids = StudentEnrollment.objects.filter(
                school=school, academic_year=current_ay, status='ACTIVE'
            ).values_list('section_id', flat=True).distinct()
            sections_qs = sections_qs.filter(id__in=active_section_ids)
        sections = sections_qs
        section_breakdown = []

        for sec in sections:
            sec_active_student_ids = StudentEnrollment.objects.filter(
                school=school, section=sec, status='ACTIVE',
                **({'academic_year': current_ay} if current_ay else {})
            ).values_list('student_id', flat=True)

            sec_records = AttendanceRecord.objects.filter(
                school=school,
                section=sec,
                date__gte=start_date,
                date__lte=end_date,
                student_id__in=sec_active_student_ids
            )
            s_total = sec_records.count()
            s_pres = sec_records.filter(status=AttendanceStatus.PRESENT).count()
            s_abs = sec_records.filter(status=AttendanceStatus.ABSENT).count()
            s_late = sec_records.filter(status=AttendanceStatus.LATE).count()
            s_exc = sec_records.filter(status=AttendanceStatus.EXCUSED).count()

            s_pct = round(((s_pres + (s_late * 0.5) + s_exc) / s_total) * 100, 1) if s_total > 0 else 100.0

            section_breakdown.append({
                'id': sec.id,
                'name': sec.name,
                'grade': sec.grade.name if sec.grade else '',
                'student_count': StudentEnrollment.objects.filter(
                    school=school, section=sec, status='ACTIVE',
                    **({'academic_year': current_ay} if current_ay else {})
                ).count(),
                'total_records': s_total,
                'present': s_pres,
                'absent': s_abs,
                'late': s_late,
                'excused': s_exc,
                'percentage': s_pct
            })

        context.update({
            'month': month,
            'year': year,
            'month_label': month_label,
            'month_choices': month_choices,
            'sections': sections,
            'selected_section_id': selected_section_id,
            'section_breakdown': section_breakdown,

            'total_records': total_records,
            'present_count': present,
            'absent_count': absent,
            'late_count': late,
            'excused_count': excused,
            'overall_percentage': percentage,

            'staff_total': staff_total,
            'staff_present': staff_present,
            'staff_absent': staff_absent,
            'staff_late': staff_late,
            'staff_leave': staff_leave,
            'staff_percentage': staff_percentage,

            'at_risk_students': at_risk,
            'title': 'Attendance Reports & Analytics'
        })
        return context


class TutorialAttendanceView(LoginRequiredMixin, View):
    template_name = 'attendance/tutorial_attendance.html'

    def get(self, request):
        school = get_school(request)
        user = request.user
        
        if user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
            sections = Section.objects.filter(school=school).select_related('grade', 'stream', 'tutorial_teacher', 'class_teacher')
        elif user.role == UserRole.TEACHER:
            sections = Section.objects.filter(school=school, tutorial_teacher=user).select_related('grade', 'stream', 'tutorial_teacher', 'class_teacher')
            if not sections.exists():
                sections = Section.objects.filter(school=school, class_teacher=user).select_related('grade', 'stream', 'tutorial_teacher', 'class_teacher')
                if not sections.exists():
                    sections = Section.objects.filter(school=school).select_related('grade', 'stream', 'tutorial_teacher', 'class_teacher')
        else:
            sections = Section.objects.filter(school=school).select_related('grade', 'stream', 'tutorial_teacher', 'class_teacher')

        selected_section_id = request.GET.get('section_id')
        selected_section = None
        if selected_section_id:
            selected_section = sections.filter(id=selected_section_id).first()
        if not selected_section and sections.exists():
            selected_section = sections.first()

        date_str = request.GET.get('date', datetime.date.today().isoformat())
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        current_ay = getattr(request, 'academic_year', None)

        from apps.academics.ethiopian_date import get_attendance_calendar_context
        cal_ctx = get_attendance_calendar_context(
            date, school, selected_section, current_ay, record_model=TutorialAttendanceRecord
        )
        date = cal_ctx['selected_date']

        students = []
        rec_dict = {}
        if selected_section:
            active_enrollment_q = {'school': school, 'section': selected_section, 'status': 'ACTIVE'}
            if current_ay:
                active_enrollment_q['academic_year'] = current_ay

            active_student_ids = StudentEnrollment.objects.filter(**active_enrollment_q).values_list('student_id', flat=True)
            students = StudentProfile.objects.filter(id__in=active_student_ids).order_by('first_name', 'last_name')

            existing_records = TutorialAttendanceRecord.objects.filter(
                school=school, section=selected_section, date=date, student_id__in=active_student_ids
            )
            rec_dict = {rec.student_id: rec for rec in existing_records}

        student_rows = []
        for s in students:
            rec = rec_dict.get(s.id)
            student_rows.append({
                'student': s,
                'status': rec.status if rec else AttendanceStatus.PRESENT,
                'reason': rec.reason if rec else '',
            })

        export = request.GET.get('export')
        if export in ['excel', 'csv', 'pdf'] and selected_section:
            rec_rows = []
            for r in student_rows:
                st = r['student']
                rec_rows.append({
                    'student_id': st.student_id,
                    'student_name': st.full_name,
                    'status': r['status'],
                    'reason': r['reason']
                })

            if export in ['excel', 'csv']:
                import csv
                from django.http import HttpResponse
                response = HttpResponse(content_type='text/csv; charset=utf-8')
                filename = f"Tutorial_Attendance_{selected_section.name}_{date.strftime('%Y-%m-%d')}.csv"
                response['Content-Disposition'] = f'attachment; filename="{filename}"'

                writer = csv.writer(response)
                writer.writerow([f"School: {school.name if school else 'N/A'}", f"Tutorial Section: {selected_section.grade.name} - {selected_section.name}", f"Date: {date}"])
                writer.writerow([f"Tutorial Controller: {selected_section.tutorial_teacher.get_full_name() if selected_section.tutorial_teacher else 'N/A'}"])
                writer.writerow([])
                writer.writerow(["Student ID", "Student Name", "Tutorial Status", "Reason / Remarks"])

                for rr in rec_rows:
                    writer.writerow([rr['student_id'], rr['student_name'], rr['status'], rr['reason']])
                return response

            elif export == 'pdf':
                from utils.pdf_utils import generate_attendance_pdf
                from django.http import HttpResponse
                pdf_bytes = generate_attendance_pdf(
                    school_name=school.name if school else "School",
                    title="TUTORIAL ATTENDANCE SHEET",
                    section_name=f"{selected_section.grade.name} - {selected_section.name}",
                    date_str=date.strftime('%b %d, %Y'),
                    controller_name=selected_section.tutorial_teacher.get_full_name() if selected_section.tutorial_teacher else "N/A",
                    records=rec_rows
                )
                filename = f"Tutorial_Attendance_{selected_section.name}_{date.strftime('%Y-%m-%d')}.pdf"
                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response

        context = {
            'sections': sections,
            'selected_section': selected_section,
            'students': student_rows,
            'date': date,
            'date_str': date.isoformat(),
        }
        context.update(cal_ctx)
        return render(request, self.template_name, context)

    def post(self, request):
        school = get_school(request)
        section_id = request.POST.get('section_id')
        section = get_object_or_404(Section, id=section_id, school=school)
        date_str = request.POST.get('date', datetime.date.today().isoformat())
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = datetime.date.today()

        current_ay = getattr(request, 'academic_year', None)
        active_enrollment_q = {'school': school, 'section': section, 'status': 'ACTIVE'}
        if current_ay:
            active_enrollment_q['academic_year'] = current_ay

        active_student_ids = StudentEnrollment.objects.filter(**active_enrollment_q).values_list('student_id', flat=True)
        students = StudentProfile.objects.filter(id__in=active_student_ids)

        for s in students:
            status_val = request.POST.get(f'status_{s.id}', AttendanceStatus.PRESENT)
            reason_val = request.POST.get(f'reason_{s.id}', '')

            TutorialAttendanceRecord.objects.update_or_create(
                school=school,
                section=section,
                student=s,
                date=date,
                defaults={
                    'status': status_val,
                    'reason': reason_val,
                    'recorded_by': request.user
                }
            )

        messages.success(request, f"Tutorial attendance for {section.grade.name} - Section {section.name} saved successfully for {date}!")
        return redirect(f"{request.path}?section_id={section.id}&date={date.isoformat()}")
