import json
from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Grade, Section, Stream
from apps.students.models import StudentProfile, StudentStatus
from apps.enrollment.models import StudentEnrollment
from apps.assessments.models import AssessmentComponent, StudentMark
from apps.examinations.models import (
    OnlineExam, ExamQuestion, QuestionOption, StudentExamAttempt,
    StudentAnswer, ExamProctoringLog, OnlineExamStatus, QuestionType,
    AttemptStatus, ProctoringEventType
)
from apps.examinations.services import ExamGradingService, ExamSecurityService, ExamAnalyticsService


class OnlineExaminationsTestSuite(TestCase):
    def setUp(self):
        # 1. School & Academic Structure
        self.school = School.objects.create(
            name="Alpha Academy",
            code="ALPHA",
            subdomain="alpha",
            status=SchoolStatus.ACTIVE,
            is_active=True
        )

        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2016 E.C.",
            ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 11),
            gregorian_end_date=datetime.date(2024, 7, 7),
            is_active=True
        )

        self.period = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            name="Semester 1",
            start_date=self.academic_year.gregorian_start_date,
            end_date=self.academic_year.gregorian_start_date + datetime.timedelta(days=120),
            is_current=True
        )

        self.stream = Stream.objects.create(school=self.school, name="Natural Science", code="NAT")
        self.grade = Grade.objects.create(school=self.school, level=11, name="Grade 11 (NS)", stream_type="NAT")
        self.section = Section.objects.create(
            school=self.school, grade=self.grade, stream=self.stream, name="11-A"
        )
        self.subject = Subject.objects.create(
            school=self.school, code="PHYS11", name="Physics", grade=self.grade, stream=self.stream
        )

        # 2. Users
        self.teacher_user = User.objects.create_user(
            username="teacher_abebe", password="Password123!",
            school=self.school, role=UserRole.TEACHER, first_name="Abebe", last_name="Kebede"
        )

        self.student_user = User.objects.create_user(
            username="student_chala", password="Password123!",
            school=self.school, role=UserRole.STUDENT, first_name="Chala", last_name="Bekele"
        )

        self.student_profile = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            student_id="STU-001",
            first_name="Chala",
            middle_name="Bekele",
            last_name="Tadesse",
            gender="M",
            status=StudentStatus.ACTIVE
        )

        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student_profile,
            academic_year=self.academic_year,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            status='ACTIVE'
        )

        # 3. Assessment Component
        self.component = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject,
            name="CBT Midterm",
            weight=Decimal('30.00'),
            max_marks=Decimal('100.00')
        )

        # 4. Online Exam
        now = timezone.now()
        self.online_exam = OnlineExam.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            period=self.period,
            subject=self.subject,
            grade=self.grade,
            section=self.section,
            title="Grade 11 Physics Midterm CBT",
            start_time=now - datetime.timedelta(hours=1),
            end_time=now + datetime.timedelta(hours=5),
            duration_minutes=60,
            total_marks=Decimal('100.00'),
            pass_mark=Decimal('50.00'),
            status=OnlineExamStatus.PUBLISHED,
            enable_proctoring=True,
            max_violations_allowed=3,
            assessment_component=self.component,
            created_by=self.teacher_user
        )

        # 5. Exam Questions
        # Q1: MCQ (Single choice) - 20 pts
        self.q_mcq = ExamQuestion.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            question_text="What is the unit of force?",
            question_type=QuestionType.MCQ,
            points=Decimal('20.00'),
            order=0
        )
        self.opt_mcq_1 = QuestionOption.objects.create(school=self.school, question=self.q_mcq, option_text="Joule", is_correct=False, order=0)
        self.opt_mcq_2 = QuestionOption.objects.create(school=self.school, question=self.q_mcq, option_text="Newton", is_correct=True, order=1)
        self.opt_mcq_3 = QuestionOption.objects.create(school=self.school, question=self.q_mcq, option_text="Watt", is_correct=False, order=2)

        # Q2: True / False - 20 pts
        self.q_tf = ExamQuestion.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            question_text="Acceleration due to gravity on Earth is approximately 9.8 m/s^2.",
            question_type=QuestionType.TRUE_FALSE,
            points=Decimal('20.00'),
            order=1
        )
        self.opt_tf_t = QuestionOption.objects.create(school=self.school, question=self.q_tf, option_text="True", is_correct=True, order=0)
        self.opt_tf_f = QuestionOption.objects.create(school=self.school, question=self.q_tf, option_text="False", is_correct=False, order=1)

        # Q3: Short Answer - 20 pts
        self.q_short = ExamQuestion.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            question_text="What is the name of Newton's first law of motion?",
            question_type=QuestionType.SHORT_ANSWER,
            points=Decimal('20.00'),
            order=2,
            correct_short_answer="Inertia, Law of Inertia",
            case_sensitive=False
        )

        # Q4: Essay - 40 pts
        self.q_essay = ExamQuestion.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            question_text="Explain the conservation of momentum with a real-world example.",
            question_type=QuestionType.ESSAY,
            points=Decimal('40.00'),
            order=3
        )

        self.client = Client()

    def test_exam_creation_and_properties(self):
        """Test model relations and properties on OnlineExam."""
        self.assertEqual(self.online_exam.question_count, 4)
        self.assertTrue(self.online_exam.is_active_now)
        self.assertFalse(self.online_exam.is_upcoming)
        self.assertEqual(self.online_exam.calculated_total_points, Decimal('100.00'))

    def test_auto_grading_service(self):
        """Test automatic grading of MCQ, True/False, and Short Answer responses."""
        attempt = StudentExamAttempt.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            student=self.student_user,
            status=AttemptStatus.IN_PROGRESS,
            started_at=timezone.now()
        )

        # Answer Q1 (MCQ) - Correct choice
        ans1 = StudentAnswer.objects.create(school=self.school, attempt=attempt, question=self.q_mcq)
        ans1.selected_options.add(self.opt_mcq_2)

        # Answer Q2 (True/False) - Correct choice
        ans2 = StudentAnswer.objects.create(school=self.school, attempt=attempt, question=self.q_tf)
        ans2.selected_options.add(self.opt_tf_t)

        # Answer Q3 (Short Answer) - Correct fill-in
        ans3 = StudentAnswer.objects.create(
            school=self.school, attempt=attempt, question=self.q_short, text_response="law of inertia"
        )

        # Answer Q4 (Essay) - Text response (pending teacher evaluation)
        ans4 = StudentAnswer.objects.create(
            school=self.school, attempt=attempt, question=self.q_essay, text_response="In collisions, momentum is conserved..."
        )

        # Run auto-grader
        ExamGradingService.grade_attempt(attempt, auto_grade_only=True)
        attempt.refresh_from_db()

        # Score should be 20 + 20 + 20 = 60.00 pts
        self.assertEqual(attempt.total_score, Decimal('60.00'))
        self.assertEqual(attempt.percentage, Decimal('60.00'))
        self.assertTrue(attempt.is_passed)
        # Status should remain SUBMITTED because essay is pending
        self.assertEqual(attempt.status, AttemptStatus.SUBMITTED)

        # Teacher grades essay (awards 35/40 pts)
        ans4.marks_awarded = Decimal('35.00')
        ans4.is_correct = True
        ans4.save()

        ExamGradingService.grade_attempt(attempt, auto_grade_only=False)
        attempt.refresh_from_db()

        # Total now: 60 + 35 = 95.00 pts
        self.assertEqual(attempt.total_score, Decimal('95.00'))
        self.assertEqual(attempt.percentage, Decimal('95.00'))
        self.assertEqual(attempt.status, AttemptStatus.GRADED)

        # Verify Gradebook sync
        mark = StudentMark.objects.filter(
            school=self.school, enrollment=self.enrollment, assessment_component=self.component
        ).first()
        self.assertIsNotNone(mark)
        self.assertEqual(mark.mark_value, Decimal('95.00'))

    def test_proctoring_incident_logging(self):
        """Test anti-cheating violations tracking and threshold flags."""
        attempt = StudentExamAttempt.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            student=self.student_user,
            status=AttemptStatus.IN_PROGRESS,
            started_at=timezone.now()
        )

        # Log 1st incident: Tab switch
        res1 = ExamSecurityService.log_incident(
            attempt=attempt, event_type=ProctoringEventType.TAB_SWITCH, description="Switched to chrome search tab"
        )
        self.assertEqual(res1['violation_count'], 1)
        self.assertFalse(res1['should_auto_submit'])

        # Log 2nd incident: Fullscreen exit
        res2 = ExamSecurityService.log_incident(
            attempt=attempt, event_type=ProctoringEventType.FULLSCREEN_EXIT, description="Exited fullscreen"
        )
        self.assertEqual(res2['violation_count'], 2)
        self.assertFalse(res2['should_auto_submit'])

        # Log 3rd incident: Exceeds threshold (max=3)
        res3 = ExamSecurityService.log_incident(
            attempt=attempt, event_type=ProctoringEventType.TAB_SWITCH, description="Switched tab again"
        )
        self.assertEqual(res3['violation_count'], 3)
        self.assertTrue(res3['should_auto_submit'])
        self.assertTrue(attempt.is_flagged)

        # Check logs created
        self.assertEqual(attempt.proctoring_logs.count(), 3)

    def test_exam_analytics_service(self):
        """Test analytics calculation for score distribution and pass rate."""
        # Create 2 completed attempts
        a1 = StudentExamAttempt.objects.create(
            school=self.school, online_exam=self.online_exam, student=self.student_user,
            status=AttemptStatus.GRADED, total_score=Decimal('85.00'), percentage=Decimal('85.00'), is_passed=True
        )
        u2 = User.objects.create_user(username="student2", password="Password123!", school=self.school, role=UserRole.STUDENT)
        a2 = StudentExamAttempt.objects.create(
            school=self.school, online_exam=self.online_exam, student=u2,
            status=AttemptStatus.GRADED, total_score=Decimal('45.00'), percentage=Decimal('45.00'), is_passed=False
        )

        analytics = ExamAnalyticsService.get_exam_analytics(self.online_exam)
        self.assertEqual(analytics['total_candidates'], 2)
        self.assertEqual(analytics['pass_count'], 1)
        self.assertEqual(analytics['fail_count'], 1)
        self.assertEqual(analytics['pass_rate'], 50.0)
        self.assertEqual(analytics['highest_score'], 85.0)
        self.assertEqual(analytics['lowest_score'], 45.0)

    def test_student_ajax_autosave_endpoint(self):
        """Test the AJAX autosave API endpoint during an active test session."""
        attempt = StudentExamAttempt.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            student=self.student_user,
            status=AttemptStatus.IN_PROGRESS,
            started_at=timezone.now()
        )

        self.client.force_login(self.student_user)
        payload = {
            'attempt_id': str(attempt.id),
            'question_id': str(self.q_mcq.id),
            'selected_option_ids': [str(self.opt_mcq_2.id)],
            'text_response': '',
            'is_marked_for_review': True
        }

        url = reverse('examinations:save_answer_api')
        # Setting HTTP_HOST for tenant resolution
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='alpha.localhost'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['answered_count'], 1)

        # Verify saved in DB
        ans = StudentAnswer.objects.filter(attempt=attempt, question=self.q_mcq).first()
        self.assertIsNotNone(ans)
        self.assertTrue(ans.is_marked_for_review)
        self.assertIn(self.opt_mcq_2, ans.selected_options.all())

    def test_student_submit_exam_view(self):
        """Test final student exam submission workflow."""
        attempt = StudentExamAttempt.objects.create(
            school=self.school,
            online_exam=self.online_exam,
            student=self.student_user,
            status=AttemptStatus.IN_PROGRESS,
            started_at=timezone.now()
        )

        # Save an answer
        ans = StudentAnswer.objects.create(school=self.school, attempt=attempt, question=self.q_mcq)
        ans.selected_options.add(self.opt_mcq_2)

        self.client.force_login(self.student_user)
        url = reverse('examinations:student_submit', kwargs={'exam_id': self.online_exam.id})
        response = self.client.post(url, HTTP_HOST='alpha.localhost')

        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.assertIn(attempt.status, [AttemptStatus.SUBMITTED, AttemptStatus.GRADED])
        self.assertIsNotNone(attempt.submitted_at)
        self.assertGreater(attempt.total_score, 0)
