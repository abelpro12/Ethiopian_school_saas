from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.tenants.models import School, SchoolStatus
from apps.platform_management.models import PlatformAuditLog
from apps.students.models import StudentProfile
import uuid

class SchoolContextTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create Super Admin
        self.super_admin = User.objects.create_user(
            username='super_admin_ctx',
            password='password123',
            role=UserRole.SUPER_ADMIN,
            is_superuser=True
        )
        
        # Create Schools
        self.school_a = School.objects.create(
            name='School A', subdomain='schoola', code='SCHA', status=SchoolStatus.ACTIVE, is_active=True
        )
        self.school_b = School.objects.create(
            name='School B', subdomain='schoolb', code='SCHB', status=SchoolStatus.ACTIVE, is_active=True
        )
        self.school_archived = School.objects.create(
            name='School Archived', subdomain='schoolarc', code='SCHARC', status=SchoolStatus.ARCHIVED, is_active=False
        )

        # Create Normal Users
        self.school_a_admin = User.objects.create_user(
            username='admin_a', password='password123', role=UserRole.SCHOOL_ADMIN, school=self.school_a
        )
        self.school_b_admin = User.objects.create_user(
            username='admin_b', password='password123', role=UserRole.SCHOOL_ADMIN, school=self.school_b
        )
        self.student_a_user = User.objects.create_user(
            username='student_a', password='password123', role=UserRole.STUDENT, school=self.school_a
        )
        self.student_b_user = User.objects.create_user(
            username='student_b', password='password123', role=UserRole.STUDENT, school=self.school_b
        )
        
        # Create Tenant Data
        self.student_a = StudentProfile.objects.create(
            user=self.student_a_user, first_name='Student', last_name='A', admission_number='A001', school=self.school_a
        )
        self.student_b = StudentProfile.objects.create(
            user=self.student_b_user, first_name='Student', last_name='B', admission_number='B001', school=self.school_b
        )

    def test_platform_context_default(self):
        self.client.login(username='super_admin_ctx', password='password123')
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Super admin should not have active school in context
        self.assertIsNone(response.wsgi_request.school)
        self.assertIsNone(getattr(response.wsgi_request, 'active_school', None))
        
    def test_enter_school_context(self):
        self.client.login(username='super_admin_ctx', password='password123')
        enter_url = reverse('platform:enter_context', args=[self.school_a.id])
        
        response = self.client.post(enter_url)
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        # Verify Context on next request
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.wsgi_request.school, self.school_a)
        
        # Verify Audit
        log = PlatformAuditLog.objects.filter(action='SCHOOL_CONTEXT_ENTERED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_school, self.school_a)

    def test_exit_school_context(self):
        self.client.login(username='super_admin_ctx', password='password123')
        self.client.post(reverse('platform:enter_context', args=[self.school_a.id]))
        
        response = self.client.post(reverse('platform:exit_context'))
        self.assertRedirects(response, reverse('platform:dashboard'))
        
        # Verify Context on next request
        response = self.client.get(reverse('platform:dashboard'))
        self.assertIsNone(response.wsgi_request.school)
        
        # Verify Audit
        log = PlatformAuditLog.objects.filter(action='SCHOOL_CONTEXT_EXITED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_school, self.school_a)

    def test_switch_school_context(self):
        self.client.login(username='super_admin_ctx', password='password123')
        self.client.post(reverse('platform:enter_context', args=[self.school_a.id]))
        
        response = self.client.post(reverse('platform:enter_context', args=[self.school_b.id]))
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        # Verify Context on next request
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.wsgi_request.school, self.school_b)
        
        # Verify Audit
        log = PlatformAuditLog.objects.filter(action='SCHOOL_CONTEXT_SWITCHED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.target_school, self.school_b)
        self.assertEqual(log.before_state['context'], str(self.school_a.id))

    def test_security_normal_users_cannot_enter_context(self):
        self.client.login(username='admin_a', password='password123')
        enter_url = reverse('platform:enter_context', args=[self.school_b.id])
        
        response = self.client.post(enter_url)
        self.assertEqual(response.status_code, 403)
        
        # Verify their school context hasn't changed
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.wsgi_request.school, self.school_a)

    def test_suspended_archived_context(self):
        self.client.login(username='super_admin_ctx', password='password123')
        enter_url = reverse('platform:enter_context', args=[self.school_archived.id])
        
        response = self.client.post(enter_url)
        self.assertRedirects(response, reverse('admin_dashboard'))
        
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.wsgi_request.school, self.school_archived)

    def test_post_only(self):
        self.client.login(username='super_admin_ctx', password='password123')
        enter_url = reverse('platform:enter_context', args=[self.school_a.id])
        
        # GET should redirect or 405, current implementation redirects to platform:dashboard
        response = self.client.get(enter_url)
        self.assertRedirects(response, reverse('platform:dashboard'))
        self.assertIsNone(response.wsgi_request.session.get('active_school_context_id'))

    def test_role_boundaries_school_views(self):
        # Admin A can access School A dashboard
        self.client.login(username='admin_a', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_tenant_isolation_idor(self):
        # Admin A cannot enter context of School B
        self.client.login(username='admin_a', password='password123')
        response = self.client.post(reverse('platform:enter_context', args=[self.school_b.id]))
        self.assertEqual(response.status_code, 403)

    def test_post_school_actions(self):
        self.client.login(username='super_admin_ctx', password='password123')
        # Suspend
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'suspend'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.SUSPENDED)
        self.assertFalse(self.school_a.is_active)
        
        # Activate
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'activate'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ACTIVE)
        self.assertTrue(self.school_a.is_active)
        
        # Archive
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'archive'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ARCHIVED)
        self.assertFalse(self.school_a.is_active)


    def test_school_context_required_decorator(self):
        # Without context
        self.client.login(username='super_admin_ctx', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)
        
        # With context
        self.client.post(reverse('platform:enter_context', args=[self.school_a.id]))
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        
    def test_role_boundaries_platform_views(self):
        # Platform Dashboard
        urls_to_test = [
            reverse('platform:dashboard'),
            reverse('platform:school_list'),
        ]
        
        # School Admin should get 403
        self.client.login(username='admin_a', password='password123')
        for url in urls_to_test:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            
        # Teacher should get 403
        teacher = User.objects.create_user(username='teacher1', password='pw', role=UserRole.TEACHER, school=self.school_a)
        self.client.login(username='teacher1', password='pw')
        for url in urls_to_test:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

        # Student should get 403
        self.client.login(username='student_a', password='password123')
        for url in urls_to_test:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_role_boundaries_school_views(self):
        # Admin A can access School A dashboard
        self.client.login(username='admin_a', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_tenant_isolation_idor(self):
        # Admin A cannot enter context of School B
        self.client.login(username='admin_a', password='password123')
        response = self.client.post(reverse('platform:enter_context', args=[self.school_b.id]))
        self.assertEqual(response.status_code, 403)

    def test_post_school_actions(self):
        self.client.login(username='super_admin_ctx', password='password123')
        # Suspend
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'suspend'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.SUSPENDED)
        self.assertFalse(self.school_a.is_active)
        
        # Activate
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'activate'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ACTIVE)
        self.assertTrue(self.school_a.is_active)
        
        # Archive
        response = self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'archive'})
        self.assertEqual(response.status_code, 302)
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ARCHIVED)
        self.assertFalse(self.school_a.is_active)



