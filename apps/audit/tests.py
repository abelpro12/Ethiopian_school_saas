from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.tenants.models import School
from apps.audit.models import AuditLog, LoginAuditLog
from apps.audit.services import AuditService


class ActivityLogTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Seattle Academy",
            code="SEA",
            subdomain="seattle",
            is_active=True
        )
        self.admin_user = User.objects.create_user(
            username="admin_test",
            password="password123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_test",
            password="password123",
            role=UserRole.TEACHER,
            school=self.school
        )
        self.student_user = User.objects.create_user(
            username="student_test",
            password="password123",
            role=UserRole.STUDENT,
            school=self.school
        )

        # Seed sample audit record
        self.log = AuditService.log_action(
            school=self.school,
            user=self.admin_user,
            action="STUDENT_ADMITTED",
            object_type="StudentProfile",
            object_id="STU-001",
            after_val={"student_name": "Abel Pro"},
            ip_address="196.188.45.12"
        )

        self.login_log = AuditService.log_login(
            school=self.school,
            username_attempted="admin_test",
            user=self.admin_user,
            status="SUCCESS",
            ip_address="196.188.45.12"
        )

        self.client = Client()

    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('audit:activity_log'))
        self.assertEqual(response.status_code, 302)

    def test_unauthorized_roles_denied(self):
        # Teacher is denied access
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('audit:activity_log'))
        self.assertEqual(response.status_code, 302)

        # Student is denied access
        self.client.force_login(self.student_user)
        response = self.client.get(reverse('audit:activity_log'))
        self.assertEqual(response.status_code, 302)

    def test_admin_access_activity_log(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('audit:activity_log'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity & Audit Trail")
        self.assertContains(response, "STUDENT_ADMITTED")

    def test_logins_tab(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('audit:activity_log') + '?tab=logins')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Authentication & Login Log")
        self.assertContains(response, "admin_test")

    def test_csv_export(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('audit:export_activity_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertContains(response, "STUDENT_ADMITTED")

    def test_login_csv_export(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('audit:export_login_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertContains(response, "admin_test")

    def test_detail_json_api(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('audit:audit_detail_json', kwargs={'log_id': self.log.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['action'], "STUDENT_ADMITTED")
        self.assertEqual(data['actor_username'], "admin_test")
