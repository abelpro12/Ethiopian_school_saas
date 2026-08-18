from decimal import Decimal
import datetime
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile, StudentStatus
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.finance.models import FeeCategory, FeeStructure, StudentInvoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus


class SaaSWorkflowTests(TestCase):
    def setUp(self):
        # Create Tenant School
        self.school = School.objects.create(
            name="Alpha Academy",
            subdomain="alpha",
            code="ALPHA",
            region="Addis Ababa"
        )

        # Admin User
        self.admin = User.objects.create_user(
            username="admin_alpha",
            email="admin@alpha.edu.et",
            password="password123",
            school=self.school,
            role=UserRole.SCHOOL_ADMIN
        )

        # Academic Setup
        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2016 E.C.",
            ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 11),
            gregorian_end_date=datetime.date(2024, 7, 7)
        )
        self.semester = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.ay,
            name="Semester 1",
            start_date=self.ay.gregorian_start_date,
            end_date=datetime.date(2024, 2, 1),
            is_current=True
        )

        self.grade9 = Grade.objects.create(school=self.school, level=9, name="Grade 9")
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section = Section.objects.create(
            school=self.school, grade=self.grade9,
            stream=self.stream, name="9-A", capacity=40
        )
        self.subject = Subject.objects.create(
            school=self.school, code="ENG-09", name="English", grade=self.grade9, stream=self.stream
        )

        # Teacher User & Profile
        self.teacher_user = User.objects.create_user(
            username="teacher1", email="teacher1@alpha.edu.et", password="password123",
            school=self.school, role=UserRole.TEACHER, first_name="Abebe", last_name="Bikila"
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school, user=self.teacher_user, employee_id="EMP-001", )
        TeacherAssignment.objects.create(
            school=self.school, academic_year=self.ay, teacher=self.teacher,
            subject=self.subject, section=self.section
        )

        # Student User & Profile
        self.student_user = User.objects.create_user(
            username="student1", email="student1@alpha.edu.et", password="password123",
            school=self.school, role=UserRole.STUDENT, first_name="Kebede", last_name="Tassew"
        )
        self.student = StudentProfile.objects.create(
            school=self.school, user=self.student_user, student_id="STU-101",
            first_name="Kebede", middle_name="Tassew", last_name="Mamo", gender="M"
        )

        self.enrollment = StudentEnrollment.objects.create(
            school=self.school, academic_year=self.ay, student=self.student,
            grade=self.grade9, stream=self.stream, section=self.section, status=EnrollmentStatus.ACTIVE
        )

        # Parent User & Profile
        self.parent_user = User.objects.create_user(
            username="parent1", email="parent1@alpha.edu.et", password="password123",
            school=self.school, role=UserRole.PARENT, first_name="Tassew", last_name="Mamo"
        )
        self.parent = ParentProfile.objects.create(
            school=self.school, user=self.parent_user, phone="+251911000000"
        )
        GuardianRelationship.objects.create(
            school=self.school, parent=self.parent, student=self.student
        )

    def test_tenant_isolation(self):
        other_school = School.objects.create(name="Beta School", code="BETA", subdomain="beta")
        other_student_user = User.objects.create_user(
            username="beta_student", school=other_school, role=UserRole.STUDENT
        )
        other_student = StudentProfile.objects.create(
            school=other_school, user=other_student_user, student_id="STU-202",
            first_name="Almaz", middle_name="Ayana", last_name="Dibaba", gender="F"
        )

        alpha_students = StudentProfile.objects.filter(school=self.school)
        self.assertIn(self.student, alpha_students)
        self.assertNotIn(other_student, alpha_students)

    def test_attendance_and_conduct(self):
        record, created = AttendanceRecord.objects.update_or_create(
            school=self.school, section=self.section, student=self.student,
            date=datetime.date.today(), defaults={'status': AttendanceStatus.PRESENT, 'recorded_by': self.teacher_user}
        )
        self.assertTrue(created)
        self.assertEqual(record.status, AttendanceStatus.PRESENT)

    def test_continuous_assessment_and_publishing(self):
        comp = AssessmentComponent.objects.create(
            school=self.school, academic_year=self.ay, period=self.semester,
            subject=self.subject, name="Final Exam", weight=Decimal('50.00'), max_marks=Decimal('50.00')
        )
        mark = StudentMark.objects.create(
            school=self.school, enrollment=self.enrollment, assessment_component=comp,
            mark_value=Decimal('45.00'), status=MarkStatus.DRAFT, entered_by=self.teacher_user
        )
        self.assertEqual(mark.status, MarkStatus.DRAFT)

        # Publish mark
        mark.status = MarkStatus.PUBLISHED
        mark.save()
        self.assertEqual(mark.status, MarkStatus.PUBLISHED)

    def test_financial_invoice_and_payment(self):
        cat = FeeCategory.objects.create(school=self.school, name="Tuition Fee")
        struct = FeeStructure.objects.create(
            school=self.school, academic_year=self.ay, grade=self.grade9,
            fee_category=cat, amount=Decimal('2000.00'), due_date=datetime.date.today()
        )

        invoice = StudentInvoice.objects.create(
            school=self.school, student=self.student, academic_year=self.ay,
            invoice_number="INV-2016-STU-101", total_amount=Decimal('2000.00'),
            due_date=datetime.date.today(), status=InvoiceStatus.UNPAID
        )

        payment = Payment.objects.create(
            school=self.school, invoice=invoice, tx_ref="PAY-1001",
            amount_paid=Decimal('2000.00'), payment_method=PaymentMethod.CASH,
            status=PaymentStatus.SUCCESS, receipt_no="REC-1001"
        )
        invoice.paid_amount += payment.amount_paid
        invoice.status = InvoiceStatus.PAID
        invoice.save()

        self.assertEqual(invoice.remaining_balance, Decimal('0.00'))
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
