from django.test import TestCase
import datetime
import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject, TimetableSlot
from apps.students.models import StudentProfile, StudentStatus
from apps.teachers.models import TeacherProfile
from apps.assessments.models import StudentMark, AssessmentComponent, MarkStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.finance.models import StudentInvoice, Payment, InvoiceStatus, PaymentStatus
from apps.communication.models import Announcement
from apps.documents.models import SchoolDocument
from utils.file_security import validate_file_upload, sanitize_filename



class TenantIsolationSecurityTest(TestCase):
    def test_mandatory_tenant_isolation_school_a_vs_school_b(self):
        """
        CRITICAL RULE (Point 56):
        Create School A and School B.
        Test every major object type.
        If querying School A's context ever returns or mutates School B's data,
        the security boundary is broken and V1 cannot launch.
        """
        # 1. Provision School A and School B
        code_a = f"A{uuid.uuid4().hex[:6].lower()}"
        code_b = f"B{uuid.uuid4().hex[:6].lower()}"

        school_a = School.objects.create(name=f"School A {code_a}", code=code_a.upper(), subdomain=code_a)
        school_b = School.objects.create(name=f"School B {code_b}", code=code_b.upper(), subdomain=code_b)

        user_a = User.objects.create_user(username=f"admin_{code_a}", school=school_a, role=UserRole.SCHOOL_ADMIN)
        user_b = User.objects.create_user(username=f"admin_{code_b}", school=school_b, role=UserRole.SCHOOL_ADMIN)

        # 2. Populate School A data
        ay_a = AcademicYear.objects.create(school=school_a, name="2016 A", gregorian_start_date=datetime.date(2023,9,1), gregorian_end_date=datetime.date(2024,6,30))
        student_a = StudentProfile.objects.create(school=school_a, user=user_a, student_id=f"SA_{code_a}", first_name="Alice", last_name="A")
        inv_a = StudentInvoice.objects.create(school=school_a, student=student_a, academic_year=ay_a, invoice_number=f"INV-A-{code_a}", total_amount=Decimal('1000.00'), due_date=datetime.date(2025,1,1))
        ann_a = Announcement.objects.create(school=school_a, title="School A Announcement", content="Secrets of A", created_by=user_a)

        # 3. Populate School B data
        ay_b = AcademicYear.objects.create(school=school_b, name="2016 B", gregorian_start_date=datetime.date(2023,9,1), gregorian_end_date=datetime.date(2024,6,30))
        student_b = StudentProfile.objects.create(school=school_b, user=user_b, student_id=f"SB_{code_b}", first_name="Bob", last_name="B")
        inv_b = StudentInvoice.objects.create(school=school_b, student=student_b, academic_year=ay_b, invoice_number=f"INV-B-{code_b}", total_amount=Decimal('2000.00'), due_date=datetime.date(2025,1,1))
        ann_b = Announcement.objects.create(school=school_b, title="School B Announcement", content="Secrets of B", created_by=user_b)

        # 4. Mandatory Tenant Queries Verification
        # A) Students queryset for School A MUST NOT contain Student B
        students_for_a = StudentProfile.objects.for_school(school_a)
        assert student_a in students_for_a
        assert student_b not in students_for_a

        # B) Invoices queryset for School A MUST NOT contain Invoice B
        invoices_for_a = StudentInvoice.objects.for_school(school_a)
        assert inv_a in invoices_for_a
        assert inv_b not in invoices_for_a

        # C) Announcements queryset for School A MUST NOT contain Announcement B
        announcements_for_a = Announcement.objects.for_school(school_a)
        assert ann_a in announcements_for_a
        assert ann_b not in announcements_for_a

        # D) Direct Object IDOR Attack Test:
        # Attempting to query School B's invoice using School A's for_school filter MUST return empty
        idor_attempt = StudentInvoice.objects.for_school(school_a).filter(id=inv_b.id).first()
        assert idor_attempt is None, "SECURITY FAILURE: Cross-tenant IDOR returned School B invoice to School A context!"

        print(f"SUCCESS: Cross-Tenant Isolation Verified for {school_a.name} vs {school_b.name}")


    def test_file_upload_security_validation(self):
        """
        Test File Security rules (Point 58):
        Executable blocks, extension whitelisting, size limits.
        """
        class MockFile:
            def __init__(self, name, size):
                self.name = name
                self.size = size

        # Executable upload attempt -> Must raise ValidationError
        exe_file = MockFile("payload.exe", 1024)
        with self.assertRaises(ValidationError) as exc:
            validate_file_upload(exe_file)
        assert "is not permitted due to security policies" in str(exc.exception)

        # Shell script attempt -> Must raise ValidationError
        sh_file = MockFile("script.sh", 1024)
        with self.assertRaises(ValidationError) as exc:
            validate_file_upload(sh_file)
        assert "is not permitted due to security policies" in str(exc.exception)

        # Oversized PDF attempt -> Must raise ValidationError
        big_file = MockFile("large_doc.pdf", 15 * 1024 * 1024)
        with self.assertRaises(ValidationError) as exc:
            validate_file_upload(big_file)
        assert "exceeds maximum limit" in str(exc.exception)

        # Valid PDF file -> Must pass
        valid_pdf = MockFile("report.pdf", 500 * 1024)
        assert validate_file_upload(valid_pdf) is True

        # Filename Sanitization UUID test
        sanitized = sanitize_filename("../../etc/passwd_report.pdf")
        assert ".." not in sanitized
        assert "/" not in sanitized
        assert sanitized.endswith(".pdf")
