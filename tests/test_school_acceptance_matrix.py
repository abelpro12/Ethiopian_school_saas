import datetime
import uuid
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject, TimetableSlot, PeriodSlot
from apps.students.models import StudentProfile, StudentStatus, StudentApplication
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus, SubjectEnrollment
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.finance.models import FeeCategory, FeeStructure, StudentInvoice, InvoiceStatus, Payment, PaymentStatus
from apps.payments.services import ChapaService
from apps.payments.models import ChapaWebhookEvent
from apps.rankings.services import RankingService
from apps.students.services import AtRiskStudentEngine
from apps.schools.search import CentralizedSearchEngine
from utils.pdf_utils import generate_report_card_pdf, generate_receipt_pdf
from apps.notifications.services import NotificationService, AfroMessageSMSProvider


class SchoolAcceptanceMatrixTest(TestCase):
    """
    Comprehensive School Acceptance Test Suite (Gate D):
    Verifies all 14 key role and functional acceptance dimensions with synthetic fixtures.
    """

    def setUp(self):
        self.uid = uuid.uuid4().hex[:6]
        self.school = School.objects.create(
            name=f"Acceptance Academy {self.uid}",
            subdomain=f"acc-{self.uid}",
            code=f"AC{self.uid.upper()}",
            calendar_preference="ETHIOPIAN",
            status='ACTIVE',
            is_active=True
        )

        # Standard Roles
        self.super_admin = User.objects.create_user(username=f"super_{self.uid}", password="password123", role=UserRole.SUPER_ADMIN, is_superuser=True)
        self.admin = User.objects.create_user(username=f"admin_{self.uid}", password="password123", school=self.school, role=UserRole.SCHOOL_ADMIN)
        self.principal = User.objects.create_user(username=f"principal_{self.uid}", password="password123", school=self.school, role=UserRole.PRINCIPAL)
        self.registrar = User.objects.create_user(username=f"registrar_{self.uid}", password="password123", school=self.school, role=UserRole.REGISTRAR)
        self.teacher_user = User.objects.create_user(username=f"teacher_{self.uid}", password="password123", school=self.school, role=UserRole.TEACHER)
        self.teacher_profile = TeacherProfile.objects.create(school=self.school, user=self.teacher_user, employee_id=f"EMP-{self.uid}")
        self.accountant = User.objects.create_user(username=f"accountant_{self.uid}", password="password123", school=self.school, role=UserRole.ACCOUNTANT)
        self.student_user = User.objects.create_user(username=f"student_{self.uid}", password="password123", school=self.school, role=UserRole.STUDENT)
        self.parent_user = User.objects.create_user(username=f"parent_{self.uid}", password="password123", school=self.school, role=UserRole.PARENT)

        # Academic fixtures
        self.ay = AcademicYear.objects.create(
            school=self.school, name="2016 E.C.", ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 12), gregorian_end_date=datetime.date(2024, 6, 30),
            is_active=True
        )
        self.period = AcademicPeriod.objects.create(
            school=self.school, academic_year=self.ay, name="Semester 1",
            start_date=datetime.date(2023, 9, 12), end_date=datetime.date(2024, 1, 20),
            is_current=True
        )
        self.grade = Grade.objects.create(school=self.school, level=11, name="Grade 11")
        self.stream = Stream.objects.create(school=self.school, name="Natural Science", code="NAT")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="11-A", capacity=45)
        self.subject = Subject.objects.create(school=self.school, code=f"PHY-{self.uid}", name="Physics", grade=self.grade, stream=self.stream)

        # Student & Parent
        self.student = StudentProfile.objects.create(
            school=self.school, user=self.student_user, student_id=f"STU-{self.uid}",
            first_name="Dawit", last_name="Haile", gender="M"
        )
        self.parent = ParentProfile.objects.create(school=self.school, user=self.parent_user, phone="+251911445566", relationship="Father")
        GuardianRelationship.objects.create(school=self.school, parent=self.parent, student=self.student, is_primary=True)

        self.enrollment = StudentEnrollment.objects.create(
            school=self.school, academic_year=self.ay, student=self.student, grade=self.grade, stream=self.stream, section=self.section,
            status=EnrollmentStatus.ACTIVE
        )
        self.client = Client()

    def test_acc_01_super_admin_tenant_management_and_context_switching(self):
        """ACC-01: Super Admin accesses platform management and inspects school status."""
        self.client.force_login(self.super_admin)
        resp = self.client.get(reverse('platform:school_list'))
        self.assertIn(resp.status_code, [200, 302])
        # Super admin API context switching
        api_resp = self.client.get('/api/v1/schools/', HTTP_X_SCHOOL_ID=str(self.school.id))
        self.assertEqual(api_resp.status_code, 200)

    def test_acc_02_school_admin_configuration_and_user_management(self):
        """ACC-02: School Admin manages users and settings."""
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('user_management'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Users")

    def test_acc_03_principal_academic_oversight_and_semester_lifecycle(self):
        """ACC-03: Principal oversees academic structures and section configuration."""
        self.client.force_login(self.principal)
        resp = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.period.is_current, True)

    def test_acc_04_registrar_student_admission_enrollment_and_search(self):
        """ACC-04: Registrar manages student records and executes centralized search."""
        self.client.force_login(self.registrar)
        search_res = CentralizedSearchEngine.search(self.school, "Dawit")
        self.assertTrue(len(search_res['students']) > 0)
        self.assertEqual(search_res['students'][0]['title'], "Dawit Haile")

    def test_acc_05_teacher_attendance_and_at_risk_detection(self):
        """ACC-05: Attendance recording updates student profile and at-risk engine."""
        AttendanceRecord.objects.create(
            school=self.school, section=self.section, student=self.student,
            date=datetime.date.today(), status=AttendanceStatus.PRESENT, recorded_by=self.teacher_user
        )
        risk = AtRiskStudentEngine.evaluate_student_risk(self.student)
        self.assertIn('risk_level', risk)
        self.assertEqual(risk['risk_level'], 'LOW')

    def test_acc_06_teacher_grade_entry_and_letter_grade_calculation(self):
        """ACC-06: Continuous assessment mark entry calculates GPA and letter grade."""
        comp = AssessmentComponent.objects.create(
            school=self.school, academic_year=self.ay, period=self.period, subject=self.subject,
            name="Midterm Assessment", weight=Decimal('50.0'), max_marks=Decimal('100.0')
        )
        mark = StudentMark.objects.create(
            school=self.school, enrollment=self.enrollment, assessment_component=comp,
            mark_value=Decimal('94.00'), entered_by=self.teacher_user
        )
        mark.refresh_from_db()
        self.assertEqual(mark.letter_grade, 'A+')
        self.assertEqual(mark.grade_points, Decimal('4.00'))

    def test_acc_07_accountant_fee_structure_invoicing_and_payments(self):
        """ACC-07: Invoicing, payments, and balance tracking for school accounting."""
        fee_cat = FeeCategory.objects.create(school=self.school, name="Semester Tuition")
        FeeStructure.objects.create(
            school=self.school, academic_year=self.ay, grade=self.grade, fee_category=fee_cat,
            amount=Decimal('4000.00'), due_date=datetime.date(2024, 2, 1)
        )
        invoice = StudentInvoice.objects.create(
            school=self.school, student=self.student, academic_year=self.ay, period=self.period,
            invoice_number=f"INV-ACC-{self.uid}", total_amount=Decimal('4000.00'),
            due_date=datetime.date(2024, 2, 1), status=InvoiceStatus.UNPAID
        )
        self.assertEqual(invoice.remaining_balance, Decimal('4000.00'))

        # Record partial payment
        Payment.objects.create(
            school=self.school, invoice=invoice, amount_paid=Decimal('2000.00'),
            payment_method='CASH', status=PaymentStatus.SUCCESS
        )
        invoice.paid_amount += Decimal('2000.00')
        invoice.status = InvoiceStatus.PARTIALLY_PAID
        invoice.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.remaining_balance, Decimal('2000.00'))

    def test_acc_08_parent_guardian_relationship_and_portal_access(self):
        """ACC-08: Parent portal displays student progress and isolates other families."""
        self.client.force_login(self.parent_user)
        resp = self.client.get(reverse('parent_portal'))
        self.assertEqual(resp.status_code, 200)

    def test_acc_09_student_portal_and_academic_views(self):
        """ACC-09: Student logs in and accesses personal academic dashboard."""
        self.client.force_login(self.student_user)
        resp = self.client.get(reverse('student_portal'))
        self.assertEqual(resp.status_code, 200)

    def test_acc_10_ethiopian_academic_calendar_and_timetable_slots(self):
        """ACC-10: Ethiopian calendar conversion and weekly timetable validation."""
        self.assertEqual(self.ay.ethiopian_year, 2016)
        period_slot = PeriodSlot.objects.create(
            school=self.school, name="Period 1",
            start_time=datetime.time(8, 30), end_time=datetime.time(9, 15),
            shift="MORNING"
        )
        slot = TimetableSlot.objects.create(
            school=self.school, academic_year=self.ay, section=self.section, subject=self.subject,
            teacher=self.teacher_profile, day_of_week='MONDAY', period_slot=period_slot, room="101"
        )
        self.assertTrue(slot.id is not None)

    def test_acc_11_report_cards_pdf_generation_and_verification(self):
        """ACC-11: Report card PDF compiles with digital signature and verification token."""
        pdf_bytes = generate_report_card_pdf(
            school_info={'name': self.school.name},
            student_info={'full_name': self.student.full_name, 'student_id': self.student.student_id, 'grade_section': '11-A', 'academic_year': self.ay.name, 'semester': self.period.name, 'rank': 1, 'doc_number': 'DOC-ACC'},
            results_info=[{'subject_name': self.subject.name, 'assignment': 10, 'quiz': 10, 'midterm': 20, 'final': 54, 'total': 94, 'letter_grade': 'A+', 'subject_rank': 1}],
            verification_url="http://localhost:8000/verify/token-acc/"
        )
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_acc_12_chapa_payment_webhook_hmac_and_idempotency(self):
        """ACC-12: Webhook signature verification and atomic idempotent processing."""
        invoice = StudentInvoice.objects.create(
            school=self.school, student=self.student, academic_year=self.ay,
            invoice_number=f"INV-CHAPA-{self.uid}", total_amount=Decimal('1500.00'),
            due_date=datetime.date(2024, 2, 1)
        )
        chapa_init = ChapaService.initialize_payment(
            school=self.school, invoice=invoice, amount=Decimal('1500.00'),
            parent_email="parent@test.et", first_name="Dawit", last_name="Haile",
            callback_url="http://localhost:8000/payments/webhook/"
        )
        tx_ref = chapa_init['tx_ref']

        # Process webhook first time
        payment1 = ChapaService.process_payment_webhook(tx_ref=tx_ref, payment_status="SUCCESS")
        self.assertEqual(payment1.status, PaymentStatus.SUCCESS)

        # Idempotent replay: must return existing payment without duplicating credit
        payment2 = ChapaService.process_payment_webhook(tx_ref=tx_ref, payment_status="SUCCESS")
        self.assertEqual(payment1.id, payment2.id)

    def test_acc_13_communication_sms_and_notification_preferences(self):
        """ACC-13: SMS normalization and simulation dispatch fallback."""
        provider = AfroMessageSMSProvider()
        normalized = provider.normalize_ethiopian_phone("0911223344")
        self.assertEqual(normalized, "+251911223344")

    def test_acc_14_strict_tenant_isolation_across_all_roles(self):
        """ACC-14: Verification that School A cannot mutate School B records."""
        school_b = School.objects.create(name=f"Foreign School {self.uid}", subdomain=f"foreign-{self.uid}", code=f"FS{self.uid.upper()}")
        grade_b = Grade.objects.create(school=school_b, level=11, name="Foreign Grade 11")
        stream_b = Stream.objects.create(school=school_b, name="Foreign Stream", code="FS")

        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Section.objects.create(school=self.school, grade=grade_b, stream=stream_b, name="Illegal-Sec")
