import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Stream, Section
from apps.students.models import StudentProfile, StudentClearance, ClearanceStatus, WithdrawalReason
from apps.enrollment.models import StudentEnrollment
from apps.finance.models import FeeCategory, StudentInvoice, InvoiceStatus
from apps.library.models import Book, BookCopy, BookStatus, BorrowRecord
from apps.teachers.models import TeacherProfile, StaffProfile, StaffPosition, StaffDocument, StaffDocumentType
from apps.attendance.models import StaffAttendanceRecord, StaffAttendanceStatus
from apps.students.clearance_service import ClearanceService


class StudentClearanceAndStaffOnboardingTests(TestCase):
    """
    Unit and integration tests for:
    - Priority 2: Student Clearance & Multi-Department Withdrawal Workflow
    - Priority 2: Teacher Recruitment Pipeline & Staff Document Verification
    - Priority 2: Non-Teaching & Teaching Staff Attendance Verification and Monthly Export
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Seattle Academy",
            code="SEA",
            calendar_preference="ETHIOPIAN"
        )

        # Admin User
        self.admin = User.objects.create_superuser(
            username="admin_sea",
            email="admin@seattle.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        # Librarian & Accountant Users
        self.librarian = User.objects.create_user(
            username="lib_aster",
            email="aster@seattle.edu.et",
            password="libpass123",
            role=UserRole.LIBRARIAN,
            school=self.school,
            first_name="Aster",
            last_name="Mekonnen"
        )
        self.accountant = User.objects.create_user(
            username="acct_dawit",
            email="dawit@seattle.edu.et",
            password="acctpass123",
            role=UserRole.ACCOUNTANT,
            school=self.school,
            first_name="Dawit",
            last_name="Tadesse"
        )

        # Academic Year, Grade & Section
        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2018 E.C. (2025/2026)",
            ethiopian_year=2018,
            gregorian_start_date=datetime.date(2025, 9, 1),
            gregorian_end_date=datetime.date(2026, 6, 30),
            is_active=True
        )
        self.grade = Grade.objects.create(school=self.school, name="Grade 10", level=10)
        self.stream = Stream.objects.create(school=self.school, name="General Stream", code="GEN")
        self.section = Section.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="10-A",
            is_active=True
        )

        # Student User & Profile
        self.student_user = User.objects.create_user(
            username="student_chala",
            email="chala@seattle.edu.et",
            password="studentpass123",
            role=UserRole.STUDENT,
            school=self.school,
            first_name="Chala",
            last_name="Bekele"
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            school=self.school,
            student_id="SEA-STU-0001",
            first_name="Chala",
            middle_name="Tola",
            last_name="Bekele",
            gender="MALE",
            date_of_birth=datetime.date(2010, 5, 12),
            status="ACTIVE"
        )
        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.ay,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            status="ACTIVE"
        )

        # Finance Setup: Unpaid balance of 1000 ETB
        self.fee_cat = FeeCategory.objects.create(
            school=self.school,
            name="Tuition Fee"
        )
        self.invoice = StudentInvoice.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.ay,
            invoice_number="INV-2026-0001",
            total_amount=Decimal("1500.00"),
            discount_amount=Decimal("0.00"),
            paid_amount=Decimal("500.00"),
            due_date=datetime.date(2026, 3, 1),
            status=InvoiceStatus.PARTIALLY_PAID
        )

        # Library Setup: Unreturned borrowed book
        self.book = Book.objects.create(
            school=self.school,
            title="General Physics Grade 10",
            author="MoE Ethiopia",
            isbn="978-99944-0-123-4",
            total_copies=5
        )
        self.book_copy = BookCopy.objects.create(
            school=self.school,
            book=self.book,
            copy_number="PHY-001",
            status=BookStatus.BORROWED
        )
        self.borrow_record = BorrowRecord.objects.create(
            school=self.school,
            book_copy=self.book_copy,
            borrower_student=self.student,
            borrowed_date=datetime.date(2026, 1, 15),
            due_date=datetime.date(2026, 2, 15),
            return_date=None,
            issued_by=self.librarian
        )

        # Teacher Setup
        self.teacher_user = User.objects.create_user(
            username="teacher_yared",
            email="yared@seattle.edu.et",
            password="teacherpass123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Yared",
            last_name="Girma"
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            school=self.school,
            employee_id="SEA-TCH-0005",
            department="Natural Science",
            specialization="Physics",
            onboarding_status="APPLIED"
        )

        # Non-teaching Staff Setup
        self.staff_profile = StaffProfile.objects.create(
            user=self.librarian,
            school=self.school,
            employee_id="SEA-STF-0001",
            department="Library Services",
            position=StaffPosition.LIBRARIAN,
            phone="0911223344"
        )

    # ==========================================
    # 1. Student Clearance & Withdrawal Workflow
    # ==========================================

    def test_initiate_clearance_and_operational_detection(self):
        """Verifies clearance initiation automatically detects finance balance and library loans."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            reason_details="Relocating to Hawassa with family",
            destination_school="Hawassa Tabor Academy",
            user=self.admin
        )

        self.assertIsNotNone(clearance)
        self.assertTrue(clearance.clearance_number.startswith("SEA-CLR-"))
        self.assertEqual(clearance.status, ClearanceStatus.INITIATED)
        self.assertEqual(clearance.outstanding_balance, Decimal("1000.00"))
        self.assertIn("General Physics", clearance.library_remarks)
        self.assertEqual(clearance.destination_school, "Hawassa Tabor Academy")

        # Test duplicate prevention
        with self.assertRaises(ValidationError):
            ClearanceService.initiate_clearance(
                school=self.school,
                student=self.student,
                withdrawal_reason=WithdrawalReason.TRANSFER,
                user=self.admin
            )

    def test_multi_department_signoffs(self):
        """Tests individual sign-offs across Library, Finance, Academic, and Property departments."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            destination_school="Hawassa Tabor Academy",
            user=self.admin
        )

        # 1. Sign Library
        ClearanceService.sign_department(
            school=self.school,
            clearance=clearance,
            department='library',
            cleared=True,
            remarks="Physics book returned and inspected.",
            user=self.librarian
        )
        clearance.refresh_from_db()
        self.assertTrue(clearance.library_cleared)
        self.assertEqual(clearance.library_cleared_by, self.librarian)
        self.assertEqual(clearance.status, ClearanceStatus.UNDER_REVIEW)

        # 2. Sign Finance
        ClearanceService.sign_department(
            school=self.school,
            clearance=clearance,
            department='finance',
            cleared=True,
            remarks="Remaining 1000 ETB paid via Telebirr receipt ref #TLB84729.",
            user=self.accountant
        )
        clearance.refresh_from_db()
        self.assertTrue(clearance.finance_cleared)

        # 3. Sign Academic
        ClearanceService.sign_department(
            school=self.school,
            clearance=clearance,
            department='academic',
            cleared=True,
            remarks="All curriculum textbooks returned, grades submitted.",
            user=self.admin
        )
        clearance.refresh_from_db()
        self.assertTrue(clearance.academic_cleared)

        # 4. Sign Property
        ClearanceService.sign_department(
            school=self.school,
            clearance=clearance,
            department='property',
            cleared=True,
            remarks="Locker key 10A-14 returned.",
            user=self.admin
        )
        clearance.refresh_from_db()
        self.assertTrue(clearance.property_cleared)

        # Check total completion
        self.assertTrue(clearance.all_departments_cleared)
        self.assertEqual(clearance.cleared_departments_count, 4)

    def test_finalize_clearance_blocked_until_all_cleared(self):
        """Ensures final administrative approval is blocked if any department is still pending."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            user=self.admin
        )

        # Only clear Library
        ClearanceService.sign_department(
            school=self.school,
            clearance=clearance,
            department='library',
            cleared=True,
            user=self.librarian
        )

        with self.assertRaises(ValidationError) as ctx:
            ClearanceService.finalize_clearance(
                school=self.school,
                clearance=clearance,
                approved=True,
                user=self.admin
            )
        self.assertIn("Pending sign-off", str(ctx.exception))

    def test_finalize_clearance_approval_and_status_transitions(self):
        """Verifies full approval issues certificate and transitions StudentProfile and Enrollment to TRANSFERRED."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            destination_school="Nazareth School",
            user=self.admin
        )

        # Sign all 4 departments
        ClearanceService.sign_department(self.school, clearance, 'library', True, user=self.librarian)
        ClearanceService.sign_department(self.school, clearance, 'finance', True, user=self.accountant)
        ClearanceService.sign_department(self.school, clearance, 'academic', True, user=self.admin)
        ClearanceService.sign_department(self.school, clearance, 'property', True, user=self.admin)

        # Finalize Approval
        ClearanceService.finalize_clearance(
            school=self.school,
            clearance=clearance,
            approved=True,
            final_remarks="Approved for transfer to Nazareth School.",
            user=self.admin
        )

        clearance.refresh_from_db()
        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()

        self.assertEqual(clearance.status, ClearanceStatus.APPROVED)
        self.assertTrue(clearance.certificate_issued)
        self.assertEqual(clearance.certificate_number, clearance.clearance_number)
        self.assertEqual(clearance.final_approved_by, self.admin)

        # Status transitions
        self.assertEqual(self.student.status, "TRANSFERRED")
        self.assertEqual(self.enrollment.status, "TRANSFERRED")

    def test_finalize_clearance_withdrawal_reason_withdrawn_status(self):
        """Verifies non-transfer reason (e.g. Relocation) sets student status to WITHDRAWN."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.RELOCATION,
            user=self.admin
        )

        ClearanceService.sign_department(self.school, clearance, 'library', True, user=self.librarian)
        ClearanceService.sign_department(self.school, clearance, 'finance', True, user=self.accountant)
        ClearanceService.sign_department(self.school, clearance, 'academic', True, user=self.admin)
        ClearanceService.sign_department(self.school, clearance, 'property', True, user=self.admin)

        ClearanceService.finalize_clearance(
            school=self.school,
            clearance=clearance,
            approved=True,
            user=self.admin
        )

        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()

        self.assertEqual(self.student.status, "WITHDRAWN")
        self.assertEqual(self.enrollment.status, "WITHDRAWN")

    def test_clearance_rejection(self):
        """Verifies administrative rejection blocks the clearance."""
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            user=self.admin
        )

        ClearanceService.finalize_clearance(
            school=self.school,
            clearance=clearance,
            approved=False,
            final_remarks="Blocked due to severe disciplinary hearing pending.",
            user=self.admin
        )

        clearance.refresh_from_db()
        self.assertEqual(clearance.status, ClearanceStatus.REJECTED)
        self.assertEqual(self.student.status, "ACTIVE")

    # ===============================================
    # 2. Teacher Recruitment Pipeline & Document Audit
    # ===============================================

    def test_teacher_onboarding_pipeline_progression(self):
        """Tests advancing candidate through recruitment stages: APPLIED -> INTERVIEWED -> OFFERED -> ONBOARDING -> ACTIVE."""
        self.assertEqual(self.teacher.onboarding_status, "APPLIED")

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('teachers:update_stage', kwargs={'teacher_id': self.teacher.id}),
            {
                'onboarding_status': 'INTERVIEWED',
                'background_check_completed': '1',
                'contract_signed': '0',
                'emergency_contact_name': 'Marta Girma',
                'emergency_contact_phone': '0911009988'
            }
        )
        self.assertEqual(response.status_code, 302)

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.onboarding_status, "INTERVIEWED")
        self.assertTrue(self.teacher.background_check_completed)
        self.assertFalse(self.teacher.contract_signed)
        self.assertEqual(self.teacher.emergency_contact_name, "Marta Girma")

        # Advance to Active
        self.client.post(
            reverse('teachers:update_stage', kwargs={'teacher_id': self.teacher.id}),
            {
                'onboarding_status': 'ACTIVE',
                'background_check_completed': '1',
                'contract_signed': '1',
            }
        )
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.onboarding_status, "ACTIVE")
        self.assertTrue(self.teacher.contract_signed)

    def test_staff_document_upload_and_verification_workflow(self):
        """Tests staff document upload, verification stamp, and rejection."""
        fake_file = SimpleUploadedFile("physics_degree.pdf", b"PDF content test", content_type="application/pdf")

        doc = StaffDocument.objects.create(
            school=self.school,
            teacher=self.teacher,
            document_type=StaffDocumentType.CERTIFICATE,
            title="BSc in Physics - AAU",
            file=fake_file,
            uploaded_by=self.admin,
            verification_status='PENDING'
        )

        self.assertEqual(doc.verification_status, 'PENDING')
        self.assertIsNone(doc.verified_by)

        self.client.force_login(self.admin)

        # Verify Document
        response = self.client.post(
            reverse('teachers:verify_document', kwargs={'document_id': doc.id}),
            {'action': 'verify', 'notes': 'Verified against official AAU registrar copy.'}
        )
        self.assertEqual(response.status_code, 302)

        doc.refresh_from_db()
        self.assertEqual(doc.verification_status, 'VERIFIED')
        self.assertEqual(doc.verified_by, self.admin)
        self.assertIsNotNone(doc.verified_at)
        self.assertIn("AAU", doc.notes)

        # Reject Document Test
        fake_file2 = SimpleUploadedFile("expired_license.pdf", b"Test", content_type="application/pdf")
        doc2 = StaffDocument.objects.create(
            school=self.school,
            teacher=self.teacher,
            document_type=StaffDocumentType.EMPLOYMENT,
            title="Teaching License",
            file=fake_file2,
            uploaded_by=self.admin,
            verification_status='PENDING'
        )

        self.client.post(
            reverse('teachers:verify_document', kwargs={'document_id': doc2.id}),
            {'action': 'reject', 'notes': 'License is expired.'}
        )
        doc2.refresh_from_db()
        self.assertEqual(doc2.verification_status, 'REJECTED')

    # ========================================================
    # 3. Non-Teaching Staff Attendance & Monthly Export
    # ========================================================

    def test_staff_attendance_and_monthly_export(self):
        """Tests recording staff attendance and exporting monthly reports in CSV and Excel."""
        today = datetime.date.today()

        # Create attendance records for both teacher and non-teaching staff
        StaffAttendanceRecord.objects.create(
            school=self.school,
            staff_user=self.teacher_user,
            date=today,
            status=StaffAttendanceStatus.PRESENT,
            recorded_by=self.admin
        )
        StaffAttendanceRecord.objects.create(
            school=self.school,
            staff_user=self.librarian,
            date=today,
            status=StaffAttendanceStatus.LATE,
            recorded_by=self.admin
        )

        self.client.force_login(self.admin)

        # Test Staff Attendance View with category filter
        resp_all = self.client.get(reverse('attendance:staff_attendance'), {'category': 'all'})
        self.assertEqual(resp_all.status_code, 200)

        resp_teaching = self.client.get(reverse('attendance:staff_attendance'), {'category': 'teaching'})
        self.assertEqual(resp_teaching.status_code, 200)

        resp_non_teaching = self.client.get(reverse('attendance:staff_attendance'), {'category': 'non_teaching'})
        self.assertEqual(resp_non_teaching.status_code, 200)

        # Test CSV Export
        export_csv_url = f"{reverse('attendance:staff_attendance_export')}?month={today.month}&year={today.year}&category=all&format=csv"
        csv_resp = self.client.get(export_csv_url)
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('Staff_Attendance_Report', csv_resp['Content-Disposition'])
        content = csv_resp.content.decode('utf-8')
        self.assertIn("Yared Girma", content)
        self.assertIn("Aster Mekonnen", content)

        # Test Excel Export
        export_xlsx_url = f"{reverse('attendance:staff_attendance_export')}?month={today.month}&year={today.year}&category=all&format=xlsx"
        xlsx_resp = self.client.get(export_xlsx_url)
        self.assertEqual(xlsx_resp.status_code, 200)
        self.assertEqual(xlsx_resp['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('.xlsx', xlsx_resp['Content-Disposition'])

    # ========================================================
    # 4. HTTP Views & Printable Certificate View
    # ========================================================

    def test_clearance_http_views(self):
        """Verifies clearance hub, detail, initiate, and printable certificate views render 200 OK."""
        self.client.force_login(self.admin)

        # 1. Dashboard View
        resp_dash = self.client.get(reverse('students:clearance_dashboard'))
        self.assertEqual(resp_dash.status_code, 200)

        # 2. Initiate View
        resp_init = self.client.get(reverse('students:clearance_initiate'))
        self.assertEqual(resp_init.status_code, 200)

        # Create clearance
        clearance = ClearanceService.initiate_clearance(
            school=self.school,
            student=self.student,
            withdrawal_reason=WithdrawalReason.TRANSFER,
            user=self.admin
        )

        # 3. Detail View
        resp_detail = self.client.get(reverse('students:clearance_detail', kwargs={'clearance_id': clearance.id}))
        self.assertEqual(resp_detail.status_code, 200)

        # 4. Certificate View before approval redirects
        resp_cert_blocked = self.client.get(reverse('students:clearance_certificate', kwargs={'clearance_id': clearance.id}))
        self.assertEqual(resp_cert_blocked.status_code, 302)

        # Approve and test certificate view
        ClearanceService.sign_department(self.school, clearance, 'library', True, user=self.librarian)
        ClearanceService.sign_department(self.school, clearance, 'finance', True, user=self.accountant)
        ClearanceService.sign_department(self.school, clearance, 'academic', True, user=self.admin)
        ClearanceService.sign_department(self.school, clearance, 'property', True, user=self.admin)
        ClearanceService.finalize_clearance(self.school, clearance, approved=True, user=self.admin)

        resp_cert = self.client.get(reverse('students:clearance_certificate', kwargs={'clearance_id': clearance.id}))
        self.assertEqual(resp_cert.status_code, 200)
        self.assertIn(b"Official Student Clearance", resp_cert.content)
        self.assertIn(b"Chala Tola Bekele", resp_cert.content)
