import datetime
from django.test import TestCase, Client
from django.urls import reverse

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, PeriodType, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment
from apps.assessments.models import (
    GradingScale, GradingScaleType, GradingScaleRule,
    AssessmentComponent, StudentMark, MarkStatus,
    AcademicIntervention, InterventionType, InterventionStatus
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.reports.models import DocumentVerification, DocumentType, DocumentStatus
from utils.pdf_utils import generate_report_card_pdf, generate_transcript_pdf


class ReportCardsAndTranscriptsSystemTests(TestCase):
    """
    Unit and integration tests for Report Cards & Transcripts System:
    - Flexible grading scale evaluation
    - Below-average score detection & warning flags (<60%)
    - Real student attendance aggregation
    - Academic intervention recording & display
    - Multi-year High School Transcript (Grades 9-12) with GPA points and cumulative CGPA
    - Authentic DocumentVerification QR token generation & public endpoint verification
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Entoto Model Secondary School",
            code="ENT",
            calendar_preference="ETHIOPIAN"
        )

        # Admin user
        self.admin = User.objects.create_superuser(
            username="admin_entoto",
            email="admin@entoto.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        # Teacher user
        self.teacher_user = User.objects.create_user(
            username="teacher_alemu",
            email="alemu@entoto.edu.et",
            password="teacherpass123",
            role=UserRole.TEACHER,
            first_name="Alemu",
            last_name="Bekele",
            school=self.school
        )

        # Academic Year & Period
        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2018 E.C.",
            ethiopian_year=2018,
            gregorian_start_date=datetime.date(2025, 9, 11),
            gregorian_end_date=datetime.date(2026, 7, 7),
            is_active=True
        )
        self.semester1 = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.ay,
            name="Semester 1",
            period_type=PeriodType.SEMESTER,
            start_date=datetime.date(2025, 9, 11),
            end_date=datetime.date(2026, 1, 30),
            is_current=True
        )

        # Stream, Grade & Section
        self.stream = Stream.objects.create(school=self.school, name="Natural Science", code="NAT")
        self.grade = Grade.objects.create(school=self.school, name="10", level=10)
        self.section = Section.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="A"
        )

        # Student User & Profile
        self.student_user = User.objects.create_user(
            username="student_kebede",
            email="kebede@entoto.edu.et",
            password="studentpass123",
            role=UserRole.STUDENT,
            first_name="Kebede",
            last_name="Tadesse",
            school=self.school
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            student_id="ENT-2018-0042",
            first_name="Kebede",
            last_name="Tadesse",
            gender="MALE",
            date_of_birth=datetime.date(2009, 4, 15)
        )

        # Student Enrollment
        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.ay,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            enrollment_date=datetime.date(2025, 9, 12)
        )

        # Grading Scale setup
        self.scale = GradingScale.objects.create(
            school=self.school,
            name="Entoto Secondary MOE Scale",
            scale_type=GradingScaleType.NUMERICAL,
            is_default=True,
            min_passing_mark=50.0,
            below_average_threshold=60.0,
            high_performance_threshold=90.0
        )
        rules = [
            ('A+', 90.0, 100.0, 4.0, 'Outstanding', True, 1),
            ('A', 85.0, 89.99, 4.0, 'Excellent', True, 2),
            ('B+', 80.0, 84.99, 3.5, 'Very Good', True, 3),
            ('B', 75.0, 79.99, 3.0, 'Good', True, 4),
            ('C+', 65.0, 74.99, 2.5, 'Satisfactory', True, 5),
            ('C', 50.0, 64.99, 2.0, 'Passing', True, 6),
            ('D', 40.0, 49.99, 1.0, 'Needs Improvement', False, 7),
            ('F', 0.0, 39.99, 0.0, 'Failing', False, 8),
        ]
        for letter, min_s, max_s, gpa, desc, is_p, ord_idx in rules:
            GradingScaleRule.objects.create(
                school=self.school,
                scale=self.scale,
                letter_grade=letter,
                min_score=min_s,
                max_score=max_s,
                gpa_point=gpa,
                description=desc,
                is_passing=is_p,
                sort_order=ord_idx
            )

        # Subjects
        self.math = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="Mathematics", code="MATH10")
        self.physics = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="Physics", code="PHYS10")
        self.english = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="English Language", code="ENG10")

    def test_generate_report_card_pdf_direct_utility(self):
        """Verifies generate_report_card_pdf creates a valid PDF byte stream with modern metadata."""
        results = [
            {
                'subject_name': 'Mathematics',
                'continuous_assessment': 28.0,
                'midterm': 27.0,
                'final': 38.0,
                'total': 93.0,
                'letter_grade': 'A+',
                'gpa': 4.0,
                'tier': 'HIGH_PERFORMANCE',
                'has_intervention': False,
                'subject_rank': 1
            },
            {
                'subject_name': 'Physics',
                'continuous_assessment': 14.0,
                'midterm': 15.0,
                'final': 24.0,
                'total': 53.0,
                'letter_grade': 'C',
                'gpa': 2.0,
                'tier': 'BELOW_AVERAGE',
                'has_intervention': True,
                'subject_rank': 25
            }
        ]
        att_info = {'present': 88, 'absent': 2, 'late': 1, 'excused': 1, 'total': 92, 'rate': 96.7}
        interventions = [{
            'subject_name': 'Physics',
            'trigger_score': 53.0,
            'threshold': 60.0,
            'action_plan': 'Afternoon physics remedial tutorial on mechanics',
            'assigned_teacher': 'Alemu Bekele',
            'status': 'Tutorial Scheduled'
        }]

        pdf_bytes = generate_report_card_pdf(
            school_info={'name': self.school.name, 'phone': '+251911223344', 'address': 'Addis Ababa'},
            student_info={
                'full_name': self.student.full_name,
                'student_id': self.student.student_id,
                'grade_section': 'Grade 10 - A',
                'academic_year': '2018 E.C.',
                'semester': 'Semester 1',
                'stream': 'Natural Science',
                'rank': '1st of 40',
                'doc_number': 'RC-ENT-0042'
            },
            results_info=results,
            verification_url="http://localhost:8000/verify/sample-token/",
            attendance_info=att_info,
            interventions_info=interventions,
            grading_scale_info=['A+ (90-100% / 4.0)', 'C (50-64% / 2.0)']
        )

        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_generate_transcript_pdf_direct_utility(self):
        """Verifies generate_transcript_pdf creates a multi-year transcript with CGPA and signatures."""
        grades_data = [
            {
                'grade_level': 9,
                'grade_name': 'Grade 9',
                'academic_year': '2017 E.C.',
                'subjects': [
                    {'name': 'Mathematics', 'sem1': 88.0, 'sem2': 92.0, 'avg': 90.0, 'letter': 'A+', 'gpa': 4.0},
                    {'name': 'Physics', 'sem1': 82.0, 'sem2': 86.0, 'avg': 84.0, 'letter': 'B+', 'gpa': 3.5},
                ]
            },
            {
                'grade_level': 10,
                'grade_name': 'Grade 10',
                'academic_year': '2018 E.C.',
                'subjects': [
                    {'name': 'Mathematics', 'sem1': 92.0, 'sem2': 94.0, 'avg': 93.0, 'letter': 'A+', 'gpa': 4.0},
                    {'name': 'Physics', 'sem1': 85.0, 'sem2': 89.0, 'avg': 87.0, 'letter': 'A', 'gpa': 4.0},
                ]
            }
        ]

        pdf_bytes = generate_transcript_pdf(
            school_info={'name': self.school.name},
            student_info={
                'full_name': self.student.full_name,
                'student_id': self.student.student_id,
                'doc_number': 'TRANS-ENT-0042',
                'stream': 'Natural Science'
            },
            grades_data=grades_data,
            verification_url="http://localhost:8000/verify/sample-trans-token/"
        )

        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_download_report_card_pdf_view_authenticated(self):
        """Verifies the HTTP endpoint download_report_card_pdf_view streams a production PDF."""
        self.client.force_login(self.admin)

        # Create assessment component & mark for math
        comp = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.ay,
            period=self.semester1,
            subject=self.math,
            name="Final Exam",
            weight=100.0,
            max_marks=100.0
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=comp,
            mark_value=92.50,
            status=MarkStatus.APPROVED
        )

        url = reverse('download_report_card_pdf', kwargs={'student_id': self.student.id, 'period_id': str(self.semester1.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn('attachment', response['Content-Disposition'])

        # Check DocumentVerification record was created
        doc = DocumentVerification.objects.filter(school=self.school, document_type=DocumentType.REPORT_CARD).first()
        self.assertIsNotNone(doc)
        self.assertTrue(doc.is_valid)
        self.assertIn('ENT', doc.doc_number)

    def test_report_card_with_attendance_and_below_average_intervention(self):
        """Verifies that actual attendance and below-average intervention records are integrated."""
        self.client.force_login(self.admin)

        # Record Attendance: 2 present, 1 absent, 1 late
        AttendanceRecord.objects.create(school=self.school, section=self.section, student=self.student, date=datetime.date(2025, 10, 1), status=AttendanceStatus.PRESENT)
        AttendanceRecord.objects.create(school=self.school, section=self.section, student=self.student, date=datetime.date(2025, 10, 2), status=AttendanceStatus.PRESENT)
        AttendanceRecord.objects.create(school=self.school, section=self.section, student=self.student, date=datetime.date(2025, 10, 3), status=AttendanceStatus.ABSENT, reason="Sick")
        AttendanceRecord.objects.create(school=self.school, section=self.section, student=self.student, date=datetime.date(2025, 10, 4), status=AttendanceStatus.LATE, reason="Traffic")

        # Record Below-Average Mark in Physics (52.0%)
        comp_phys = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.ay,
            period=self.semester1,
            subject=self.physics,
            name="Midterm Exam",
            weight=100.0,
            max_marks=100.0
        )
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=comp_phys,
            mark_value=52.00,
            status=MarkStatus.APPROVED
        )

        # Create active AcademicIntervention
        AcademicIntervention.objects.create(
            school=self.school,
            student=self.student,
            enrollment=self.enrollment,
            subject=self.physics,
            assessment_component=comp_phys,
            academic_year=self.ay,
            period=self.semester1,
            trigger_score=52.00,
            threshold_applied=60.00,
            intervention_type=InterventionType.TUTORIAL,
            status=InterventionStatus.IN_PROGRESS,
            action_plan="Weekly remedial tutorial and reassessment on electrostatics",
            assigned_teacher=self.teacher_user,
            created_by=self.admin
        )

        url = reverse('download_report_card_pdf', kwargs={'student_id': self.student.id, 'period_id': str(self.semester1.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertTrue(len(response.content) > 1000)

    def test_download_transcript_pdf_view_authenticated(self):
        """Verifies the HTTP endpoint download_transcript_pdf_view generates official multi-year transcript."""
        self.client.force_login(self.admin)

        url = reverse('download_transcript_pdf', kwargs={'student_id': self.student.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertIn('Transcript', response['Content-Disposition'])

        # Check DocumentVerification record was created for transcript
        doc = DocumentVerification.objects.filter(school=self.school, document_type=DocumentType.TRANSCRIPT).first()
        self.assertIsNotNone(doc)
        self.assertTrue(doc.is_valid)

    def test_document_verification_public_endpoint(self):
        """Verifies public QR scan verification endpoint validates genuine report card tokens."""
        doc = DocumentVerification.objects.create(
            school=self.school,
            document_type=DocumentType.REPORT_CARD,
            doc_number="RC-ENT-0042-TEST",
            metadata_json={'student_name': self.student.full_name, 'average': 88.5, 'gpa': 3.8},
            is_valid=True
        )

        # Public scan without login
        resp = self.client.get(f"/verify/{doc.verification_token}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Authentic Document", resp.content)
        self.assertIn(self.school.name.encode(), resp.content)
        self.assertIn(b"VERIFIED", resp.content)