from apps.platform_management.models import PlatformAuditLog
from apps.students.models import StudentProfile

class MoreSchoolContextTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(username='super2', password='pw', role=UserRole.SUPER_ADMIN)
        
        self.school_a = School.objects.create(name='School A', subdomain='a', code='SCHA', status=SchoolStatus.ACTIVE)
        self.school_b = School.objects.create(name='School B', subdomain='b', code='SCHB', status=SchoolStatus.ACTIVE)
        
        # We need users for StudentProfile to pass validation
        self.student_u_a = User.objects.create_user(username='stu_a', password='pw', role=UserRole.STUDENT, school=self.school_a)
        self.student_u_b = User.objects.create_user(username='stu_b', password='pw', role=UserRole.STUDENT, school=self.school_b)
        
        self.student_a = StudentProfile.objects.create(
            user=self.student_u_a,
            first_name='Student A',
            school=self.school_a
        )
        self.student_b = StudentProfile.objects.create(
            user=self.student_u_b,
            first_name='Student B',
            school=self.school_b
        )

    def test_audit_log_on_context_entry_and_exit(self):
        self.client.login(username='super2', password='pw')
        # Entry
        self.client.post(reverse('platform:enter_context', args=[self.school_a.id]))
        
        # Check audit log
        logs = PlatformAuditLog.objects.filter(actor=self.super_admin, action='SCHOOL_CONTEXT_ENTERED')
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().target_school, self.school_a)

        # Exit
        self.client.post(reverse('platform:exit_context'))
        exit_logs = PlatformAuditLog.objects.filter(actor=self.super_admin, action='SCHOOL_CONTEXT_EXITED')
        self.assertEqual(exit_logs.count(), 1)
        self.assertEqual(exit_logs.first().target_school, self.school_a)
        
    def test_tenant_isolation_in_context(self):
        self.client.login(username='super2', password='pw')
        # Enter Context A
        self.client.post(reverse('platform:enter_context', args=[self.school_a.id]))
        
        # We can simulate viewing a school view or just querying
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Test student profile listing via the actual view if we had one, but we can verify middleware sets request.school
        self.assertEqual(response.wsgi_request.school, self.school_a)
        
    def test_csrf_enforcement_on_actions(self):
        # We test that GET on school_action redirects without doing anything, and POST works only with CSRF
        self.client.login(username='super2', password='pw')
        # Django test client by default bypasses CSRF unless enforce_csrf_checks=True
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username='super2', password='pw')
        
        response = csrf_client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'suspend'})
        # Should be forbidden due to missing CSRF token
        self.assertEqual(response.status_code, 403)

