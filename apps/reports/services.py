from decimal import Decimal
from django.db.models import Avg, Count
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Section, Grade, Stream
from apps.students.models import StudentProfile, StudentStatus, StudentDemographics
from apps.teachers.models import TeacherProfile
from apps.enrollment.models import StudentEnrollment, StudentTransfer, EnrollmentStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.assessments.models import StudentMark
from apps.reports.models import RegionalReportTemplate


class EthiopianEducationReportingService:
    """
    Ethiopian Education Administration & Regional/Woreda Standardized Reporting Engine.
    Generates configurable regional statistics reports according to MoE or regional templates.
    Dynamically aggregates custom demographic fields without hard-coded assumptions.
    """
    @staticmethod
    def generate_standardized_report(school: School, academic_year: AcademicYear, template: RegionalReportTemplate = None) -> dict:
        config = template.config_json if template and template.config_json else {}

        # 1. Total Students & Gender Breakdown
        students = StudentProfile.objects.filter(school=school)
        total_students = students.count()
        male_count = students.filter(gender='M').count()
        female_count = students.filter(gender='F').count()

        # 2. Configurable Dynamic Demographics Aggregation (Requirement 5)
        custom_demographics_summary = {}
        demographics = StudentDemographics.objects.filter(school=school)
        for demo in demographics:
            for key, val in demo.custom_demographics.items():
                if key not in custom_demographics_summary:
                    custom_demographics_summary[key] = {}
                str_val = str(val)
                custom_demographics_summary[key][str_val] = custom_demographics_summary[key].get(str_val, 0) + 1

        # 3. Students by Grade
        students_by_grade = {}
        for g in Grade.objects.filter(school=school):
            students_by_grade[g.name] = StudentEnrollment.objects.filter(
                school=school, academic_year=academic_year, grade=g, status=EnrollmentStatus.ACTIVE
            ).count()

        # 4. Students by Stream
        students_by_stream = {}
        for st in Stream.objects.filter(school=school):
            students_by_stream[st.name] = StudentEnrollment.objects.filter(
                school=school, academic_year=academic_year, stream=st, status=EnrollmentStatus.ACTIVE
            ).count()

        # 5. Teachers Count
        teachers_count = TeacherProfile.objects.filter(school=school).count()

        # 6. Attendance Statistics
        att_records = AttendanceRecord.objects.filter(school=school, date__gte=academic_year.gregorian_start_date, date__lte=academic_year.gregorian_end_date)
        total_att = att_records.count()
        present_att = att_records.filter(status=AttendanceStatus.PRESENT).count()
        attendance_rate = 100.0 if total_att == 0 else (present_att / total_att) * 100.0

        # 7. Pass / Fail Statistics
        marks = StudentMark.objects.filter(school=school, assessment_component__academic_year=academic_year)
        passed_marks = marks.filter(mark_value__gte=Decimal('50.00')).count()
        failed_marks = marks.filter(mark_value__lt=Decimal('50.00')).count()
        total_marks = marks.count()
        pass_rate = 100.0 if total_marks == 0 else (passed_marks / total_marks) * 100.0

        # 8. Dropout / Withdrawal / Graduation
        dropout_withdrawal_count = students.filter(status__in=[StudentStatus.WITHDRAWN, StudentStatus.SUSPENDED]).count()
        graduation_count = students.filter(status=StudentStatus.GRADUATED).count()

        # 9. Transfers Count
        transfers_count = StudentTransfer.objects.filter(school=school).count()

        # 10. Active Enrollment Count
        enrollment_count = StudentEnrollment.objects.filter(school=school, academic_year=academic_year, status=EnrollmentStatus.ACTIVE).count()

        # 11. School Capacity Statistics
        sections = Section.objects.filter(school=school)
        total_capacity = sum(s.capacity for s in sections)
        capacity_utilization = 100.0 if total_capacity == 0 else (enrollment_count / total_capacity) * 100.0

        # 12. Academic Performance
        avg_score = marks.aggregate(avg=Avg('mark_value'))['avg'] or 0.0

        report = {
            'school_info': {
                'name': school.name,
                'code': school.code,
                'region': school.region,
                'woreda': school.woreda,
                'academic_year': academic_year.name,
            },
            'total_students': total_students,
            'gender_breakdown': {'male': male_count, 'female': female_count},
            'custom_demographics_summary': custom_demographics_summary,
            'students_by_grade': students_by_grade,
            'students_by_stream': students_by_stream,
            'teachers_count': teachers_count,
            'attendance_rate_percentage': round(attendance_rate, 2),
            'pass_fail_statistics': {'passed': passed_marks, 'failed': failed_marks, 'pass_rate': round(pass_rate, 2)},
            'dropout_withdrawal_count': dropout_withdrawal_count,
            'graduation_count': graduation_count,
            'transfers_count': transfers_count,
            'enrollment_count': enrollment_count,
            'capacity_statistics': {'total_capacity': total_capacity, 'enrolled': enrollment_count, 'utilization_percentage': round(capacity_utilization, 2)},
            'academic_performance_average': round(float(avg_score), 2)
        }

        # Apply configurable template filters if provided
        if config.get('exclude_capacity'):
            report.pop('capacity_statistics', None)
        if config.get('exclude_transfers'):
            report.pop('transfers_count', None)

        return report
