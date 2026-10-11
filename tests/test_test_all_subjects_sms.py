import json
import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Section, Subject, Stream
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.communication.models import ExamResultSMSLog
from apps.communication.services import TestAllSubjectsSMSService


class TestAllSubjectsSMSTestCase(TestCase):
    """
    Test suite for Single-Test Across All Subjects Dispatcher:
    - Verifies aggregation of Test 1 / Continuous Assessment across all subjects in one message.
    - Verifies subject score formatting, totals, percentage, and letter grade calculation.
    - Verifies 3-Way Omni-Channel dispatch (SMS, Telegram, Email).
    - Verifies preview API and send API endpoints.
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Addis Future Academy",
            code="AFA",
            calendar_preference="ETHIOPIAN"
        )

        self.admin = User.objects.create_superuser(
            username="admin_test_all",
            email="admin@addisfuture.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 6, 30),
            is_active=True
        )

        self.period = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            name="Semester 1",
            start_date=datetime.date(2024, 9, 11),
            end_date=datetime.date(2025, 1, 30),
            is_current=True
        )

        self.grade = Grade.objects.create(school=self.school, level=9, name="Grade 9", stream_type='GEN')
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="9A", capacity=40)

        # Create two subjects: Mathematics and English
        self.subject_math = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="Mathematics", code="MATH9")
        self.subject_eng = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="English Language", code="ENG9")

        # Create components: "Test 1" for both subjects
        self.comp_math_test1 = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject_math,
            name="Test 1",
            weight=Decimal('20.0'),
            max_marks=Decimal('20.0')
        )
        self.comp_eng_test1 = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject_eng,
            name="Test 1",
            weight=Decimal('20.0'),
            max_marks=Decimal('20.0')
        )

        # Student Dawit
        self.student_user = User.objects.create_user(
            username="stu_dawit_test",
            email="dawit@test.com",
            password="stupassword123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Dawit",
            last_name="Haile"
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            student_id="AFA-9A-001",
            first_name="Dawit",
            last_name="Haile",
            gender="M",
            phone="0911000001"
        )
        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            academic_year=self.academic_year,
            status=EnrollmentStatus.ACTIVE
        )

        # Parent Haile
        self.parent_user = User.objects.create_user(
            username="parent_haile_test",
            email="haile@test.com",
            phone="0911445566",
            password="parentpass123",
            role=UserRole.PARENT,
            school=self.school
        )
        self.parent = ParentProfile.objects.create(
            school=self.school,
            user=self.parent_user,
            phone="0911445566",
            preferred_language="am"
        )
        GuardianRelationship.objects.create(
            school=self.school,
            parent=self.parent,
            student=self.student,
            is_primary=True
        )

        # Marks for Dawit: Math Test 1 = 18/20, English Test 1 = 17/20
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=self.comp_math_test1,
            mark_value=Decimal('18.0'),
            status=MarkStatus.PUBLISHED
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=self.comp_eng_test1,
            mark_value=Decimal('17.0'),
            status=MarkStatus.PUBLISHED
        )

    def test_get_available_tests_for_section(self):
        tests = TestAllSubjectsSMSService.get_available_tests_for_section(self.school, self.section)
        self.assertIn("Test 1", tests)

    def test_get_test_all_subjects_results_aggregation(self):
        recipients = TestAllSubjectsSMSService.get_test_all_subjects_results_for_dispatch(
            school=self.school,
            section=self.section,
            test_name="Test 1"
        )
        self.assertEqual(len(recipients), 1)
        r = recipients[0]
        self.assertEqual(r['student_name'], "Dawit Haile")
        self.assertEqual(r['has_marks'], True)
        self.assertEqual(r['total_score'], 35.0)  # 18 + 17
        self.assertEqual(r['total_max'], 40.0)    # 20 + 20
        self.assertEqual(r['percentage'], 87.5)   # 35/40 * 100
        self.assertIn("Math: 18/20", r['subjects_summary'])
        self.assertIn("English: 17/20", r['subjects_summary'])
        self.assertIn("35/40", r['preview_en'])
        self.assertIn("87.5%", r['preview_en'])

    def test_bulk_dispatch_test_all_subjects(self):
        summary = TestAllSubjectsSMSService.bulk_dispatch_test_all_subjects(
            school=self.school,
            section=self.section,
            test_name="Test 1",
            channels=['SMS', 'TELEGRAM', 'EMAIL']
        )
        self.assertEqual(summary['total_students'], 1)
        self.assertEqual(summary['dispatched'], 1)
        self.assertEqual(summary['failed'], 0)

        # Verify log entry in ExamResultSMSLog
        log = ExamResultSMSLog.objects.filter(school=self.school, student=self.student).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.score, Decimal('35.00'))
        self.assertEqual(log.max_score, Decimal('40.00'))
        self.assertIn("[Test 1 - All Subjects]", log.message)

    def test_preview_api_endpoint(self):
        self.client.force_login(self.admin)
        url = reverse('assessments:test_all_subjects_sms_preview_modal', args=[self.section.id])
        resp = self.client.get(f"{url}?test_name=Test%201")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['test_name'], "Test 1")
        self.assertEqual(len(data['recipients']), 1)
        self.assertEqual(data['recipients'][0]['total_score'], 35.0)

    def test_send_api_endpoint(self):
        self.client.force_login(self.admin)
        url = reverse('assessments:test_all_subjects_sms_send')
        payload = {
            'section_id': self.section.id,
            'test_name': 'Test 1',
            'student_ids': [str(self.student.id)],
            'channels': ['SMS', 'TELEGRAM', 'EMAIL']
        }
        resp = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['dispatched'], 1)

    def test_privacy_no_cross_parent_delivery(self):
        """
        Verify that when multiple students are dispatched:
        1. A parent only receives notifications for their own student.
        2. Parents without Telegram bot links do NOT trigger simulated cross-parent push to another parent's chat.
        3. No student marks are ever leaked to another parent's phone or Telegram.
        """
        from apps.communication.models import TelegramAccountLink

        # Parent 1 (Haile) links Telegram with Chat ID 8520255687
        TelegramAccountLink.objects.create(
            school=self.school,
            user=self.parent_user,
            telegram_chat_id="8520255687",
            is_verified=True
        )

        # Create Student 2 (Marta) with Parent 2 (Getachew - NO TELEGRAM LINK)
        student2_user = User.objects.create_user(
            username="stu_marta_test",
            email="marta@test.com",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Marta",
            last_name="Getachew"
        )
        student2 = StudentProfile.objects.create(
            school=self.school,
            user=student2_user,
            student_id="AFA-9A-002",
            first_name="Marta",
            last_name="Getachew",
            gender="F",
            phone="0911000002"
        )
        enrollment2 = StudentEnrollment.objects.create(
            school=self.school,
            student=student2,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            academic_year=self.academic_year,
            status=EnrollmentStatus.ACTIVE
        )
        parent2_user = User.objects.create_user(
            username="parent_getachew_test",
            email="getachew@test.com",
            phone="0911200028",
            role=UserRole.PARENT,
            school=self.school
        )
        parent2 = ParentProfile.objects.create(
            school=self.school,
            user=parent2_user,
            phone="0911200028",
            relationship="Father"
        )
        GuardianRelationship.objects.create(
            school=self.school,
            parent=parent2,
            student=student2,
            is_primary=True
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=enrollment2,
            assessment_component=self.comp_math_test1,
            mark_value=Decimal('15.0'),
            status=MarkStatus.PUBLISHED
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=enrollment2,
            assessment_component=self.comp_eng_test1,
            mark_value=Decimal('16.0'),
            status=MarkStatus.PUBLISHED
        )

        summary = TestAllSubjectsSMSService.bulk_dispatch_test_all_subjects(
            school=self.school,
            section=self.section,
            test_name="Test 1",
            channels=['SMS', 'TELEGRAM', 'EMAIL']
        )

        self.assertEqual(summary['total_students'], 2)
        # Only Dawit's parent has Telegram, so exactly 1 telegram message is dispatched
        self.assertEqual(summary['telegram_dispatched'], 1)

        # Check logs for both students
        log_dawit = ExamResultSMSLog.objects.filter(school=self.school, student=self.student).order_by('-sent_at').first()
        log_marta = ExamResultSMSLog.objects.filter(school=self.school, student=student2).order_by('-sent_at').first()

        self.assertIn("Telegram Bot", log_dawit.message)
        self.assertNotIn("Telegram Bot", log_marta.message)
        # Marta's log recipient must be Marta's parent's phone, not Dawit's parent's phone
        self.assertEqual(log_marta.recipient_phone, "0911200028")
        self.assertEqual(log_dawit.recipient_phone, "0911445566")

