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
from apps.communication.models import SMSTemplate, SMSTemplateType, ExamResultSMSLog
from apps.communication.services import (
    ensure_default_sms_templates,
    render_sms_template,
    ExamResultSMSService,
)


class ExamResultsSMSTests(TestCase):
    """
    Test suite for Exam & Test Results SMS Dispatcher:
    - Bilingual message template rendering
    - Parent contact resolution & fallback
    - Bulk and single test result dispatch (e.g. Test 1)
    - Prevention of sending without mark or with missing phone
    - API endpoints (preview modal API & send API)
    - Dashboard access and authorization
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Addis Future Academy",
            code="AFA",
            calendar_preference="ETHIOPIAN"
        )

        # Admin
        self.admin = User.objects.create_superuser(
            username="admin_sms",
            email="admin@addisfuture.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        # Teacher
        self.teacher = User.objects.create_user(
            username="teacher_tariku",
            email="tariku@addisfuture.edu.et",
            password="teacherpassword123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Tariku",
            last_name="Lemma"
        )

        # Academic Calendar
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            is_active=True
        )
        from apps.academics.models import PeriodType
        self.period = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            name="Semester 1",
            period_type=PeriodType.SEMESTER,
            start_date=datetime.date(2024, 9, 16),
            end_date=datetime.date(2025, 1, 20),
            is_current=True
        )

        # Grade, Stream, Section
        self.grade10 = Grade.objects.create(school=self.school, name="Grade 10", level=10)
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section10a = Section.objects.create(
            school=self.school, grade=self.grade10, stream=self.stream, name="10A"
        )

        # Subject: Physics
        self.subject = Subject.objects.create(
            school=self.school,
            grade=self.grade10,
            stream=self.stream,
            name="Physics",
            code="PHY-10"
        )

        # Assessment Component: Test 1 (Max 20 marks, Weight 20%)
        self.test1 = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject,
            name="Test 1",
            weight=Decimal('20.00'),
            max_marks=Decimal('20.00'),
            assessment_type="NUMERICAL"
        )

        # Student 1: With parent & registered phone
        self.student1_user = User.objects.create_user(
            username="stu_dawit",
            email="dawit@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Dawit",
            last_name="Haile"
        )
        self.student1 = StudentProfile.objects.create(
            school=self.school,
            user=self.student1_user,
            student_id="AFA-1001",
            first_name="Dawit",
            last_name="Haile",
            amharic_name="ዳዊት ኃይሌ",
            date_of_birth=datetime.date(2008, 3, 15),
            gender="M"
        )
        self.enrollment1 = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student1,
            academic_year=self.academic_year,
            grade=self.grade10,
            stream=self.stream,
            section=self.section10a,
            enrollment_date=datetime.date(2024, 9, 12),
            status=EnrollmentStatus.ACTIVE
        )

        # Parent of Student 1
        self.parent1_user = User.objects.create_user(
            username="parent_haile",
            email="haile@gmail.com",
            password="password123",
            role=UserRole.PARENT,
            school=self.school,
            first_name="Haile",
            last_name="Gebre",
            phone="0911445566"
        )
        self.parent1 = ParentProfile.objects.create(
            school=self.school,
            user=self.parent1_user,
            phone="0911445566",
            relationship="Father",
            preferred_language="am"
        )
        GuardianRelationship.objects.create(
            school=self.school,
            parent=self.parent1,
            student=self.student1,
            is_primary=True
        )

        # Student 2: With parent who has English preference
        self.student2_user = User.objects.create_user(
            username="stu_selam",
            email="selam@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Selam",
            last_name="Tadesse"
        )
        self.student2 = StudentProfile.objects.create(
            school=self.school,
            user=self.student2_user,
            student_id="AFA-1002",
            first_name="Selam",
            last_name="Tadesse",
            amharic_name="ሰላም ታደሰ",
            date_of_birth=datetime.date(2008, 7, 20),
            gender="F"
        )
        self.enrollment2 = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student2,
            academic_year=self.academic_year,
            grade=self.grade10,
            stream=self.stream,
            section=self.section10a,
            enrollment_date=datetime.date(2024, 9, 12),
            status=EnrollmentStatus.ACTIVE
        )
        self.parent2_user = User.objects.create_user(
            username="parent_tadesse",
            email="tadesse@gmail.com",
            password="password123",
            role=UserRole.PARENT,
            school=self.school,
            first_name="Tadesse",
            last_name="Alemu",
            phone="0922334455"
        )
        self.parent2 = ParentProfile.objects.create(
            school=self.school,
            user=self.parent2_user,
            phone="0922334455",
            relationship="Father",
            preferred_language="en"
        )
        GuardianRelationship.objects.create(
            school=self.school,
            parent=self.parent2,
            student=self.student2,
            is_primary=True
        )

        # Student 3: Has NO parent phone
        self.student3_user = User.objects.create_user(
            username="stu_yonas",
            email="yonas@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Yonas",
            last_name="Bekele"
        )
        self.student3 = StudentProfile.objects.create(
            school=self.school,
            user=self.student3_user,
            student_id="AFA-1003",
            first_name="Yonas",
            last_name="Bekele",
            date_of_birth=datetime.date(2008, 1, 10),
            gender="M"
        )
        self.enrollment3 = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student3,
            academic_year=self.academic_year,
            grade=self.grade10,
            stream=self.stream,
            section=self.section10a,
            enrollment_date=datetime.date(2024, 9, 12),
            status=EnrollmentStatus.ACTIVE
        )

        # Record marks for Test 1
        # Dawit: 18 / 20 (90%, A+)
        self.mark1 = StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment1,
            assessment_component=self.test1,
            mark_value=Decimal('18.00'),
            letter_grade="A+",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )
        # Selam: 15 / 20 (75%, B)
        self.mark2 = StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment2,
            assessment_component=self.test1,
            mark_value=Decimal('15.00'),
            letter_grade="B",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )
        # Yonas: 12 / 20 (60%, C) - but no phone!
        self.mark3 = StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment3,
            assessment_component=self.test1,
            mark_value=Decimal('12.00'),
            letter_grade="C",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )

    def test_01_ensure_and_render_exam_result_sms_template(self):
        """Verify default EXAM_RESULT template exists and renders placeholders in English & Amharic."""
        ensure_default_sms_templates(self.school)

        context = {
            'student_name': "Dawit Haile",
            'subject_name': "Physics",
            'test_name': "Test 1",
            'score': "18",
            'max_score': "20",
            'percentage': "90.0",
            'grade_letter': "A+",
            'school_name': "Addis Future Academy",
        }

        # Render in Amharic
        am_msg = render_sms_template(self.school, SMSTemplateType.EXAM_RESULT, context, lang='am')
        self.assertIn("Dawit Haile", am_msg)
        self.assertIn("Physics", am_msg)
        self.assertIn("Test 1", am_msg)
        self.assertIn("18/20", am_msg)
        self.assertIn("90.0%", am_msg)
        self.assertIn("A+", am_msg)
        self.assertIn("ክቡር ወላጅ", am_msg)

        # Render in English
        en_msg = render_sms_template(self.school, SMSTemplateType.EXAM_RESULT, context, lang='en')
        self.assertIn("Dear Parent", en_msg)
        self.assertIn("Dawit Haile", en_msg)
        self.assertIn("18/20", en_msg)
        self.assertIn("90.0%", en_msg)

    def test_02_get_component_results_for_dispatch(self):
        """Verify recipient preparation collects marks, percentages, parent contacts, and status."""
        recipients = ExamResultSMSService.get_component_results_for_dispatch(
            school=self.school,
            component=self.test1,
            section=self.section10a
        )

        self.assertEqual(len(recipients), 3)

        # Dawit checks
        r1 = next(r for r in recipients if r['student_id'] == str(self.student1.id))
        self.assertTrue(r1['has_mark'])
        self.assertEqual(r1['score'], 18.0)
        self.assertEqual(r1['max_score'], 20.0)
        self.assertEqual(r1['percentage'], 90.0)
        self.assertEqual(r1['letter_grade'], "A+")
        self.assertTrue(r1['has_phone'])
        self.assertEqual(r1['parent_phone'], "0911445566")
        self.assertEqual(r1['preferred_lang'], "am")
        self.assertFalse(r1['already_sent'])

        # Yonas (no phone) checks
        r3 = next(r for r in recipients if r['student_id'] == str(self.student3.id))
        self.assertTrue(r3['has_mark'])
        self.assertFalse(r3['has_phone'])

    def test_03_dispatch_single_result_sms_success_and_logging(self):
        """Verify dispatching a single test result SMS creates an ExamResultSMSLog and sends notification."""
        res = ExamResultSMSService.dispatch_single_result_sms(
            school=self.school,
            component=self.test1,
            student=self.student1,
            score_val=18.0,
            max_score=20.0,
            percentage=90.0,
            letter_grade="A+",
            parent=self.parent1,
            sender_user=self.admin
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['status'], 'SENT')
        self.assertEqual(res['phone'], "0911445566")

        # Verify database log
        log = ExamResultSMSLog.objects.filter(
            school=self.school,
            student=self.student1,
            assessment_component=self.test1
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SENT')
        self.assertEqual(log.score, Decimal('18.00'))
        self.assertEqual(log.max_score, Decimal('20.00'))
        self.assertIn("Dawit Haile", log.message)

    def test_04_dispatch_missing_phone_handled_safely(self):
        """Verify student with missing parent phone records status='NO_PHONE' without crashing."""
        res = ExamResultSMSService.dispatch_single_result_sms(
            school=self.school,
            component=self.test1,
            student=self.student3,
            score_val=12.0,
            max_score=20.0,
            percentage=60.0,
            letter_grade="C",
            parent=None,
            sender_user=self.admin
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['status'], 'NO_PHONE')

        log = ExamResultSMSLog.objects.filter(
            school=self.school,
            student=self.student3,
            assessment_component=self.test1
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'NO_PHONE')

    def test_05_bulk_dispatch_results(self):
        """Verify bulk dispatching test results to a class section."""
        summary = ExamResultSMSService.bulk_dispatch_results(
            school=self.school,
            component=self.test1,
            section=self.section10a,
            sender_user=self.admin
        )

        self.assertEqual(summary['total_students'], 3)
        self.assertEqual(summary['dispatched'], 2)  # Dawit and Selam have phones
        self.assertEqual(summary['skipped_no_phone'], 1)  # Yonas has no phone
        self.assertEqual(summary['failed'], 0)

        # Check total logs created
        logs_count = ExamResultSMSLog.objects.filter(
            school=self.school,
            assessment_component=self.test1
        ).count()
        self.assertEqual(logs_count, 3)

    def test_06_dashboard_view_and_filtering(self):
        """Verify exam_results_sms_dashboard renders with 200 OK and filters by component."""
        self.client.force_login(self.admin)
        url = reverse('assessments:exam_results_sms')

        # 1. Base dashboard
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exam & Test Results SMS Dispatcher")

        # 2. Filtered by Test 1 and Section 10A
        response_filtered = self.client.get(url, {
            'grade_id': self.grade10.id,
            'section_id': self.section10a.id,
            'subject_id': self.subject.id,
            'component_id': self.test1.id,
        })
        self.assertEqual(response_filtered.status_code, 200)
        self.assertContains(response_filtered, "Dawit Haile")
        self.assertContains(response_filtered, "Selam Tadesse")
        self.assertContains(response_filtered, "Test 1")

    def test_07_preview_modal_api(self):
        """Verify JSON preview API for the Gradebook (Mark Entry Grid) quick modal."""
        self.client.force_login(self.admin)
        url = reverse('assessments:exam_results_sms_preview_modal', args=[self.test1.id, self.section10a.id])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['component']['name'], "Test 1")
        self.assertEqual(data['stats']['total'], 3)
        self.assertEqual(data['stats']['with_marks'], 3)
        self.assertEqual(data['stats']['with_phone'], 2)
        self.assertEqual(len(data['recipients']), 3)

    def test_08_send_api_endpoint(self):
        """Verify POST API to dispatch results for selected students."""
        self.client.force_login(self.admin)
        url = reverse('assessments:exam_results_sms_send')

        payload = {
            'component_id': self.test1.id,
            'section_id': self.section10a.id,
            'student_ids': [str(self.student1.id)],
            'lang': 'am'
        }

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data['success'])
        self.assertEqual(data['summary']['dispatched'], 1)
        self.assertIn("Dispatched 1 SMS alert", data['message'])

        # Verify database record
        sent_log = ExamResultSMSLog.objects.filter(
            school=self.school,
            student=self.student1,
            assessment_component=self.test1,
            status='SENT'
        ).exists()
        self.assertTrue(sent_log)
