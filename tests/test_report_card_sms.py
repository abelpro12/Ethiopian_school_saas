import json
import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, PeriodType, Grade, Section, Subject, Stream
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.communication.models import SMSTemplate, SMSTemplateType, ReportCardSMSLog
from apps.communication.services import (
    ensure_default_sms_templates,
    render_sms_template,
    ReportCardSMSService,
)


class ReportCardSMSTests(TestCase):
    """
    Test suite for Report Card SMS Dispatcher:
    - Bilingual message template rendering (Amharic & English)
    - Parent contact resolution & fallback to student emergency contact
    - ReportCardSMSService: roster preparation, single student dispatch, bulk section dispatch
    - Handling missing parent phone numbers (NO_PHONE status & logging)
    - Preview modal JSON API
    - Send API (bulk & filtered student dispatch)
    - Audit logging in ReportCardSMSLog and history view
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
            username="admin_report_sms",
            email="admin_report@addisfuture.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        # Teacher / Homeroom Teacher
        self.teacher = User.objects.create_user(
            username="teacher_aster",
            email="aster@addisfuture.edu.et",
            password="teacherpassword123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Aster",
            last_name="Kebede"
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
            school=self.school, grade=self.grade10, stream=self.stream, name="10A", class_teacher=self.teacher
        )

        # Subjects
        self.subject_math = Subject.objects.create(
            school=self.school,
            grade=self.grade10,
            stream=self.stream,
            name="Mathematics",
            code="MAT-10"
        )
        self.subject_eng = Subject.objects.create(
            school=self.school,
            grade=self.grade10,
            stream=self.stream,
            name="English",
            code="ENG-10"
        )

        # Assessment Components
        self.comp_math = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject_math,
            name="Final Exam",
            weight=Decimal('100.00'),
            max_marks=Decimal('100.00'),
            assessment_type="NUMERICAL"
        )
        self.comp_eng = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject_eng,
            name="Final Exam",
            weight=Decimal('100.00'),
            max_marks=Decimal('100.00'),
            assessment_type="NUMERICAL"
        )

        # Student 1: High achiever with Amharic parent
        self.student1_user = User.objects.create_user(
            username="stu_dawit_rc",
            email="dawit_rc@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Dawit",
            last_name="Haile"
        )
        self.student1 = StudentProfile.objects.create(
            school=self.school,
            user=self.student1_user,
            student_id="AFA-2001",
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

        self.parent1_user = User.objects.create_user(
            username="parent_haile_rc",
            email="haile_rc@gmail.com",
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

        # Student 2: English preference parent
        self.student2_user = User.objects.create_user(
            username="stu_selam_rc",
            email="selam_rc@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Selam",
            last_name="Tadesse"
        )
        self.student2 = StudentProfile.objects.create(
            school=self.school,
            user=self.student2_user,
            student_id="AFA-2002",
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
            username="parent_tadesse_rc",
            email="tadesse_rc@gmail.com",
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
            username="stu_yonas_rc",
            email="yonas_rc@afa.edu.et",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Yonas",
            last_name="Bekele"
        )
        self.student3 = StudentProfile.objects.create(
            school=self.school,
            user=self.student3_user,
            student_id="AFA-2003",
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

        # Record marks
        # Dawit: Math 95, Eng 85 -> Total 180, Avg 90
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment1,
            assessment_component=self.comp_math,
            mark_value=Decimal('95.00'),
            letter_grade="A",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment1,
            assessment_component=self.comp_eng,
            mark_value=Decimal('85.00'),
            letter_grade="B",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )

        # Selam: Math 80, Eng 70 -> Total 150, Avg 75
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment2,
            assessment_component=self.comp_math,
            mark_value=Decimal('80.00'),
            letter_grade="B",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment2,
            assessment_component=self.comp_eng,
            mark_value=Decimal('70.00'),
            letter_grade="C",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )

        # Yonas: Math 40, Eng 45 -> Total 85, Avg 42.5
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment3,
            assessment_component=self.comp_math,
            mark_value=Decimal('40.00'),
            letter_grade="D",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment3,
            assessment_component=self.comp_eng,
            mark_value=Decimal('45.00'),
            letter_grade="D",
            status=MarkStatus.APPROVED,
            entered_by=self.teacher
        )

    def test_default_template_generation_and_rendering(self):
        """
        Verify that report card SMS template is generated and renders properly with
        all subject marks, total, average, rank, and grade in Amharic and English.
        """
        ensure_default_sms_templates(self.school)
        tpl = SMSTemplate.objects.filter(
            school=self.school, template_type=SMSTemplateType.REPORT_CARD
        ).first()
        self.assertIsNotNone(tpl)

        context = {
            'student_name': 'Dawit Haile',
            'period_name': 'Semester 1',
            'subjects_summary': 'Mathematics: 95, English: 85',
            'average': '90.0',
            'total_score': '180.0',
            'rank': '1/3',
            'grade': 'A',
            'conduct': 'A',
            'status': 'Promoted',
            'school_name': 'Addis Future Academy'
        }

        en_msg = render_sms_template(self.school, SMSTemplateType.REPORT_CARD, context, lang='en')
        self.assertIn("Dawit Haile", en_msg)
        self.assertIn("Mathematics: 95, English: 85", en_msg)
        self.assertIn("Total: 180.0", en_msg)
        self.assertIn("Average: 90.0%", en_msg)
        self.assertIn("Rank: 1/3", en_msg)
        self.assertIn("Grade: A", en_msg)
        self.assertIn("Addis Future Academy", en_msg)

        context_am = {
            'student_name': 'ዳዊት ኃይሌ',
            'period_name': 'ሴሚስተር 1',
            'subjects_summary': 'Mathematics: 95, English: 85',
            'average': '90.0',
            'total_score': '180.0',
            'rank': '1/3',
            'grade': 'A',
            'conduct': 'A',
            'status': 'አልፏል',
            'school_name': 'Addis Future Academy'
        }
        am_msg = render_sms_template(self.school, SMSTemplateType.REPORT_CARD, context_am, lang='am')
        self.assertIn("ዳዊት ኃይሌ", am_msg)
        self.assertIn("ውጤቶች: Mathematics: 95, English: 85", am_msg)
        self.assertIn("ድምር: 180.0", am_msg)
        self.assertIn("አማካይ: 90.0%", am_msg)
        self.assertIn("ደረጃ: 1/3", am_msg)
        self.assertIn("ውጤት: A", am_msg)
        self.assertIn("አልፏል", am_msg)

    def test_get_section_report_cards_for_dispatch(self):
        """
        Verify that roster extraction computes accurate averages, totals, ranks, grades, and subject summaries.
        """
        recipients = ReportCardSMSService.get_section_report_cards_for_dispatch(
            school=self.school,
            section=self.section10a,
            period=self.period,
            is_annual=False
        )

        self.assertEqual(len(recipients), 3)

        # Sorted by student name, Dawit has rank 1, Selam rank 2, Yonas rank 3
        dawit = next(r for r in recipients if r['student_id'] == str(self.student1.id))
        self.assertEqual(dawit['average_score'], 90.0)
        self.assertEqual(dawit['total_score'], 180.0)
        self.assertEqual(dawit['rank'], 1)
        self.assertEqual(dawit['grade'], 'A+')
        self.assertIn("Mathematics: 95", dawit['subjects_summary'])
        self.assertIn("English: 85", dawit['subjects_summary'])
        self.assertEqual(dawit['parent_phone'], '0911445566')
        self.assertTrue(dawit['has_phone'])
        self.assertTrue(dawit['has_marks'])

        # Check rendered message for Dawit contains all subject mark, total, average, rank, grade
        self.assertIn("Mathematics: 95, English: 85", dawit['rendered_sms_en'])
        self.assertIn("Total: 180.0", dawit['rendered_sms_en'])
        self.assertIn("Average: 90.0%", dawit['rendered_sms_en'])
        self.assertIn("Rank: 1/3", dawit['rendered_sms_en'])
        self.assertIn("Grade: A+", dawit['rendered_sms_en'])

        selam = next(r for r in recipients if r['student_id'] == str(self.student2.id))
        self.assertEqual(selam['average_score'], 75.0)
        self.assertEqual(selam['total_score'], 150.0)
        self.assertEqual(selam['rank'], 2)
        self.assertIn("Mathematics: 80", selam['subjects_summary'])
        self.assertIn("English: 70", selam['subjects_summary'])
        self.assertEqual(selam['parent_phone'], '0922334455')
        self.assertTrue(selam['has_phone'])

        yonas = next(r for r in recipients if r['student_id'] == str(self.student3.id))
        self.assertEqual(yonas['average_score'], 42.5)
        self.assertEqual(yonas['rank'], 3)
        self.assertFalse(yonas['has_phone'])

    def test_dispatch_single_report_card_sms_success(self):
        """
        Verify single report card dispatch logs to ReportCardSMSLog and returns SENT.
        """
        result = ReportCardSMSService.dispatch_single_report_card_sms(
            school=self.school,
            student=self.student1,
            period=self.period,
            parent=self.parent1,
            parent_phone="0911445566",
            average=90.0,
            total_score=180.0,
            rank=1,
            total_students=3,
            conduct='A',
            promotion_status='Promoted',
            lang_override='am',
            sender_user=self.admin
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'SENT')
        self.assertIn('0911445566', result['phone'])

        # Verify audit log
        log = ReportCardSMSLog.objects.get(id=result['log_id'])
        self.assertEqual(log.school, self.school)
        self.assertEqual(log.student, self.student1)
        self.assertEqual(log.recipient_phone, "0911445566")
        self.assertEqual(log.average_score, Decimal('90.00'))
        self.assertEqual(log.section_rank, 1)
        self.assertEqual(log.status, 'SENT')

    def test_dispatch_single_report_card_sms_missing_phone(self):
        """
        Verify dispatching to student without phone fails safely with status NO_PHONE.
        """
        result = ReportCardSMSService.dispatch_single_report_card_sms(
            school=self.school,
            student=self.student3,
            period=self.period,
            parent=None,
            parent_phone="",
            average=42.5,
            total_score=85.0,
            rank=3,
            total_students=3,
            conduct='B',
            promotion_status='Retained',
            sender_user=self.admin
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'NO_PHONE')

        # Check log was created with NO_PHONE
        log = ReportCardSMSLog.objects.filter(student=self.student3, status='NO_PHONE').first()
        self.assertIsNotNone(log)
        self.assertIn("SKIPPED: No registered parent phone number", log.message)

    def test_bulk_dispatch_report_cards(self):
        """
        Verify bulk dispatch dispatches to students with phones and skips missing phones.
        """
        summary = ReportCardSMSService.bulk_dispatch_report_cards(
            school=self.school,
            section=self.section10a,
            period=self.period,
            is_annual=False,
            sender_user=self.admin
        )

        self.assertEqual(summary['total_students'], 3)
        self.assertEqual(summary['dispatched'], 2)  # Dawit and Selam
        self.assertEqual(summary['skipped_no_phone'], 1)  # Yonas
        self.assertEqual(summary['failed'], 0)

        # Verify ReportCardSMSLog entries
        self.assertEqual(ReportCardSMSLog.objects.filter(school=self.school, status='SENT').count(), 2)
        self.assertEqual(ReportCardSMSLog.objects.filter(school=self.school, status='NO_PHONE').count(), 1)

    def test_report_cards_sms_dashboard_view(self):
        """
        Test the dedicated Report Card SMS Dispatcher Dashboard view.
        """
        self.client.force_login(self.admin)
        url = reverse('assessments:report_cards_sms')
        response = self.client.get(url, {
            'section_id': self.section10a.id,
            'period_id': self.period.id
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Cards SMS Dispatcher")
        self.assertContains(response, "10A")
        self.assertContains(response, "Dawit Haile")
        self.assertContains(response, "Selam Tadesse")

    def test_report_cards_sms_preview_modal_api(self):
        """
        Test the modal preview JSON API called by the Report Cards main view.
        """
        self.client.force_login(self.admin)
        url = reverse('assessments:report_cards_sms_preview_modal', kwargs={'section_id': self.section10a.id})
        response = self.client.get(url, {'period_id': self.period.id})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['stats']['total_students'], 3)
        self.assertEqual(data['stats']['valid_phones'], 2)
        self.assertEqual(data['stats']['missing_phones'], 1)
        self.assertEqual(len(data['recipients']), 3)

    def test_report_cards_sms_send_api(self):
        """
        Test the POST send API for report cards SMS.
        """
        self.client.force_login(self.admin)
        url = reverse('assessments:report_cards_sms_send')
        payload = {
            'section_id': self.section10a.id,
            'period_id': self.period.id,
            'student_ids': [str(self.student1.id)],  # Only Dawit
            'lang': 'pref'
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['dispatched'], 1)
        self.assertEqual(data['total_students'], 1)

        # Verify log has total_students=3 and section_rank=1, and message has 1/3 (not 1/1)
        log = ReportCardSMSLog.objects.filter(student=self.student1).order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.section_rank, 1)
        self.assertEqual(log.total_students, 3)
        self.assertIn("1/3", log.message)

    def test_amharic_and_english_rank_consistency(self):
        """
        Verify that dispatching in Amharic and English produces the exact same rank
        (e.g. Rank: 1/3 and ደረጃ: 1/3), never collapsing to 1/1 when filtering students.
        """
        # Dispatch Dawit in English
        res_en = ReportCardSMSService.bulk_dispatch_report_cards(
            school=self.school,
            section=self.section10a,
            period=self.period,
            student_ids=[str(self.student1.id)],
            lang_override='en',
            sender_user=self.admin
        )
        self.assertEqual(res_en['dispatched'], 1)
        log_en = ReportCardSMSLog.objects.filter(student=self.student1).order_by('-id').first()
        self.assertEqual(log_en.section_rank, 1)
        self.assertEqual(log_en.total_students, 3)
        self.assertIn("Rank: 1/3", log_en.message)

        # Dispatch Dawit in Amharic
        res_am = ReportCardSMSService.bulk_dispatch_report_cards(
            school=self.school,
            section=self.section10a,
            period=self.period,
            student_ids=[str(self.student1.id)],
            lang_override='am',
            sender_user=self.admin
        )
        self.assertEqual(res_am['dispatched'], 1)
        log_am = ReportCardSMSLog.objects.filter(student=self.student1).order_by('-id').first()
        self.assertEqual(log_am.section_rank, 1)
        self.assertEqual(log_am.total_students, 3)
        self.assertIn("ደረጃ: 1/3", log_am.message)

    def test_report_cards_sms_history_view(self):
        """
        Test the Report Card SMS Audit History view.
        """
        # Create a sample log
        ReportCardSMSLog.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            student=self.student1,
            parent=self.parent1,
            recipient_phone="0911445566",
            average_score=Decimal('90.00'),
            total_score=Decimal('180.00'),
            section_rank=1,
            total_students=3,
            conduct_grade='A',
            promotion_status='Promoted',
            message="Test message",
            status='SENT',
            sent_by=self.admin
        )

        self.client.force_login(self.admin)
        url = reverse('assessments:report_cards_sms_history')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Cards SMS Dispatch History")
        self.assertContains(response, "Dawit Haile")
        self.assertContains(response, "0911445566")

    def test_starter_campaign_handling_and_error_propagation(self):
        """
        Verify that starter campaign unwhitelisted numbers are handled gracefully,
        errors are propagated, and user=None does not trigger an IntegrityError.
        """
        from apps.notifications.services import NotificationService, SMSEthiopiaProvider
        from unittest.mock import patch, MagicMock

        # 1. Test unwhitelisted with simulate_unwhitelisted = True
        # 1. Test unwhitelisted with simulate_unwhitelisted = True
        provider = SMSEthiopiaProvider(api_key="dummy_test_starter_key_mock")
        from apps.notifications.services import MockSMSProvider
        try:
            NotificationService.set_sms_provider(provider)

            mock_resp_400 = MagicMock()
            mock_resp_400.status_code = 400
            mock_resp_400.text = '{"error_message":"DEFAULT_CAMPAIGN_RECIPIENT_NOT_WHITELISTED: This is a starter (default) campaign and can only deliver to numbers verified in the dashboard. Error Code :: 10007"}'

            with patch('requests.post', return_value=mock_resp_400):
                # In test environment with simulate_unwhitelisted = True
                with self.settings(SMS_SIMULATE_UNWHITELISTED=True):
                    sent = provider.send_sms("0953905885", "Test report card message")
                    self.assertTrue(sent)
                    self.assertTrue(provider.last_details.get('simulated'))

                # With simulate_unwhitelisted = False, it should fail and record exact error
                with self.settings(SMS_SIMULATE_UNWHITELISTED=False, DEBUG=False):
                    sent_fail = provider.send_sms("0953905885", "Test report card message")
                    self.assertFalse(sent_fail)
                    self.assertIn("SMSEthiopia Starter Account limitation", provider.last_error)
        finally:
            # Reset provider immediately
            NotificationService.set_sms_provider(MockSMSProvider())

            mock_resp_400 = MagicMock()
            mock_resp_400.status_code = 400
            mock_resp_400.text = '{"error_message":"DEFAULT_CAMPAIGN_RECIPIENT_NOT_WHITELISTED: This is a starter (default) campaign and can only deliver to numbers verified in the dashboard. Error Code :: 10007"}'

            with patch('requests.post', return_value=mock_resp_400):
                # In test environment with simulate_unwhitelisted = True
                with self.settings(SMS_SIMULATE_UNWHITELISTED=True):
                    sent = provider.send_sms("0953905885", "Test report card message")
                    self.assertTrue(sent)
                    self.assertTrue(provider.last_details.get('simulated'))

                # With simulate_unwhitelisted = False, it should fail and record exact error
                with self.settings(SMS_SIMULATE_UNWHITELISTED=False, DEBUG=False):
                    sent_fail = provider.send_sms("0953905885", "Test report card message")
                    self.assertFalse(sent_fail)
                    self.assertIn("SMSEthiopia Starter Account limitation", provider.last_error)
        finally:
            # Reset provider immediately
            NotificationService.set_sms_provider(MockSMSProvider())

        # 2. Test user=None safety in NotificationService
        sent_none_user = NotificationService.send_notification(
            school=self.school,
            recipient_user=None,
            channel="SMS",
            message="Test message without user",
            phone_number="0911445566"
        )
        self.assertTrue(sent_none_user)

    def test_omni_channel_dispatch_report_cards_and_exam_results(self):
        """
        Verify multi-channel dispatch across SMS, free Telegram Bot, and free Email.
        """
        from apps.communication.services import ReportCardSMSService, ExamResultSMSService
        from apps.communication.models import TelegramAccountLink

        TelegramAccountLink.objects.get_or_create(
            school=self.school,
            user=self.parent1_user,
            defaults={'telegram_chat_id': '123456789', 'is_verified': True}
        )

        # 1. Test Report Card dispatch with all 3 channels
        summary_all = ReportCardSMSService.bulk_dispatch_report_cards(
            school=self.school,
            section=self.section10a,
            period=self.period,
            sender_user=self.teacher,
            channels=['SMS', 'TELEGRAM', 'EMAIL']
        )
        self.assertGreater(summary_all['dispatched'], 0)
        self.assertGreater(summary_all['sms_dispatched'], 0)
        self.assertGreater(summary_all['telegram_dispatched'], 0)
        self.assertGreater(summary_all['email_dispatched'], 0)

        # 2. Test Report Card dispatch with FREE ONLY channels (Telegram + Email, no SMS cost)
        summary_free = ReportCardSMSService.bulk_dispatch_report_cards(
            school=self.school,
            section=self.section10a,
            period=self.period,
            sender_user=self.teacher,
            channels=['TELEGRAM', 'EMAIL']
        )
        self.assertGreater(summary_free['dispatched'], 0)
        self.assertEqual(summary_free['sms_dispatched'], 0)
        self.assertGreater(summary_free['telegram_dispatched'], 0)
        self.assertGreater(summary_free['email_dispatched'], 0)

        # 3. Test Exam Result dispatch with all 3 channels
        exam_summary = ExamResultSMSService.bulk_dispatch_results(
            school=self.school,
            component=self.comp_math,
            section=self.section10a,
            sender_user=self.teacher,
            channels=['SMS', 'TELEGRAM', 'EMAIL']
        )
        self.assertGreater(exam_summary['dispatched'], 0)
        self.assertGreater(exam_summary['sms_dispatched'], 0)
        self.assertGreater(exam_summary['telegram_dispatched'], 0)
        self.assertGreater(exam_summary['email_dispatched'], 0)
