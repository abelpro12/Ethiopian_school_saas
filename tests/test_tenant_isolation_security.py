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
from rest_framework.test import APIClient



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

    def test_cross_tenant_api_header_spoofing_blocked(self):
        """
        REGRESSION TEST FOR DEFECT SEC-P0-01:
        Verifies that an authenticated user from School A (Teacher, Student, Parent, or School Admin)
        cannot supply an arbitrary X-School-ID header to query or alter School B records.
        """
        school_a = School.objects.create(name="Reg School A", code="REG-A", subdomain="reg-a")
        school_b = School.objects.create(name="Reg School B", code="REG-B", subdomain="reg-b")

        user_a_teacher = User.objects.create_user(username="reg_teacher_a", school=school_a, role=UserRole.TEACHER)
        user_a_admin = User.objects.create_user(username="reg_admin_a", school=school_a, role=UserRole.SCHOOL_ADMIN)
        user_b_student = User.objects.create_user(username="reg_stu_b", school=school_b, role=UserRole.STUDENT)
        student_b = StudentProfile.objects.create(
            school=school_b,
            user=user_b_student,
            student_id="REG-B-STU",
            first_name="Bob",
            last_name="Builder"
        )

        client = APIClient()

        # 1. Non-superadmin Teacher from School A attempts X-School-ID attack against School B
        client.force_authenticate(user=user_a_teacher)
        resp_spoof = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=str(school_b.id))
        self.assertEqual(resp_spoof.status_code, 403, "Forged X-School-ID must be denied with HTTP 403 Forbidden")

        # 2. Non-superadmin School Admin from School A attempts X-School-ID attack against School B
        client.force_authenticate(user=user_a_admin)
        resp_admin_spoof = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=str(school_b.id))
        self.assertEqual(resp_admin_spoof.status_code, 403, "School Admin cannot forge X-School-ID to access another school")

        # 3. Direct IDOR detail lookup of School B student by School A user returns 404
        resp_detail_idor = client.get(f'/api/v1/students/{student_b.id}/')
        self.assertEqual(resp_detail_idor.status_code, 404, "Direct object lookup of another school's record must return 404 Not Found")

        # 4. Legitimate same-school access succeeds cleanly
        student_a = StudentProfile.objects.create(
            school=school_a,
            user=User.objects.create_user(username="reg_stu_a", school=school_a, role=UserRole.STUDENT),
            student_id="REG-A-STU",
            first_name="Alice",
            last_name="Wonder"
        )
        resp_legit = client.get('/api/v1/students/')
        self.assertEqual(resp_legit.status_code, 200)
        results = resp_legit.data.get('results', resp_legit.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['student_id'], 'REG-A-STU')

        # 5. Super Admin legitimate cross-school access is preserved
        super_admin = User.objects.create_user(username="reg_super", role=UserRole.SUPER_ADMIN, is_superuser=True)
        client.force_authenticate(user=super_admin)
        resp_super = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=str(school_b.id))
        self.assertEqual(resp_super.status_code, 200)
        super_results = resp_super.data.get('results', resp_super.data)
        self.assertEqual(len(super_results), 1)
        self.assertEqual(super_results[0]['student_id'], 'REG-B-STU')

    def test_sec_p1_02_cross_tenant_foreign_key_substitution_blocked(self):
        """
        REGRESSION TEST FOR DEFECT SEC-P1-02:
        Verifies that users cannot create, update, or substitute foreign-key references
        pointing to another school's models (Grade, Stream, Section, Student, Enrollment, AssessmentComponent).
        Asserts that DRF rejects with 400 Bad Request, model-level validation rejects,
        and no cross-tenant records are inserted into the database.
        """
        import datetime
        from apps.academics.models import Grade, Stream, Section, AcademicYear, AcademicPeriod, Subject
        from apps.enrollment.models import StudentEnrollment
        from apps.assessments.models import AssessmentComponent, StudentMark
        from apps.attendance.models import AttendanceRecord

        school_a = School.objects.create(name="School A FK", code="SA-FK", subdomain="sa-fk")
        school_b = School.objects.create(name="School B FK", code="SB-FK", subdomain="sb-fk")

        # Academic fixtures for School A
        ay_a = AcademicYear.objects.create(
            school=school_a, name="2016 SA", ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 11),
            gregorian_end_date=datetime.date(2024, 7, 7)
        )
        period_a = AcademicPeriod.objects.create(
            school=school_a, academic_year=ay_a, name="Sem 1 SA",
            start_date=ay_a.gregorian_start_date, end_date=datetime.date(2024, 1, 30)
        )
        grade_a = Grade.objects.create(school=school_a, level=9, name="Grade 9 SA", stream_type='GEN')
        stream_a = Stream.objects.create(school=school_a, name="General SA", code='GEN')
        section_a = Section.objects.create(school=school_a, grade=grade_a, stream=stream_a, name="9-A")
        subject_a = Subject.objects.create(school=school_a, code="ENG-A", name="English", grade=grade_a, stream=stream_a)
        comp_a = AssessmentComponent.objects.create(
            school=school_a, academic_year=ay_a, period=period_a, subject=subject_a, name="Midterm", weight=30.0
        )
        user_a_teacher = User.objects.create_user(username="teacher_a_fk", school=school_a, role=UserRole.TEACHER)
        user_a_student = User.objects.create_user(username="stu_a_fk", school=school_a, role=UserRole.STUDENT)
        student_a = StudentProfile.objects.create(school=school_a, user=user_a_student, student_id="STU-A-01", first_name="Abebe")
        enrollment_a = StudentEnrollment.objects.create(
            school=school_a, academic_year=ay_a, student=student_a, grade=grade_a, stream=stream_a, section=section_a
        )

        # Academic fixtures for School B
        ay_b = AcademicYear.objects.create(
            school=school_b, name="2016 SB", ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 11),
            gregorian_end_date=datetime.date(2024, 7, 7)
        )
        period_b = AcademicPeriod.objects.create(
            school=school_b, academic_year=ay_b, name="Sem 1 SB",
            start_date=ay_b.gregorian_start_date, end_date=datetime.date(2024, 1, 30)
        )
        grade_b = Grade.objects.create(school=school_b, level=9, name="Grade 9 SB", stream_type='GEN')
        stream_b = Stream.objects.create(school=school_b, name="General SB", code='GEN')
        section_b = Section.objects.create(school=school_b, grade=grade_b, stream=stream_b, name="9-B")
        subject_b = Subject.objects.create(school=school_b, code="ENG-B", name="English", grade=grade_b, stream=stream_b)
        comp_b = AssessmentComponent.objects.create(
            school=school_b, academic_year=ay_b, period=period_b, subject=subject_b, name="Midterm", weight=30.0
        )
        user_b_student = User.objects.create_user(username="stu_b_fk", school=school_b, role=UserRole.STUDENT)
        student_b = StudentProfile.objects.create(school=school_b, user=user_b_student, student_id="STU-B-01", first_name="Biruk")
        enrollment_b = StudentEnrollment.objects.create(
            school=school_b, academic_year=ay_b, student=student_b, grade=grade_b, stream=stream_b, section=section_b
        )

        client = APIClient()
        client.force_authenticate(user=user_a_teacher)

        # 1. School A attempts to create a section referencing School B's Grade -> 400 Bad Request
        initial_sections_count = Section.objects.count()
        resp_sec_grade_b = client.post('/api/v1/sections/', {
            'name': 'Malicious-Sec',
            'grade': grade_b.id,
            'stream': stream_a.id,
            'capacity': 40
        })
        self.assertEqual(resp_sec_grade_b.status_code, 400, "Section referencing School B grade must be rejected with 400")
        self.assertEqual(Section.objects.count(), initial_sections_count, "No section record should be created")

        # 2. School A attempts to create a section referencing School B's Stream -> 400 Bad Request
        resp_sec_stream_b = client.post('/api/v1/sections/', {
            'name': 'Malicious-Sec-2',
            'grade': grade_a.id,
            'stream': stream_b.id,
            'capacity': 40
        })
        self.assertEqual(resp_sec_stream_b.status_code, 400, "Section referencing School B stream must be rejected with 400")
        self.assertEqual(Section.objects.count(), initial_sections_count, "No section record should be created")

        # 3. School A attempts to create attendance referencing School B's student -> 400 Bad Request
        initial_att_count = AttendanceRecord.objects.count()
        resp_att_stu_b = client.post('/api/v1/attendance/', {
            'section': section_a.id,
            'student': student_b.id,
            'date': '2024-01-15',
            'status': 'PRESENT'
        })
        self.assertEqual(resp_att_stu_b.status_code, 400, "Attendance referencing School B student must be rejected with 400")
        self.assertEqual(AttendanceRecord.objects.count(), initial_att_count, "No attendance record should be created")

        # 4. School A attempts to create attendance referencing School B's section -> 400 Bad Request
        resp_att_sec_b = client.post('/api/v1/attendance/', {
            'section': section_b.id,
            'student': student_a.id,
            'date': '2024-01-15',
            'status': 'PRESENT'
        })
        self.assertEqual(resp_att_sec_b.status_code, 400, "Attendance referencing School B section must be rejected with 400")
        self.assertEqual(AttendanceRecord.objects.count(), initial_att_count, "No attendance record should be created")

        # 5. School A attempts to submit marks referencing School B's enrollment -> 400 Bad Request
        initial_marks_count = StudentMark.objects.count()
        resp_mark_enr_b = client.post('/api/v1/marks/', {
            'enrollment': enrollment_b.id,
            'assessment_component': comp_a.id,
            'mark_value': '85.00',
            'status': 'SUBMITTED'
        })
        self.assertEqual(resp_mark_enr_b.status_code, 400, "Mark referencing School B enrollment must be rejected with 400")
        self.assertEqual(StudentMark.objects.count(), initial_marks_count, "No mark record should be created")

        # 6. School A attempts to submit marks referencing School B's assessment component -> 400 Bad Request
        resp_mark_comp_b = client.post('/api/v1/marks/', {
            'enrollment': enrollment_a.id,
            'assessment_component': comp_b.id,
            'mark_value': '85.00',
            'status': 'SUBMITTED'
        })
        self.assertEqual(resp_mark_comp_b.status_code, 400, "Mark referencing School B component must be rejected with 400")
        self.assertEqual(StudentMark.objects.count(), initial_marks_count, "No mark record should be created")

        # 7. School A attempts PATCH on existing section to substitute School B's Grade -> 400 Bad Request
        resp_patch_sec = client.patch(f'/api/v1/sections/{section_a.id}/', {
            'grade': grade_b.id
        })
        self.assertEqual(resp_patch_sec.status_code, 400, "Patch substituting foreign grade must return 400")
        section_a.refresh_from_db()
        self.assertEqual(section_a.grade_id, grade_a.id, "Section grade must remain unchanged")

        # 8. Legitimate same-school creation succeeds cleanly -> 201 Created
        resp_valid_sec = client.post('/api/v1/sections/', {
            'name': '9-Legit',
            'grade': grade_a.id,
            'stream': stream_a.id,
            'capacity': 40
        })
        self.assertEqual(resp_valid_sec.status_code, 201, "Legitimate same-school section creation must succeed")

        resp_valid_att = client.post('/api/v1/attendance/', {
            'section': section_a.id,
            'student': student_a.id,
            'date': '2024-01-15',
            'status': 'PRESENT'
        })
        self.assertEqual(resp_valid_att.status_code, 201, "Legitimate same-school attendance creation must succeed")

        resp_valid_mark = client.post('/api/v1/marks/', {
            'enrollment': enrollment_a.id,
            'assessment_component': comp_a.id,
            'mark_value': '92.00',
            'status': 'SUBMITTED'
        })
        self.assertEqual(resp_valid_mark.status_code, 201, "Legitimate same-school mark creation must succeed")

        # 9. Anonymous request cannot bypass validation
        client.logout()
        resp_anon = client.post('/api/v1/sections/', {
            'name': 'Anon-Sec',
            'grade': grade_a.id,
            'stream': stream_a.id
        })
        self.assertIn(resp_anon.status_code, [401, 403], "Unauthenticated section creation must be denied")

        # 10. Direct model-level save prevention (Defense in Depth)
        from django.core.exceptions import ValidationError as DjangoValidationError
        with self.assertRaises(DjangoValidationError):
            Section.objects.create(school=school_a, grade=grade_b, stream=stream_a, name="Illegal-ORM-Sec")
        with self.assertRaises(DjangoValidationError):
            AttendanceRecord.objects.create(school=school_a, section=section_a, student=student_b, date=datetime.date(2024, 1, 16))
        with self.assertRaises(DjangoValidationError):
            StudentMark.objects.create(school=school_a, enrollment=enrollment_b, assessment_component=comp_a, mark_value=75.0)

    def test_err_p2_04_malformed_x_school_id_handled_safely(self):
        """
        REGRESSION TEST FOR DEFECT ERR-P2-04:
        Verifies that malformed, nonexistent, or forged X-School-ID headers never crash
        the application with HTTP 500, whether the client is authenticated or anonymous.
        """
        import uuid
        school = School.objects.create(name="Middleware Test School", code="MW-01", subdomain="mw01")
        user_teacher = User.objects.create_user(username="mw_teacher", school=school, role=UserRole.TEACHER)
        user_super = User.objects.create_user(username="mw_super", role=UserRole.SUPER_ADMIN, is_superuser=True)

        client = APIClient()

        malformed_headers = [
            "not-a-valid-uuid",
            "12345",
            "../../etc/passwd",
            "null",
            "undefined",
            "invalid-hex-chars-zzzzzzzzzzzzzzzzzzzzzzzzzz"
        ]

        # 1. Unauthenticated requests with malformed headers never crash with 500
        for bad_header in malformed_headers:
            resp = client.get('/api/v1/schools/', HTTP_X_SCHOOL_ID=bad_header)
            self.assertEqual(resp.status_code, 400, f"Malformed header '{bad_header}' must return 400 Bad Request, never 500")
            self.assertNotEqual(resp.status_code, 500)

        # 2. Authenticated non-superadmin with malformed headers never crash with 500
        client.force_authenticate(user=user_teacher)
        for bad_header in malformed_headers:
            resp = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=bad_header)
            self.assertEqual(resp.status_code, 400, f"Malformed header '{bad_header}' must return 400 Bad Request, never 500")
            self.assertNotEqual(resp.status_code, 500)

        # 3. Valid UUID but nonexistent school ID:
        nonexistent_uuid = str(uuid.uuid4())
        # Unauthenticated:
        client.logout()
        resp_nonexist_anon = client.get('/api/v1/schools/', HTTP_X_SCHOOL_ID=nonexistent_uuid)
        self.assertNotEqual(resp_nonexist_anon.status_code, 500, "Nonexistent UUID must not generate 500")

        # Authenticated non-superadmin sending another school UUID (even nonexistent):
        client.force_authenticate(user=user_teacher)
        resp_unauth_sel = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=nonexistent_uuid)
        self.assertEqual(resp_unauth_sel.status_code, 403, "Non-matching school selection must be denied with 403")
        self.assertNotEqual(resp_unauth_sel.status_code, 500)

        # Super Admin with nonexistent UUID:
        client.force_authenticate(user=user_super)
        resp_super_nonexist = client.get('/api/v1/schools/', HTTP_X_SCHOOL_ID=nonexistent_uuid)
        self.assertNotEqual(resp_super_nonexist.status_code, 500, "Super admin with nonexistent school ID must not 500")

        # 4. Legitimate request with matching header or no header continues to work
        client.force_authenticate(user=user_teacher)
        resp_legit_header = client.get('/api/v1/students/', HTTP_X_SCHOOL_ID=str(school.id))
        self.assertEqual(resp_legit_header.status_code, 200, "Legitimate school header must return 200")

        resp_no_header = client.get('/api/v1/students/')
        self.assertEqual(resp_no_header.status_code, 200, "Missing header must use authenticated user's school and return 200")


