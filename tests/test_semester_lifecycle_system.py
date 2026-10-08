import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.schools.models import School
from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    PeriodStatus,
    SemesterArchive,
    Grade,
    Section,
    SchoolEvent
)
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.students.models import StudentProfile
from apps.assessments.models import (
    AcademicPeriodResult,
    MarkEntryLock,
    AssessmentComponent,
    StudentMark,
    MarkStatus
)
from apps.academics.lifecycle_service import AcademicPeriodLifecycleService
from apps.audit.models import AuditLog

User = get_user_model()


class SemesterLifecycleSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Horizon Academy",
            code="HORIZON",
            calendar_preference="ETHIOPIAN"
        )
        self.admin = User.objects.create_superuser(
            username="horizon_admin",
            email="admin@horizon.edu.et",
            password="adminpassword123",
            role="SCHOOL_ADMIN",
            school=self.school
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
            instructional_days=92,
            is_current=True,
            status=PeriodStatus.OPEN
        )

        self.sem2 = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.ay,
            name="Semester 2",
            start_date=datetime.date(2025, 2, 10),
            end_date=datetime.date(2025, 6, 30),
            instructional_days=88,
            is_current=False,
            status=PeriodStatus.OPEN
        )

        self.grade = Grade.objects.create(school=self.school, name="Grade 9", level=9)
        from apps.academics.models import Stream
        self.stream = Stream.objects.create(school=self.school, name="General Stream", code="GEN")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="9-A")

        self.student_user = User.objects.create_user(
            username="student_bereket",
            email="bereket@horizon.edu.et",
            role="STUDENT",
            school=self.school
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            school=self.school,
            first_name="Bereket",
            last_name="Haile",
            student_id="STU-001",
            date_of_birth=datetime.date(2010, 1, 1),
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

        self.client.force_login(self.admin)

    def test_set_active_semester(self):
        """Verify activating a semester unsets others and updates pointers."""
        res = AcademicPeriodLifecycleService.set_active_semester(self.sem2, user=self.admin)
        self.assertTrue(res['success'])

        self.sem1.refresh_from_db()
        self.sem2.refresh_from_db()

        self.assertFalse(self.sem1.is_current)
        self.assertTrue(self.sem2.is_current)

        audit = AuditLog.objects.filter(school=self.school, action="PERIOD_ACTIVATED").first()
        self.assertIsNotNone(audit)

    def test_lock_and_reopen_semester(self):
        """Verify locking a semester freezes records, and reopening requires justification."""
        # 1. Lock semester
        lock_res = AcademicPeriodLifecycleService.lock_semester(self.sem1, user=self.admin, reason="End of teaching.")
        self.assertTrue(lock_res['success'])

        self.sem1.refresh_from_db()
        self.assertEqual(self.sem1.status, PeriodStatus.LOCKED)
        self.assertIsNotNone(self.sem1.locked_at)
        self.assertEqual(self.sem1.locked_by, self.admin)
        self.assertTrue(self.sem1.is_locked)

        # Verify MarkEntryLock detects locked semester
        is_locked, reason, _ = MarkEntryLock.check_lock(self.school, period=self.sem1)
        self.assertTrue(is_locked)
        self.assertIn("cannot be altered", reason)

        # 2. Reopen without reason should fail
        fail_res = AcademicPeriodLifecycleService.reopen_semester(self.sem1, user=self.admin, reason="")
        self.assertFalse(fail_res['success'])

        # 3. Reopen with valid reason should succeed
        reopen_res = AcademicPeriodLifecycleService.reopen_semester(
            self.sem1,
            user=self.admin,
            reason="Approved supplementary exam grade entry by Principal."
        )
        self.assertTrue(reopen_res['success'])

        self.sem1.refresh_from_db()
        self.assertEqual(self.sem1.status, PeriodStatus.OPEN)
        self.assertIsNotNone(self.sem1.reopened_at)
        self.assertEqual(self.sem1.reopen_reason, "Approved supplementary exam grade entry by Principal.")

    def test_semester_close_and_archive(self):
        """Verify closing a semester generates section ranks and creates SemesterArchive."""
        # Create a mock result
        AcademicPeriodResult.objects.create(
            school=self.school,
            enrollment=self.enrollment,
            period=self.sem1,
            total_score=85.0,
            average_score=85.0,
            subjects_passed=5,
            subjects_failed=0,
            section_rank=1,
            is_published=True
        )

        # Create archive
        archive = AcademicPeriodLifecycleService.create_semester_archive(
            period=self.sem1,
            user=self.admin,
            notes="Quarterly close audit snapshot."
        )

        self.assertIsNotNone(archive)
        self.assertEqual(archive.total_students, 1)
        self.assertEqual(archive.passed_students, 1)
        self.assertEqual(float(archive.overall_average), 85.0)
        self.assertIn("pass_rate_percentage", archive.snapshot_data)
        self.assertEqual(archive.snapshot_data["pass_rate_percentage"], 100.0)

    def test_transition_to_next_semester(self):
        """Verify seamless rollover from Semester 1 to Semester 2."""
        res = AcademicPeriodLifecycleService.transition_to_next_semester(
            current_period=self.sem1,
            next_period=self.sem2,
            user=self.admin
        )
        self.assertTrue(res['success'])

        self.sem1.refresh_from_db()
        self.sem2.refresh_from_db()

        self.assertFalse(self.sem1.is_current)
        self.assertEqual(self.sem1.status, PeriodStatus.LOCKED)
        self.assertTrue(self.sem2.is_current)
        self.assertEqual(self.sem2.status, PeriodStatus.OPEN)

        # Check archive exists
        self.assertTrue(SemesterArchive.objects.filter(school=self.school, period=self.sem1).exists())

    def test_schedule_supplementary_exams(self):
        """Verify scheduling supplementary exam window creates calendar event."""
        res = AcademicPeriodLifecycleService.configure_supplementary_exams(
            period=self.sem1,
            start_date=datetime.date(2025, 2, 1),
            end_date=datetime.date(2025, 2, 5),
            user=self.admin
        )
        self.assertTrue(res['success'])

        self.sem1.refresh_from_db()
        self.assertTrue(self.sem1.has_supplementary_exam)
        self.assertEqual(self.sem1.supplementary_start_date, datetime.date(2025, 2, 1))

        # Verify calendar event created
        evt = SchoolEvent.objects.filter(
            school=self.school,
            academic_period=self.sem1,
            title__icontains="Supplementary"
        ).first()
        self.assertIsNotNone(evt)
        self.assertEqual(evt.start_date, datetime.date(2025, 2, 1))

    def test_semester_lifecycle_views_http(self):
        """Verify HTTP endpoints for lifecycle dashboard and actions."""
        # 1. Dashboard View
        resp = self.client.get(reverse('academics:semester_lifecycle'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Term & Semester Lifecycle Hub")
        self.assertContains(resp, "Semester 1")

        # 2. Lock Action POST
        lock_url = reverse('academics:lock_semester', kwargs={'period_id': self.sem1.id})
        lock_post = self.client.post(lock_url, {'reason': 'Term ended'}, follow=True)
        self.assertEqual(lock_post.status_code, 200)

        self.sem1.refresh_from_db()
        self.assertEqual(self.sem1.status, PeriodStatus.LOCKED)

        # 3. Reopen Action POST
        reopen_url = reverse('academics:reopen_semester', kwargs={'period_id': self.sem1.id})
        reopen_post = self.client.post(reopen_url, {'reason': 'Board approval for regrade'}, follow=True)
        self.assertEqual(reopen_post.status_code, 200)

        self.sem1.refresh_from_db()
        self.assertEqual(self.sem1.status, PeriodStatus.OPEN)
