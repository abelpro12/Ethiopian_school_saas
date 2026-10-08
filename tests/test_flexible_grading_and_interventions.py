import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.schools.models import School
from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    Grade,
    Stream,
    Section,
    Subject
)
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.assessments.models import (
    AssessmentComponent,
    StudentMark,
    MarkStatus,
    MarkEntryLock,
    GradingScale,
    GradingScaleRule,
    GradingScaleType,
    AcademicIntervention,
    InterventionType,
    InterventionStatus
)
from apps.assessments.grading_service import GradingService
from apps.assessments.intervention_service import AcademicInterventionService
from apps.audit.models import AuditLog

User = get_user_model()


class FlexibleGradingAndInterventionsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Seattle Academy",
            code="SEA",
            calendar_preference="ETHIOPIAN"
        )
        self.admin = User.objects.create_superuser(
            username="admin_sea",
            email="admin@seattle.edu.et",
            password="adminpassword123",
            role="SCHOOL_ADMIN",
            school=self.school
        )

        self.teacher_user = User.objects.create_user(
            username="teacher_almaz",
            email="almaz@seattle.edu.et",
            password="teacherpass123",
            role="TEACHER",
            school=self.school,
            first_name="Almaz",
            last_name="Kebede"
        )
        self.teacher_profile = TeacherProfile.objects.create(
            user=self.teacher_user,
            school=self.school,
            employee_id="SEA-TCH-001"
        )

        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            is_active=True
        )

        self.sem1 = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.ay,
            name="Semester 1",
            start_date=datetime.date(2024, 9, 16),
            end_date=datetime.date(2025, 1, 30),
            is_current=True
        )

        self.grade = Grade.objects.create(school=self.school, name="Grade 9", level=9)
        self.stream = Stream.objects.create(school=self.school, name="General Stream", code="GEN")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="9-A")
        self.subject = Subject.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="Mathematics", code="MATH-9")

        # Assign teacher to section and subject
        TeacherAssignment.objects.create(
            school=self.school,
            teacher=self.teacher_profile,
            section=self.section,
            subject=self.subject,
            academic_year=self.ay
        )

        # Create Student
        self.student_user = User.objects.create_user(
            username="student_dawit",
            email="dawit@seattle.edu.et",
            role="STUDENT",
            school=self.school,
            first_name="Dawit",
            last_name="Tadesse",
            phone="0911223344"
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            school=self.school,
            first_name="Dawit",
            last_name="Tadesse",
            student_id="SEA-001",
            date_of_birth=datetime.date(2010, 5, 12),
            gender="M"
        )

        self.enrollment = StudentEnrollment.objects.create(
            school=self.school,
            student=self.student,
            academic_year=self.ay,
            grade=self.grade,
            stream=self.stream,
            section=self.section,
            status=EnrollmentStatus.ACTIVE
        )

        # Components
        self.comp_midterm = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.ay,
            period=self.sem1,
            subject=self.subject,
            name="Midterm Exam",
            assessment_type="EXAM",
            max_marks=Decimal('30.00'),
            weight=Decimal('30.00')
        )
        self.comp_final = AssessmentComponent.objects.create(
            school=self.school,
            academic_year=self.ay,
            period=self.sem1,
            subject=self.subject,
            name="Final Exam",
            assessment_type="EXAM",
            max_marks=Decimal('50.00'),
            weight=Decimal('50.00')
        )

        # Configured Grading Scale
        self.scale = GradingScale.objects.create(
            school=self.school,
            name="Standard Secondary Scale",
            scale_type=GradingScaleType.NUMERICAL,
            is_default=True,
            min_passing_mark=Decimal('50.00'),
            below_average_threshold=Decimal('60.00'),
            high_performance_threshold=Decimal('90.00')
        )
        self.rule_a = GradingScaleRule.objects.create(
            school=self.school, scale=self.scale, letter_grade="A", min_score=Decimal('85.00'), max_score=Decimal('100.00'),
            gpa_point=Decimal('4.00'), description="Distinction", is_passing=True, sort_order=1
        )
        self.rule_b = GradingScaleRule.objects.create(
            school=self.school, scale=self.scale, letter_grade="B", min_score=Decimal('70.00'), max_score=Decimal('84.99'),
            gpa_point=Decimal('3.00'), description="Very Good", is_passing=True, sort_order=2
        )
        self.rule_c = GradingScaleRule.objects.create(
            school=self.school, scale=self.scale, letter_grade="C", min_score=Decimal('50.00'), max_score=Decimal('69.99'),
            gpa_point=Decimal('2.00'), description="Satisfactory", is_passing=True, sort_order=3
        )
        self.rule_f = GradingScaleRule.objects.create(
            school=self.school, scale=self.scale, letter_grade="F", min_score=Decimal('0.00'), max_score=Decimal('49.99'),
            gpa_point=Decimal('0.00'), description="Fail", is_passing=False, sort_order=4
        )

    def test_grading_scale_numerical_evaluation(self):
        """Test Option A: numerical percentage score maps to letter grade and GPA point."""
        eval_high = GradingService.evaluate_mark(self.school, 92.0, 100.0, grade=self.grade)
        self.assertEqual(eval_high['letter_grade'], "A")
        self.assertEqual(float(eval_high['gpa_points']), 4.0)
        self.assertTrue(eval_high['is_passing'])

        eval_mid = GradingService.evaluate_mark(self.school, 75.0, 100.0, grade=self.grade)
        self.assertEqual(eval_mid['letter_grade'], "B")
        self.assertEqual(float(eval_mid['gpa_points']), 3.0)

        eval_fail = GradingService.evaluate_mark(self.school, 40.0, 100.0, grade=self.grade)
        self.assertEqual(eval_fail['letter_grade'], "F")
        self.assertEqual(float(eval_fail['gpa_points']), 0.0)
        self.assertFalse(eval_fail['is_passing'])

    def test_grading_scale_letter_conversion_option_b(self):
        """Test Option B: converting letter grades directly to numerical scores."""
        score_a = GradingService.convert_letter_to_score(self.school, "A", max_marks=100.0, grade=self.grade)
        self.assertIsNotNone(score_a)
        self.assertGreaterEqual(score_a, 85.0)
        self.assertLessEqual(score_a, 100.0)

        score_f = GradingService.convert_letter_to_score(self.school, "F", max_marks=100.0, grade=self.grade)
        self.assertIsNotNone(score_f)
        self.assertLess(score_f, 50.0)

    def test_student_mark_save_auto_evaluates_scale(self):
        """Test StudentMark automatically populates letter_grade and grade_points upon save."""
        # 27 / 30 = 90% (Distinction A)
        mark = StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=self.comp_midterm,
            mark_value=Decimal('27.00'),
            entered_by=self.admin
        )
        self.assertEqual(mark.letter_grade, "A")
        self.assertEqual(mark.grade_points, Decimal('4.00'))

    def test_component_level_lock_enforcement(self):
        """Test locking an individual AssessmentComponent locks only that component."""
        # Lock Midterm Exam only for Section 9-A
        MarkEntryLock.objects.create(
            school=self.school,
            academic_year=self.ay,
            period=self.sem1,
            assessment_component=self.comp_midterm,
            section=self.section,
            lock_type="COMPONENT",
            is_active=True,
            reason="Midterm grade submission deadline expired",
            locked_by=self.admin
        )

        # Check Midterm is locked
        midterm_locked, reason, _ = MarkEntryLock.check_lock(
            school=self.school,
            academic_year=self.ay,
            period=self.sem1,
            grade=self.grade,
            subject=self.subject,
            section=self.section,
            assessment_component=self.comp_midterm
        )
        self.assertTrue(midterm_locked)
        self.assertIn("Midterm grade submission deadline expired", reason)

        # Check Final Exam remains OPEN
        final_locked, _, _ = MarkEntryLock.check_lock(
            school=self.school,
            academic_year=self.ay,
            period=self.sem1,
            grade=self.grade,
            subject=self.subject,
            section=self.section,
            assessment_component=self.comp_final
        )
        self.assertFalse(final_locked)

    def test_teacher_quick_toggle_component_lock(self):
        """Test assigned teacher can lock and unlock their assigned class component with audit trail."""
        self.client.force_login(self.teacher_user)
        toggle_url = reverse('assessments:quick_toggle_grid_lock')

        # 1. Lock component
        res_lock = self.client.post(toggle_url, {
            'target_type': 'component',
            'target_id': self.comp_midterm.id,
            'section_id': self.section.id,
            'reason': 'Teacher submitted preliminary marks'
        })
        self.assertEqual(res_lock.status_code, 302)

        lock_record = MarkEntryLock.objects.filter(
            school=self.school, assessment_component=self.comp_midterm, section=self.section
        ).first()
        self.assertIsNotNone(lock_record)
        self.assertTrue(lock_record.is_active)

        # 2. Unlock component with reason
        res_unlock = self.client.post(toggle_url, {
            'target_type': 'component',
            'target_id': self.comp_midterm.id,
            'section_id': self.section.id,
            'reason': 'Student re-evaluation approved'
        })
        self.assertEqual(res_unlock.status_code, 302)
        lock_record.refresh_from_db()
        self.assertFalse(lock_record.is_active)
        self.assertEqual(lock_record.unlocked_by, self.teacher_user)
        self.assertEqual(lock_record.unlock_reason, 'Student re-evaluation approved')

        # Check Audit Log recorded
        audit = AuditLog.objects.filter(school=self.school, action="MARK_LOCK_COMPONENT_UNLOCKED").first()
        self.assertIsNotNone(audit)

    def test_below_average_detection_and_academic_intervention(self):
        """Test below-average performance detection (<60%) and intervention workflow."""
        # 12 / 30 = 40% (Below 60% threshold)
        mark = StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=self.comp_midterm,
            mark_value=Decimal('12.00'),
            entered_by=self.admin
        )

        detected = AcademicInterventionService.detect_below_average_students(
            school=self.school,
            period=self.sem1,
            subject_id=self.subject.id
        )
        self.assertEqual(len(detected), 1)
        self.assertEqual(str(detected[0]['student_id']), str(self.student.id))
        self.assertAlmostEqual(detected[0]['percentage'], 40.0, places=1)

        # Create Intervention
        intervention = AcademicInterventionService.create_intervention(
            school=self.school,
            enrollment_id=self.enrollment.id,
            subject_id=self.subject.id,
            component_id=self.comp_midterm.id,
            trigger_score=40.0,
            intervention_type=InterventionType.TUTORIAL,
            action_plan="Weekly remedial tutoring on algebra foundations.",
            scheduled_date=datetime.date.today() + datetime.timedelta(days=2),
            assigned_teacher_id=self.teacher_profile.id,
            notify_parent=True,
            user=self.admin
        )
        self.assertEqual(intervention.status, InterventionStatus.IN_PROGRESS)
        self.assertTrue(intervention.parent_notified)
        self.assertIsNotNone(intervention.parent_notified_at)

        # Resolve Intervention with Retest Score
        updated = AcademicInterventionService.update_intervention(
            intervention_id=intervention.id,
            school=self.school,
            status=InterventionStatus.RESOLVED,
            follow_up_score=75.0,
            outcome_notes="Dawit passed the remedial retest with 75% after 3 tutorial sessions.",
            user=self.admin
        )
        self.assertEqual(updated.status, InterventionStatus.RESOLVED)
        self.assertEqual(updated.follow_up_score, Decimal('75.00'))

    def test_grading_scales_views(self):
        """Test HTTP views for managing grading scales and rules."""
        self.client.force_login(self.admin)
        
        # 1. Scale list view
        res = self.client.get(reverse('assessments:grading_scales'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Standard Secondary Scale")

        # 2. Save new scale
        res_create = self.client.post(reverse('assessments:save_grading_scale'), {
            'name': 'Primary School Letter Scale',
            'scale_type': 'LETTER_GRADE',
            'min_passing_mark': '50',
            'below_average_threshold': '60',
            'high_performance_threshold': '90'
        })
        self.assertEqual(res_create.status_code, 302)
        new_scale = GradingScale.objects.filter(school=self.school, name='Primary School Letter Scale').first()
        self.assertIsNotNone(new_scale)

        # 3. Save rule for scale
        res_rule = self.client.post(reverse('assessments:save_grading_rule'), {
            'scale_id': new_scale.id,
            'letter_grade': 'A+',
            'min_score': '95',
            'max_score': '100',
            'gpa_point': '4.0',
            'description': 'Superior Distinction',
            'is_passing': 'on',
            'sort_order': '1'
        })
        self.assertEqual(res_rule.status_code, 302)
        self.assertTrue(GradingScaleRule.objects.filter(scale=new_scale, letter_grade='A+').exists())

    def test_intervention_dashboard_views(self):
        """Test HTTP view for Academic Intervention Hub."""
        self.client.force_login(self.admin)

        # Create a below average mark
        StudentMark.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            assessment_component=self.comp_midterm,
            mark_value=Decimal('10.00'),
            entered_by=self.admin
        )

        res = self.client.get(reverse('assessments:interventions'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Academic Intervention & Support Hub")
        self.assertContains(res, "Dawit")

        # Create intervention via view
        create_url = reverse('assessments:create_intervention')
        res_post = self.client.post(create_url, {
            'student_id': str(self.student.id),
            'enrollment_id': self.enrollment.id,
            'subject_id': self.subject.id,
            'component_id': self.comp_midterm.id,
            'trigger_score': '33.33',
            'intervention_type': 'PARENT_MEETING',
            'action_plan': 'Meeting scheduled with guardian to review exam papers.',
            'scheduled_date': datetime.date.today().strftime('%Y-%m-%d'),
            'notify_parent': 'on'
        })
        self.assertEqual(res_post.status_code, 302)
        intervention = AcademicIntervention.objects.filter(school=self.school, student=self.student).first()
        self.assertIsNotNone(intervention)
        self.assertEqual(intervention.intervention_type, 'PARENT_MEETING')
