import datetime
from decimal import Decimal
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
from apps.grading.services import GradeService
from apps.rankings.services import RankingService
from apps.finance.models import FeeCategory, FeeStructure, StudentInvoice, InvoiceStatus, Payment, PaymentStatus
from apps.payments.services import ChapaService
from apps.reports.models import DocumentVerification
from apps.audit.services import AuditService
from utils.pdf_utils import generate_report_card_pdf, generate_receipt_pdf


class CriticalEndToEndWorkflowTest(TestCase):
    def test_24_step_master_school_workflow(self):
        import uuid
        code = f"E2E-{uuid.uuid4().hex[:6].upper()}"
        sub = f"sub-{uuid.uuid4().hex[:6].lower()}"
        # Step 1: Create School
        school = School.objects.create(
            name="Addis International Academy",
            subdomain=sub,
            code=code,
            calendar_preference="ETHIOPIAN"
        )
        self.assertEqual(school.code, code)

        # Step 2: Create Admin
        admin_user = User.objects.create_user(
            username="school_admin",
            email="admin@addisacademy.edu.et",
            password="adminpassword123",
            school=school,
            role=UserRole.SCHOOL_ADMIN
        )
        self.assertTrue(admin_user.has_school_permission('marks.approve'))

        # Step 3: Configure Academic Year
        ay = AcademicYear.objects.create(
            school=school,
            name="2016 E.C. (2023/24)",
            ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 12),
            gregorian_end_date=datetime.date(2024, 6, 30),
            is_active=True
        )

        semester1 = AcademicPeriod.objects.create(
            school=school,
            academic_year=ay,
            name="Semester 1",
            start_date=datetime.date(2023, 9, 12),
            end_date=datetime.date(2024, 1, 20),
            is_current=True
        )

        # Step 4: Create Grade 11
        grade11 = Grade.objects.create(school=school, level=11, name="Grade 11")

        # Step 5: Create Natural Science Stream
        nat_stream = Stream.objects.create(school=school, name="Natural Science", code="NAT")

        # Step 6: Create Section 11-Nat-1
        section = Section.objects.create(
            school=school,
            grade=grade11,
            stream=nat_stream,
            name="11-Nat-1",
            capacity=45,
            shift="FULL_DAY"
        )

        # Step 7: Create Physics Subject
        physics = Subject.objects.create(
            school=school,
            code="PHY-11",
            name="Physics",
            amharic_name="ፊዚክስ",
            grade=grade11,
            stream=nat_stream
        )

        # Step 8: Create Teacher
        teacher_user = User.objects.create_user(
            username="teacher_physics",
            school=school,
            role=UserRole.TEACHER
        )
        teacher_profile = TeacherProfile.objects.create(
            school=school,
            user=teacher_user,
            employee_id="EMP-101",
            specialization="Physics"
        )

        # Step 9: Create Parent
        parent_user = User.objects.create_user(
            username="parent_kebede",
            school=school,
            role=UserRole.PARENT
        )
        parent_profile = ParentProfile.objects.create(
            school=school,
            user=parent_user,
            phone="+251911000000",
            relationship="Father"
        )

        # Step 10: Create Student
        student_user = User.objects.create_user(
            username="student_abebe",
            school=school,
            role=UserRole.STUDENT
        )
        student_profile = StudentProfile.objects.create(
            school=school,
            user=student_user,
            student_id="AIA-STU-001",
            first_name="Abebe",
            middle_name="Kebede",
            last_name="Tadesse",
            gender="M"
        )
        GuardianRelationship.objects.create(
            school=school,
            parent=parent_profile,
            student=student_profile,
            is_primary=True
        )

        # Step 11: Enroll Student
        enrollment = StudentEnrollment.objects.create(
            school=school,
            academic_year=ay,
            student=student_profile,
            grade=grade11,
            stream=nat_stream,
            section=section,
            status=EnrollmentStatus.ACTIVE
        )

        # Step 12: Assign Teacher
        TeacherAssignment.objects.create(
            school=school,
            academic_year=ay,
            teacher=teacher_profile,
            subject=physics,
            section=section
        )

        # Step 13: Teacher Takes Attendance
        att = AttendanceRecord.objects.create(
            school=school,
            section=section,
            student=student_profile,
            date=datetime.date.today(),
            status=AttendanceStatus.PRESENT,
            recorded_by=teacher_user
        )
        self.assertEqual(att.status, AttendanceStatus.PRESENT)

        # Step 14: Assessment Components & Mark Entry
        comp_final = AssessmentComponent.objects.create(
            school=school,
            academic_year=ay,
            period=semester1,
            subject=physics,
            name="Final Exam",
            weight=Decimal('60.00'),
            max_marks=Decimal('60.00')
        )
        mark = StudentMark.objects.create(
            school=school,
            enrollment=enrollment,
            assessment_component=comp_final,
            mark_value=Decimal('55.00'),
            status=MarkStatus.DRAFT,
            entered_by=teacher_user
        )

        # Step 15 & 16: Teacher Submits, Admin Approves & Publishes
        mark.status = MarkStatus.APPROVED
        mark.save()
        mark.status = MarkStatus.PUBLISHED
        mark.save()
        self.assertEqual(mark.status, MarkStatus.PUBLISHED)

        # Grade calculation
        letter_grade = GradeService.get_letter_grade(school, 55.00)
        self.assertIn(letter_grade, ['A+', 'A', 'B+', 'B', 'C+', 'C', 'D', 'F'])

        # Step 17: Ranking Calculation
        rankings = RankingService.calculate_ranks_for_section(
            school=school,
            academic_year=ay,
            period=semester1,
            section=section
        )
        self.assertEqual(len(rankings), 1)
        self.assertEqual(rankings[0].section_rank, 1)

        # Step 18: Generate PDF Report Card
        pdf_bytes = generate_report_card_pdf(
            school_info={'name': school.name, 'phone': '+251111223344'},
            student_info={'full_name': student_profile.full_name, 'student_id': student_profile.student_id, 'grade_section': f"{section.grade.name}-{section.name}", 'academic_year': ay.name, 'semester': semester1.name, 'rank': 1, 'doc_number': 'DOC-1001'},
            results_info=[{'subject_name': physics.name, 'assignment': 10, 'quiz': 10, 'midterm': 20, 'final': 55, 'total': 95, 'letter_grade': 'A+', 'subject_rank': 1}],
            verification_url="http://localhost:8000/verify/sample-token/"
        )
        self.assertTrue(len(pdf_bytes) > 0)

        # Step 19: Create Tuition Invoice (5,000 ETB)
        fee_cat = FeeCategory.objects.create(school=school, name="Tuition Fee")
        invoice = StudentInvoice.objects.create(
            school=school,
            student=student_profile,
            academic_year=ay,
            period=semester1,
            invoice_number="INV-2016-001",
            total_amount=Decimal('5000.00'),
            due_date=datetime.date(2024, 2, 1),
            status=InvoiceStatus.UNPAID
        )

        # Step 20 & 21: Parent Initiates Chapa Payment & Webhook Processed
        chapa_res = ChapaService.initialize_payment(
            school=school,
            invoice=invoice,
            amount=Decimal('5000.00'),
            parent_email="parent@kebede.et",
            first_name="Kebede",
            last_name="Tadesse",
            callback_url="http://localhost:8000/payments/webhook/"
        )
        tx_ref = chapa_res['tx_ref']

        processed_payment = ChapaService.process_payment_webhook(
            tx_ref=tx_ref,
            payment_status="SUCCESS"
        )
        self.assertEqual(processed_payment.status, PaymentStatus.SUCCESS)

        # Step 22: Invoice Balance Updated & Receipt Issued
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.remaining_balance, Decimal('0.00'))

        # Step 23: Public Document Verification Token
        doc_verification = DocumentVerification.objects.filter(school=school, document_type='RECEIPT').first()
        self.assertIsNotNone(doc_verification)
        self.assertTrue(doc_verification.is_valid)

        # Step 24: Audit Log Entry
        audit = AuditService.log_action(
            school=school,
            user=admin_user,
            action="RESULT_PUBLISHED",
            object_type="StudentMark",
            object_id=mark.id
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "RESULT_PUBLISHED")