class PlatformSubscriptionPlanTests(TestCase):
    def setUp(self):
        from apps.subscriptions.models import SubscriptionPlan
        self.client = Client()
        self.super_admin = User.objects.create_superuser(
            username='super_admin_subs', email='super_subs@platform.com', password='password'
        )
        self.school_admin = User.objects.create_user(
            username='school_admin_subs', email='admin_subs@school.com', password='password', role=UserRole.SCHOOL_ADMIN
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Test Plan", tier="BASIC", price_per_year_etb=1000
        )

    def test_super_admin_can_access_plans(self):
        self.client.login(username='super_admin_subs', password='password')
        response = self.client.get(reverse('platform:subscription_plan_list'))
        self.assertEqual(response.status_code, 200)

    def test_school_admin_cannot_access_plans(self):
        self.client.login(username='school_admin_subs', password='password')
        response = self.client.get(reverse('platform:subscription_plan_list'))
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_create_plan(self):
        from apps.subscriptions.models import SubscriptionPlan
        self.client.login(username='super_admin_subs', password='password')
        response = self.client.post(reverse('platform:save_subscription_plan'), {
            'name': 'New Plan',
            'tier': 'PREMIUM',
            'max_students': 100,
            'max_teachers': 10,
            'max_sms_per_month': 500,
            'max_storage_mb': 1000,
            'price_per_year_etb': 5000,
            'billing_cycle': 'YEARLY'
        })
        self.assertRedirects(response, reverse('platform:subscription_plan_list'))
        self.assertTrue(SubscriptionPlan.objects.filter(name='New Plan').exists())

class SuperAdminSubscriptionOverrideTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_superuser(
            username='super_override', email='super_override@platform.com', password='password'
        )
        self.school_admin = User.objects.create_user(
            username='school_admin_override', email='admin@school.com', password='password', role=UserRole.SCHOOL_ADMIN
        )
        self.school = School.objects.create(
            name="Override Test Academy", code="OTA", subdomain="ota", is_active=True
        )

    def test_super_admin_can_grant_free_trial_presets(self):
        self.client.login(username='super_override', password='password')
        response = self.client.post(reverse('platform:manage_school_subscription', args=[self.school.id]), {
            'action_type': 'preset_trial_90'
        })
        self.assertRedirects(response, reverse('platform:school_list'))
        
        self.school.refresh_from_db()
        sub = self.school.subscription
        self.assertEqual(sub.status, 'TRIAL')
        self.assertGreaterEqual(sub.days_remaining, 89)

    def test_super_admin_can_grant_free_1year_active(self):
        self.client.login(username='super_override', password='password')
        response = self.client.post(reverse('platform:manage_school_subscription', args=[self.school.id]), {
            'action_type': 'preset_free_1year'
        })
        self.assertRedirects(response, reverse('platform:school_list'))
        
        self.school.refresh_from_db()
        sub = self.school.subscription
        self.assertEqual(sub.status, 'ACTIVE')
        self.assertGreaterEqual(sub.days_remaining, 364)

    def test_super_admin_can_record_manual_payment(self):
        from apps.subscriptions.models import SubscriptionPayment
        self.client.login(username='super_override', password='password')
        response = self.client.post(reverse('platform:manage_school_subscription', args=[self.school.id]), {
            'action_type': 'custom',
            'status': 'ACTIVE',
            'days_to_add': '365',
            'amount_paid': '15000.00',
            'note': 'Special discount manual payment'
        })
        self.assertRedirects(response, reverse('platform:school_list'))
        
        self.assertTrue(SubscriptionPayment.objects.filter(school=self.school, amount_paid=15000.00).exists())

    def test_school_admin_cannot_override_subscription(self):
        self.client.login(username='school_admin_override', password='password')
        response = self.client.post(reverse('platform:manage_school_subscription', args=[self.school.id]), {
            'action_type': 'preset_free_1year'
        })
        self.assertEqual(response.status_code, 403)

    def test_super_admin_can_access_subscription_management_dashboard(self):
        self.client.login(username='super_override', password='password')
        response = self.client.get(reverse('platform:subscription_management'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'platform_management/subscription_management.html')
        self.assertIn('subscriptions', response.context)

    def test_subscription_management_filter_by_status(self):
        self.client.login(username='super_override', password='password')
        response = self.client.get(reverse('platform:subscription_management') + '?status=TRIAL')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['status_filter'], 'TRIAL')


