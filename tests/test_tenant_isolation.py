from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.students.models import StudentProfile


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(name="School A", subdomain="school-a", code="SCH-A")
        self.school_b = School.objects.create(name="School B", subdomain="school-b", code="SCH-B")

        self.user_a = User.objects.create_user(username="user_a", school=self.school_a, role=UserRole.TEACHER)
        self.user_b = User.objects.create_user(username="user_b", school=self.school_b, role=UserRole.TEACHER)

        self.student_a_user = User.objects.create_user(username="student_a_u", school=self.school_a)
        self.student_a = StudentProfile.objects.create(
            school=self.school_a,
            user=self.student_a_user,
            student_id="STU-001",
            first_name="Abel",
            middle_name="Tesfaye",
            last_name="Mamo",
            gender="M"
        )

        self.student_b_user = User.objects.create_user(username="student_b_u", school=self.school_b)
        self.student_b = StudentProfile.objects.create(
            school=self.school_b,
            user=self.student_b_user,
            student_id="STU-002",
            first_name="Beti",
            middle_name="Girma",
            last_name="Haile",
            gender="F"
        )

    def test_tenant_queryset_isolation(self):
        # Querying for School A returns only School A students
        qs_a = StudentProfile.objects.for_school(self.school_a)
        self.assertIn(self.student_a, qs_a)
        self.assertNotIn(self.student_b, qs_a)

        # Querying for School B returns only School B students
        qs_b = StudentProfile.objects.for_school(self.school_b)
        self.assertIn(self.student_b, qs_b)
        self.assertNotIn(self.student_a, qs_b)

    def test_cross_tenant_saving_prevention(self):
        # Attempting to save TenantAwareModel without school raises ValueError
        with self.assertRaises(ValueError):
            StudentProfile.objects.create(
                school=None,
                user=self.student_a_user,
                student_id="STU-BAD",
                first_name="Invalid",
                middle_name="NoSchool",
                last_name="Test",
                gender="M"
            )
