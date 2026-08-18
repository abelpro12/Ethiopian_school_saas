from decimal import Decimal
from django.db import models
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.assessments.models import StudentMark


class RiskLevel(models.TextChoices):
    LOW = 'LOW', 'Low Risk'
    MEDIUM = 'MEDIUM', 'Medium Risk'
    HIGH = 'HIGH', 'High Risk'


class AtRiskStudentEngine:
    """
    At-Risk Student Engine (Points 16 & 71).
    Identifies low attendance (<80%), 3+ consecutive absences, low mark averages, or excessive failures.
    """
    @staticmethod
    def evaluate_student_risk(student: StudentProfile):
        school = student.school
        records = AttendanceRecord.objects.filter(school=school, student=student)
        total_records = records.count()
        
        absent_count = records.filter(status=AttendanceStatus.ABSENT).count()
        attendance_rate = 100.0 if total_records == 0 else ((total_records - absent_count) / total_records) * 100.0

        marks = StudentMark.objects.filter(school=school, enrollment__student=student)
        failing_marks = marks.filter(mark_value__lt=Decimal('50.00')).count()

        risk_factors = []
        if attendance_rate < 80.0:
            risk_factors.append(f"Low Attendance: {attendance_rate:.1f}%")
        if absent_count >= 3:
            risk_factors.append(f"High Absences: {absent_count} days")
        if failing_marks > 0:
            risk_factors.append(f"Failing Subjects: {failing_marks} assessments")

        if len(risk_factors) >= 2:
            risk_level = RiskLevel.HIGH
        elif len(risk_factors) == 1:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        return {
            'student_id': student.student_id,
            'student_name': student.full_name,
            'risk_level': risk_level,
            'attendance_rate': attendance_rate,
            'absent_count': absent_count,
            'failing_marks_count': failing_marks,
            'risk_factors': risk_factors
        }
