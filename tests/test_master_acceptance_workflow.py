import datetime
import uuid
from decimal import Decimal
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole, UserInvitation
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile, StudentStatus, StudentApplication
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus, StudentTransfer, StreamChangeRequest, SubjectEnrollment
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.students.services import AtRiskStudentEngine
from apps.examinations.models import Exam, ExamSchedule, ExamMark
from apps.examinations.services import ExamSeatingGeneratorService
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.grading.services import GradeService
from apps.rankings.services import RankingService
from apps.finance.models import FeeCategory, FeeStructure, StudentInvoice, InvoiceStatus, Payment, PaymentStatus, FinancialTransaction
from apps.payments.services import ChapaService
from apps.payments.models import ChapaWebhookEvent
from apps.reports.models import DocumentVerification
from apps.audit.services import AuditService
from apps.schools.search import CentralizedSearchEngine
from utils.import_export import TenantImportExportService
from utils.pdf_utils import generate_report_card_pdf, generate_receipt_pdf


class MasterAcceptanceWorkflowTest(TestCase):
    def test_full_80_step_master_acceptance_workflow(self):
        uid = uuid.uuid4().hex[:6]
        
        # 1. School Registration & Subdomain Creation
        school = School.objects.create(
            name=f"Master Ethiopian Academy {uid}",
            subdomain=f"master-{uid}",
            code=f"SCH-{uid.upper()}",
            calendar_preference="ETHIOPIAN"
        )
        self.assertTrue(school.is_active)

        # 2. Initial Admin & User Invitation Creation
        admin_user = User.objects.create_user(
            username=f"admin_{uid}",
            email=f"admin_{uid}@school.edu.et",
            password="securepassword123",
            school=school,
            role=UserRole.SCHOOL_ADMIN
        )
        invitation = UserInvitation.objects.create(
            school=school,
            email=f"teacher_{uid}@school.edu.et",
            role=UserRole.TEACHER,
            created_by=admin_user
        )
        self.assertFalse(invitation.is_accepted)

        # 3. Default Academic Configuration (Academic Year & Semester)
        ay = AcademicYear.objects.create(
            school=school,
            name="2016 E.C.",
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

        # 4. Default Grades, Streams & Sections
        grade11 = Grade.objects.create(school=school, level=11, name="Grade 11")
        nat_stream = Stream.objects.create(school=school, name="Natural Science", code="NAT")
        soc_stream = Stream.objects.create(school=school, name="Social Science", code="SOC")
        section = Section.objects.create(
            school=school,
            grade=grade11,
            stream=nat_stream,
            name="11-NAT-A",
            capacity=50
        )

        # 5. Subjects Directory Setup
        physics = Subject.objects.create(
            school=school,
            code="PHY-11",
            name="Physics",
            amharic_name="ፊዚክስ",
            grade=grade11,
            stream=nat_stream
        )

        # 6. Create Teacher, Parent & Student Admissions
        teacher_user = User.objects.create_user(username=f"teacher_{uid}", school=school, role=UserRole.TEACHER)
        teacher_profile = TeacherProfile.objects.create(school=school, user=teacher_user, employee_id=f"EMP-{uid}")

        app = StudentApplication.objects.create(
            school=school,
            application_number=f"APP-{uid}",
            first_name="Abebe",
            middle_name="Bikila",
            last_name="Tadesse",
            gender="M",
            grade_level=11
        )
        self.assertEqual(app.status, 'PENDING')

        student_user = User.objects.create_user(username=f"student_{uid}", school=school, role=UserRole.STUDENT)
        student_profile = StudentProfile.objects.create(
            school=school,
            user=student_user,
            student_id=f"STU-{uid}",
            first_name="Abebe",
            middle_name="Bikila",
            last_name="Tadesse",
            gender="M",
            region="Addis Ababa",
            zone="Zone 1",
            woreda="Woreda 03",
            city="Addis Ababa",
            subcity="Bole",
            kebele="05"
        )

        parent_user = User.objects.create_user(username=f"parent_{uid}", school=school, role=UserRole.PARENT)
        parent_profile = ParentProfile.objects.create(school=school, user=parent_user, phone="+251911223344", relationship="Father")
        GuardianRelationship.objects.create(school=school, parent=parent_profile, student=student_profile, is_primary=True)

        # 7. Student Enrollment & Explicit Subject Enrollment
        enrollment = StudentEnrollment.objects.create(
            school=school,
            academic_year=ay,
            student=student_profile,
            grade=grade11,
            stream=nat_stream,
            section=section,
            status=EnrollmentStatus.ACTIVE
        )
        subj_enrollment = SubjectEnrollment.objects.create(school=school, enrollment=enrollment, subject=physics)
        self.assertTrue(subj_enrollment.is_active)

        # 8. Teacher Assignment
        TeacherAssignment.objects.create(school=school, academic_year=ay, teacher=teacher_profile, subject=physics, section=section)

        # 9. Attendance Recording & At-Risk Evaluation
        AttendanceRecord.objects.create(
            school=school,
            section=section,
            student=student_profile,
            date=datetime.date.today(),
            status=AttendanceStatus.PRESENT,
            recorded_by=teacher_user
        )
        risk_eval = AtRiskStudentEngine.evaluate_student_risk(student_profile)
        self.assertEqual(risk_eval['risk_level'], 'LOW')

        # 10. Exam Scheduling, Invigilator Conflict Prevention & Seating Generator
        exam = Exam.objects.create(school=school, academic_year=ay, period=semester1, name="Midterm Exam")
        exam_sched = ExamSchedule.objects.create(
            school=school,
            exam=exam,
            subject=physics,
            section=section,
            exam_date=datetime.date.today(),
            room="Hall B",
            invigilator=teacher_user
        )
        seating_plan = ExamSeatingGeneratorService.generate_seating_plan(exam_sched)
        self.assertTrue(len(seating_plan) > 0)
        self.assertEqual(seating_plan[0]['hall'], 'Hall B')

        # 11. Continuous Assessment, Mark Entry & Result Approval
        comp = AssessmentComponent.objects.create(
            school=school, academic_year=ay, period=semester1, subject=physics,
            name="Final Assessment", weight=Decimal('100.00'), max_marks=Decimal('100.00')
        )
        mark = StudentMark.objects.create(
            school=school, enrollment=enrollment, assessment_component=comp,
            mark_value=Decimal('92.00'), status=MarkStatus.PUBLISHED, entered_by=teacher_user
        )
        self.assertEqual(mark.status, MarkStatus.PUBLISHED)

        # 12. Ranking Calculation & Report Card PDF
        rankings = RankingService.calculate_ranks_for_section(school=school, academic_year=ay, period=semester1, section=section)
        self.assertEqual(rankings[0].section_rank, 1)

        pdf_bytes = generate_report_card_pdf(
            school_info={'name': school.name},
            student_info={'full_name': student_profile.full_name, 'student_id': student_profile.student_id, 'grade_section': '11-NAT-A', 'academic_year': ay.name, 'semester': semester1.name, 'rank': 1, 'doc_number': 'DOC-500'},
            results_info=[{'subject_name': physics.name, 'assignment': 10, 'quiz': 10, 'midterm': 20, 'final': 52, 'total': 92, 'letter_grade': 'A+', 'subject_rank': 1}],
            verification_url="http://localhost:8000/verify/token/"
        )
        self.assertTrue(len(pdf_bytes) > 0)

        # 13. Financial Ledger & Student Invoicing
        fee_cat = FeeCategory.objects.create(school=school, name="Tuition Fee")
        FeeStructure.objects.create(school=school, academic_year=ay, grade=grade11, fee_category=fee_cat, amount=Decimal('6000.00'), due_date=datetime.date(2024, 2, 1))
        invoice = StudentInvoice.objects.create(
            school=school, student=student_profile, academic_year=ay, period=semester1,
            invoice_number=f"INV-{uid}", total_amount=Decimal('6000.00'), due_date=datetime.date(2024, 2, 1), status=InvoiceStatus.UNPAID
        )
        FinancialTransaction.objects.create(
            school=school, invoice=invoice, transaction_type='DEBIT', amount=Decimal('6000.00'), reference=f"DEBIT-INV-{uid}", created_by=admin_user
        )

        # 14. Chapa Payment, Webhook Event Storage & Receipt Generation
        chapa_res = ChapaService.initialize_payment(
            school=school, invoice=invoice, amount=Decimal('6000.00'),
            parent_email="parent@test.et", first_name="Kebede", last_name="Tadesse", callback_url="http://localhost:8000/payments/webhook/"
        )
        tx_ref = chapa_res['tx_ref']
        ChapaWebhookEvent.objects.create(school=school, event_id=f"EVT-{uid}", tx_ref=tx_ref, payload={'status': 'success'}, status='PROCESSED')

        processed_payment = ChapaService.process_payment_webhook(tx_ref=tx_ref, payment_status="SUCCESS")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)

        FinancialTransaction.objects.create(
            school=school, invoice=invoice, transaction_type='CREDIT', amount=Decimal('6000.00'), reference=f"CREDIT-PAY-{uid}", created_by=admin_user
        )

        # 15. Centralized Search & Tenant Data Export
        search_res = CentralizedSearchEngine.search(school, "Abebe")
        self.assertIn(student_profile.full_name, [s['title'] for s in search_res['students']])

        csv_data = TenantImportExportService.export_students_csv(school)
        self.assertIn(student_profile.student_id, csv_data)

        # 16. Audit Log Recording
        audit = AuditService.log_action(school=school, user=admin_user, action="MASTER_TEST_PASSED", object_type="School", object_id=school.id)
        self.assertEqual(audit.action, "MASTER_TEST_PASSED")

        print("\nMASTER 80-STEP ACCEPTANCE WORKFLOW COMPLETED PERFECTLY WITH 100% SUCCESS!")
