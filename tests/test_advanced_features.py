from django.test import TestCase
from django.core.exceptions import ValidationError
import datetime
from decimal import Decimal
from apps.tenants.models import School
from apps.accounts.models import User
from apps.teachers.models import TeacherProfile
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject, PeriodSlot, TimetableSlot
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.attendance.services import check_attendance_alerts


class AdvancedFeaturesTest(TestCase):
    def test_timetable_teacher_conflict(self):
        school = School.objects.create(name="Test School")
        user = User.objects.create_user(username="teacher1", password="pw", school=school)
        teacher = TeacherProfile.objects.create(school=school, user=user, employee_id="T01")
    
        ay = AcademicYear.objects.create(school=school, name="2016", gregorian_start_date=datetime.date(2023,9,1), gregorian_end_date=datetime.date(2024,6,30))
        grade = Grade.objects.create(school=school, level=9, name="Grade 9")
        stream = Stream.objects.create(school=school, name="General", code="GEN")
        section1 = Section.objects.create(school=school, grade=grade, stream=stream, name="A")
        section2 = Section.objects.create(school=school, grade=grade, stream=stream, name="B")
    
        subject1 = Subject.objects.create(school=school, code="MATH", name="Math", grade=grade, stream=stream)
        subject2 = Subject.objects.create(school=school, code="ENG", name="English", grade=grade, stream=stream)
    
        period = PeriodSlot.objects.create(school=school, name="P1", start_time=datetime.time(8, 0), end_time=datetime.time(8, 45))
    
        # Create first slot
        TimetableSlot.objects.create(
            school=school,
            section=section1,
            subject=subject1,
            teacher=teacher,
            day_of_week='MONDAY',
            period_slot=period,
            room="Room 101"
        )
    
        # Try to create conflicting slot for same teacher
        with self.assertRaises(ValidationError) as exc_info:
            TimetableSlot.objects.create(
                school=school,
                section=section2,
                subject=subject2,
                teacher=teacher,
                day_of_week='MONDAY',
                period_slot=period,
                room="Room 102"
            )
        assert "is already scheduled during MONDAY - P1" in str(exc_info.exception)


    def test_attendance_alerts(self):
        school = School.objects.create(name="Test School")
        user = User.objects.create_user(username="student1", password="pw", school=school)
        student = StudentProfile.objects.create(school=school, user=user, student_id="S01")
        ay = AcademicYear.objects.create(school=school, name="2016", gregorian_start_date=datetime.date(2023,9,1), gregorian_end_date=datetime.date(2024,6,30))
        grade = Grade.objects.create(school=school, level=9, name="Grade 9")
        stream = Stream.objects.create(school=school, name="General", code="GEN")
        section = Section.objects.create(school=school, grade=grade, stream=stream, name="A")

        # 3 consecutive absences
        AttendanceRecord.objects.create(school=school, section=section, student=student, date=datetime.date(2023,10,1), status=AttendanceStatus.ABSENT)
        AttendanceRecord.objects.create(school=school, section=section, student=student, date=datetime.date(2023,10,2), status=AttendanceStatus.ABSENT)
        AttendanceRecord.objects.create(school=school, section=section, student=student, date=datetime.date(2023,10,3), status=AttendanceStatus.ABSENT)

        flagged = check_attendance_alerts(school)
        self.assertIn(student, flagged)
