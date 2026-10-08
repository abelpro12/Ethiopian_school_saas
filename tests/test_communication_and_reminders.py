import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Section
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.finance.models import (
    FeeCategory, StudentInvoice, InvoiceStatus
)
from apps.communication.models import (
    SMSTemplate,
    SMSTemplateType,
    ParentMeetingRequest,
    ParentMeetingCategory,
    ParentMeetingStatus,
    PaymentReminderLog,
    PaymentReminderStage,
    NotificationLog,
    NotificationChannel,
)
from apps.communication.services import (
    ensure_default_sms_templates,
    render_sms_template,
    send_student_absence_alert,
    dispatch_parent_meeting_sms,
    PaymentReminderService,
)


class CommunicationAndPresenceTests(TestCase):
    """
    Test suite for:
    - Item 7: Configurable SMS Templates, Automated Student Absence SMS trigger,
              Parent Meeting Request Module with SMS dispatch.
    - Item 8: Payment Due-Date Warning Engine (7-day, 3-day, due-date, and overdue SMS alerts)
              with deduplication guards.
    - Item 10: User Active Presence Tracking (UserPresenceMiddleware, presence_status, badges).
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Alpha Ethiopian Academy",
            code="ALPHA",
            calendar_preference="ETHIOPIAN"
        )

        # Admin & Teacher
        self.admin = User.objects.create_superuser(
            username="admin_comm",
            email="admin@alpha.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        self.teacher = User.objects.create_user(
            username="teacher_almaz",
            email="almaz@alpha.edu.et",
            password="teacherpassword123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Almaz",
            last_name="Kebede",
            phone="0911223344"
        )

        # Academic Year, Grade, Section
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            ethiopian_year=2017,
            is_active=True
        )

        self.grade = Grade.objects.create(school=self.school, name="Grade 9", level=9)
        from apps.academics.models import Stream
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="A")

        # Parent User & Profile
        self.parent_user = User.objects.create_user(
            username="parent_solomon",
            email="solomon@gmail.com",
            password="parentpassword123",
            role=UserRole.PARENT,
            school=self.school,
            first_name="Solomon",
            last_name="Bekele",
            phone="0911556677"
        )
        self.parent_profile = ParentProfile.objects.create(
            school=self.school,
            user=self.parent_user,
            phone="0911556677",
            relationship="Father",
            preferred_language="am"
        )

        # Student User & Profile
        self.student_user = User.objects.create_user(
            username="student_dani",
            email="dani@alpha.edu.et",
            password="studentpassword123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Daniel",
            last_name="Solomon"
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            student_id="ALPHA-001",
            first_name="Daniel",
            last_name="Solomon",
            date_of_birth=datetime.date(2010, 5, 12),
            gender="M"
        )
        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.academic_year,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            enrollment_date=datetime.date(2024, 9, 12),
            status=EnrollmentStatus.ACTIVE
        )

        # Link parent to student
        GuardianRelationship.objects.create(
            school=self.school,
            parent=self.parent_profile,
            student=self.student,
            is_primary=True
        )

    def test_01_ensure_and_render_default_sms_templates(self):
        """Verify default templates are created and rendered bilingually with placeholders."""
        ensure_default_sms_templates(self.school)

        templates_count = SMSTemplate.objects.filter(school=self.school).count()
        self.assertGreaterEqual(templates_count, 5)

        # Render Student Absence Template in Amharic
        context = {
            'student_name': self.student.full_name,
            'date': '2024-10-08',
            'school_name': self.school.name,
            'reason': 'Medical illness',
        }
        rendered_am = render_sms_template(self.school, SMSTemplateType.STUDENT_ABSENCE, context, lang='am')
        self.assertIn("Daniel Solomon", rendered_am)
        self.assertIn("Alpha Ethiopian Academy", rendered_am)
        self.assertIn("Medical illness", rendered_am)

        # Render in English
        rendered_en = render_sms_template(self.school, SMSTemplateType.STUDENT_ABSENCE, context, lang='en')
        self.assertIn("ABSENT", rendered_en)
        self.assertIn("Daniel Solomon", rendered_en)

    def test_02_student_absence_sms_alert_and_deduplication(self):
        """Verify student absence triggers SMS alert and prevents repeated spam on same day."""
        ensure_default_sms_templates(self.school)
        today = datetime.date.today()

        # First alert dispatch
        sent = send_student_absence_alert(
            school=self.school,
            student=self.student,
            date=today,
            reason="Unexcused absence",
            recorded_by=self.teacher
        )
        self.assertTrue(sent)

        # Verify NotificationLog created
        logs = NotificationLog.objects.filter(
            school=self.school,
            recipient=self.parent_user,
            channel=NotificationChannel.SMS,
            status='SENT'
        )
        self.assertEqual(logs.count(), 1)
        self.assertIn("Daniel Solomon", logs.first().message)

        # Subsequent dispatch for same student on same day should be deduplicated (False)
        sent_again = send_student_absence_alert(
            school=self.school,
            student=self.student,
            date=today,
            reason="Repeated save",
            recorded_by=self.teacher
        )
        self.assertFalse(sent_again)
        self.assertEqual(logs.count(), 1, "Duplicate SMS should have been blocked by deduplication guard.")

    def test_03_parent_meeting_request_and_sms_dispatch(self):
        """Verify scheduling a parent meeting creates request and dispatches SMS invitation."""
        ensure_default_sms_templates(self.school)
        self.client.login(username="admin_comm", password="adminpassword123")

        meeting_date = datetime.date.today() + datetime.timedelta(days=2)
        response = self.client.post(reverse('communication:create_parent_meeting'), {
            'student_id': str(self.student.id),
            'category': ParentMeetingCategory.ACADEMIC,
            'reason': 'Mid-semester performance review and tutoring plan.',
            'meeting_date': meeting_date.strftime('%Y-%m-%d'),
            'meeting_time': '10:30',
            'location': 'Principal Office',
            'contact_person': 'Almaz Kebede',
            'contact_phone': '0911223344',
            'send_sms': 'on',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        meeting = ParentMeetingRequest.objects.filter(school=self.school, student=self.student).first()
        self.assertIsNotNone(meeting)
        self.assertEqual(meeting.category, ParentMeetingCategory.ACADEMIC)
        self.assertTrue(meeting.sms_sent)

        # Verify notification log
        log = NotificationLog.objects.filter(
            school=self.school,
            subject=f"PARENT_MEETING:{meeting.id}"
        ).first()
        self.assertIsNotNone(log)
        self.assertIn("Daniel Solomon", log.message)

        # Update meeting status to completed with outcome notes
        update_url = reverse('communication:update_parent_meeting_status', kwargs={'meeting_id': meeting.id})
        resp_update = self.client.post(update_url, {
            'status': ParentMeetingStatus.COMPLETED,
            'outcome_notes': 'Parent agreed to enroll student in weekend chemistry clinic.'
        }, follow=True)
        self.assertEqual(resp_update.status_code, 200)

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, ParentMeetingStatus.COMPLETED)
        self.assertIn("weekend chemistry clinic", meeting.outcome_notes)

    def test_04_payment_reminder_engine_multi_stage(self):
        """Verify automated multi-stage payment reminders (7d, 3d, due-date, overdue)."""
        ensure_default_sms_templates(self.school)
        today = datetime.date.today()

        # Create 4 invoices with different due dates:
        # 1: Due in 7 days
        inv_7d = StudentInvoice.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.academic_year,
            invoice_number="INV-ALPHA-7D",
            total_amount=Decimal('5000.00'),
            paid_amount=Decimal('0.00'),
            due_date=today + datetime.timedelta(days=7),
            status=InvoiceStatus.UNPAID
        )

        # 2: Due in 3 days
        inv_3d = StudentInvoice.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.academic_year,
            invoice_number="INV-ALPHA-3D",
            total_amount=Decimal('4000.00'),
            paid_amount=Decimal('1000.00'),
            due_date=today + datetime.timedelta(days=3),
            status=InvoiceStatus.PARTIALLY_PAID
        )

        # 3: Due today
        inv_due = StudentInvoice.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.academic_year,
            invoice_number="INV-ALPHA-DUE",
            total_amount=Decimal('3500.00'),
            paid_amount=Decimal('0.00'),
            due_date=today,
            status=InvoiceStatus.UNPAID
        )

        # 4: Overdue
        inv_overdue = StudentInvoice.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.academic_year,
            invoice_number="INV-ALPHA-OVERDUE",
            total_amount=Decimal('6000.00'),
            paid_amount=Decimal('0.00'),
            due_date=today - datetime.timedelta(days=5),
            status=InvoiceStatus.OVERDUE
        )

        # Run payment reminder engine
        results = PaymentReminderService.run_due_date_reminders(self.school, target_date=today)

        self.assertEqual(results['reminders_dispatched'], 4)
        self.assertEqual(results['by_stage'][PaymentReminderStage.SEVEN_DAYS_BEFORE], 1)
        self.assertEqual(results['by_stage'][PaymentReminderStage.THREE_DAYS_BEFORE], 1)
        self.assertEqual(results['by_stage'][PaymentReminderStage.DUE_DATE], 1)
        self.assertEqual(results['by_stage'][PaymentReminderStage.OVERDUE], 1)

        # Verify PaymentReminderLogs exist
        logs = PaymentReminderLog.objects.filter(school=self.school)
        self.assertEqual(logs.count(), 4)

        # Deduplication check: Running the engine again on the same day should send 0 new reminders
        results_rerun = PaymentReminderService.run_due_date_reminders(self.school, target_date=today)
        self.assertEqual(results_rerun['reminders_dispatched'], 0, "Repeated run should dispatch 0 duplicates.")

    def test_05_user_presence_middleware_and_badges(self):
        """Verify UserPresenceMiddleware updates last_seen and calculates correct presence states."""
        self.client.login(username="admin_comm", password="adminpassword123")

        # Initial request triggers middleware
        response = self.client.get('/communication/parent-meetings/')
        self.assertEqual(response.status_code, 200)

        self.admin.refresh_from_db()
        self.assertIsNotNone(self.admin.last_seen)
        self.assertEqual(self.admin.presence_status, 'online')
        self.assertEqual(self.admin.presence_label, 'Online')
        self.assertIn('emerald', self.admin.presence_badge_classes)

        # Simulate 15 minutes ago (Away / Recently Active)
        self.admin.last_seen = timezone.now() - datetime.timedelta(minutes=15)
        self.admin.save(update_fields=['last_seen'])
        self.assertEqual(self.admin.presence_status, 'away')
        self.assertEqual(self.admin.presence_label, 'Recently Active')
        self.assertIn('amber', self.admin.presence_badge_classes)

        # Simulate 45 minutes ago (Offline)
        self.admin.last_seen = timezone.now() - datetime.timedelta(minutes=45)
        self.admin.save(update_fields=['last_seen'])
        self.assertEqual(self.admin.presence_status, 'offline')
        self.assertEqual(self.admin.presence_label, 'Offline')
        self.assertIn('slate', self.admin.presence_badge_classes)

    def test_06_sms_templates_customization_view(self):
        """Verify SMS template editing via admin dashboard."""
        ensure_default_sms_templates(self.school)
        self.client.login(username="admin_comm", password="adminpassword123")

        template = SMSTemplate.objects.filter(
            school=self.school, template_type=SMSTemplateType.STUDENT_ABSENCE
        ).first()

        new_en = "Custom Alert: {student_name} is absent from {school_name} on {date}."
        new_am = "ልዩ ማስታወቂያ: {student_name} በ {date} ከት/ቤት ቀርተዋል::"

        response = self.client.post(reverse('communication:sms_templates'), {
            'template_id': str(template.id),
            'name': 'Customized Absence SMS',
            'body_en': new_en,
            'body_am': new_am,
            'is_active': 'on',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        template.refresh_from_db()
        self.assertEqual(template.name, 'Customized Absence SMS')
        self.assertEqual(template.body_en, new_en)
        self.assertEqual(template.body_am, new_am)
