import uuid
import datetime
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject, SchoolEvent, EventType, TargetAudience
from apps.students.models import StudentProfile
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.teachers.services import HomeroomService
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import StudentConduct, ConductGrade


class EventAndHomeroomManagementTest(TestCase):
    def test_school_events_and_homeroom_scoping(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"Event Academy {uid}", subdomain=f"evt-{uid}", code=f"EAC-{uid.upper()}")
        ay = AcademicYear.objects.create(
            school=school, name="2016 E.C.", gregorian_start_date=datetime.date(2023,9,12), gregorian_end_date=datetime.date(2024,6,30)
        )
        semester1 = AcademicPeriod.objects.create(school=school, academic_year=ay, name="Semester 1", start_date=datetime.date(2023,9,12), end_date=datetime.date(2024,1,20))

        # 1. Create School Events across categories
        evt1 = SchoolEvent.objects.create(
            school=school, academic_year=ay, title="Semester 1 Parent Meeting", event_type=EventType.PARENT_MEETING,
            target_audience=TargetAudience.PARENTS, start_date=datetime.date(2023, 10, 15)
        )
        evt2 = SchoolEvent.objects.create(
            school=school, academic_year=ay, title="National Holiday", event_type=EventType.HOLIDAY,
            target_audience=TargetAudience.ALL, start_date=datetime.date(2024, 1, 7)
        )
        self.assertEqual(evt1.event_type, EventType.PARENT_MEETING)
        self.assertEqual(evt2.target_audience, TargetAudience.ALL)

        teacher_user = User.objects.create_user(username=f"teacher_{uid}", school=school, role=UserRole.TEACHER)
        teacher_profile = TeacherProfile.objects.create(school=school, user=teacher_user, employee_id=f"T-{uid}")

        grade11 = Grade.objects.create(school=school, level=11, name="Grade 11")
        nat_stream = Stream.objects.create(school=school, name="Natural Science", code="NAT")
        section = Section.objects.create(school=school, grade=grade11, stream=nat_stream, name="11-NAT-A", capacity=40, class_teacher=teacher_user)

        physics = Subject.objects.create(school=school, code="PHY-11", name="Physics", grade=grade11, stream=nat_stream)
        chemistry = Subject.objects.create(school=school, code="CHEM-11", name="Chemistry", grade=grade11, stream=nat_stream)

        # Teacher is assigned to Physics, NOT Chemistry
        TeacherAssignment.objects.create(school=school, academic_year=ay, teacher=teacher_profile, subject=physics, section=section)

        stu_user = User.objects.create_user(username=f"student_{uid}", school=school, role=UserRole.STUDENT)
        student = StudentProfile.objects.create(school=school, user=stu_user, student_id=f"S-{uid}", first_name="Abebe", last_name="Kebede", gender="M")
        enrollment = StudentEnrollment.objects.create(school=school, academic_year=ay, student=student, grade=grade11, stream=nat_stream, section=section, status=EnrollmentStatus.ACTIVE)

        # Record Student Conduct
        StudentConduct.objects.create(
            school=school, enrollment=enrollment, academic_year=ay, period=semester1,
            grade=ConductGrade.A, remarks="Helpful and punctual student", recorded_by=teacher_user
        )

        # 3. Retrieve Homeroom Dashboard Data
        dash = HomeroomService.get_homeroom_dashboard(teacher_profile)
        self.assertTrue(dash['has_homeroom'])
        self.assertEqual(dash['total_students'], 1)
        self.assertEqual(dash['students'][0]['conduct'], 'Excellent (A)')

        # 4. Verify Scoping Restriction (Teacher can edit Physics, CANNOT edit Chemistry)
        self.assertTrue(HomeroomService.can_teacher_edit_subject_marks(teacher_profile, section, physics))
        self.assertFalse(HomeroomService.can_teacher_edit_subject_marks(teacher_profile, section, chemistry))

        print("\nSCHOOL EVENT & HOMEROOM MANAGEMENT SCOPING TEST PASSED CLEANLY!")
