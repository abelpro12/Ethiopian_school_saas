import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import UserRole
from apps.students.models import StudentProfile
from apps.subscriptions.models import SubscriptionPlan, SchoolSubscription, SubscriptionStatus
from apps.platform_management.models import PlatformFeatureFlag, PlatformAnnouncement, PlatformAuditLog
from apps.audit.models import AuditLog

User = get_user_model()

class PlatformManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Platform/Super Admin
        self.super_admin = User.objects.create_user(
            username="superadmin_test",
            password="password",
            role=UserRole.SUPER_ADMIN,
            is_superuser=True
        )

        import datetime

        # Create Subscriptions
        self.basic_plan = SubscriptionPlan.objects.create(
            name="Basic",
            tier="BASIC",
            price_per_year_etb=Decimal('6000.00'),
            billing_cycle='MONTHLY',
            is_active=True
        )
        
        self.premium_plan = SubscriptionPlan.objects.create(
            name="Premium",
            tier="PREMIUM",
            price_per_year_etb=Decimal('15000.00'),
            billing_cycle='YEARLY',
            is_active=True
        )

        # Create Schools
        self.school_a = School.objects.create(
            name="School A", subdomain="school-a", code="SCH-A", status=SchoolStatus.ACTIVE
        )
        self.school_b = School.objects.create(
            name="School B", subdomain="school-b", code="SCH-B", status=SchoolStatus.ACTIVE
        )

        end_date = datetime.date.today() + datetime.timedelta(days=365)

        # Create School Subscriptions
        SchoolSubscription.objects.create(school=self.school_a, plan=self.basic_plan, end_date=end_date, status=SubscriptionStatus.ACTIVE)
        SchoolSubscription.objects.create(school=self.school_b, plan=self.premium_plan, end_date=end_date, status=SubscriptionStatus.ACTIVE)

        # Create Role Users for School A
        self.school_admin_a = User.objects.create_user(username="admin_a", password="password", school=self.school_a, role=UserRole.SCHOOL_ADMIN)
        self.teacher_a = User.objects.create_user(username="teacher_a", password="password", school=self.school_a, role=UserRole.TEACHER)
        self.student_a_user = User.objects.create_user(username="student_a", password="password", school=self.school_a, role=UserRole.STUDENT)
        self.parent_a = User.objects.create_user(username="parent_a", password="password", school=self.school_a, role=UserRole.PARENT)
        
        StudentProfile.objects.create(school=self.school_a, user=self.student_a_user, student_id="STU-A", first_name="A", last_name="A", gender="M")

        # Create Users for School B
        self.school_admin_b = User.objects.create_user(username="admin_b", password="password", school=self.school_b, role=UserRole.SCHOOL_ADMIN)
        self.student_b_user = User.objects.create_user(username="student_b", password="password", school=self.school_b, role=UserRole.STUDENT)
        
        StudentProfile.objects.create(school=self.school_b, user=self.student_b_user, student_id="STU-B", first_name="B", last_name="B", gender="F")


    # 2. TEST ROLE BOUNDARIES
    def test_role_boundaries_for_super_admin(self):
        # Unauthenticated
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 302)
        
        # Super Admin
        self.client.login(username="superadmin_test", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 200)

        # School Admin
        self.client.login(username="admin_a", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 403)

        # Teacher
        self.client.login(username="teacher_a", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 403)

        # Student
        self.client.login(username="student_a", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 403)

        # Parent
        self.client.login(username="parent_a", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 403)

    # 3. TEST TENANT ISOLATION & 4. TEST TENANT CONTEXT
    def test_super_admin_tenant_context(self):
        # When Super Admin requests platform endpoint, they don't get restricted by middleware.
        self.client.login(username="superadmin_test", password="password")
        # In platform view, request.school should be None or not restrict queries.
        # This is implicitly tested by dashboard returning 200 and listing both schools.
        response = self.client.get(reverse('platform:dashboard'))
        self.assertContains(response, "School A")
        self.assertContains(response, "School B")

    # 5. TEST PROVISIONING END-TO-END
    def test_school_provisioning_flow(self):
        self.client.login(username="superadmin_test", password="password")
        
        response = self.client.post(reverse('platform:provision_school'), {
            'action': 'provision_school',
            'school_name': 'New Provisioned School',
            'school_subdomain': 'new-school',
            'school_code': 'NEW-SCH',
            'plan_id': self.basic_plan.id,
            'admin_first_name': 'Admin',
            'admin_last_name': 'User',
            'admin_email': 'admin@newschool.com',
            'admin_phone': '123456789'
        })
        
        self.assertEqual(response.status_code, 302) # Redirects back to dashboard
        
        # Verify
        new_school = School.objects.get(code='NEW-SCH')
        self.assertEqual(new_school.name, 'New Provisioned School')
        self.assertEqual(new_school.subdomain, 'new-school')
        
        # Subscription
        sub = SchoolSubscription.objects.get(school=new_school)
        self.assertEqual(sub.plan, self.basic_plan)
        
        # Admin
        admin_user = User.objects.get(school=new_school, role=UserRole.SCHOOL_ADMIN)
        self.assertEqual(admin_user.email, 'admin@newschool.com')
        
        # Duplicate code prevention
        response_duplicate = self.client.post(reverse('platform:provision_school'), {
            'action': 'provision_school',
            'school_name': 'Another',
            'school_subdomain': 'another-school',
            'school_code': 'NEW-SCH', # Duplicate
            'plan_id': self.basic_plan.id,
            'admin_first_name': 'A',
            'admin_last_name': 'B',
            'admin_email': 'a@b.com',
            'admin_phone': '123'
        })
        # Check that we still only have 1 NEW-SCH
        self.assertEqual(School.objects.filter(code='NEW-SCH').count(), 1)


    # 6. TEST STATUS TRANSITIONS
    def test_status_transitions(self):
        self.client.login(username="superadmin_test", password="password")
        
        # Suspend School A
        self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'suspend'})
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.SUSPENDED)
        
        sub_a = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub_a.status, SubscriptionStatus.SUSPENDED)
        
        # Activate School A
        self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'activate'})
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ACTIVE)
        
        sub_a.refresh_from_db()
        self.assertEqual(sub_a.status, SubscriptionStatus.ACTIVE)
        
        # Archive School A
        self.client.post(reverse('platform:school_action', args=[self.school_a.id]), {'action': 'archive'})
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ARCHIVED)
        
        sub_a.refresh_from_db()
        self.assertEqual(sub_a.status, SubscriptionStatus.CANCELLED)


    # 7. TEST AUDIT LOGGING
    def test_platform_audit_logs(self):
        self.client.login(username="superadmin_test", password="password")
        
        # Do an action
        self.client.post(reverse('platform:school_action', args=[self.school_b.id]), {'action': 'suspend'})
        
        log = PlatformAuditLog.objects.last()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.super_admin)
        self.assertEqual(log.action, 'SUSPEND_SCHOOL')
        self.assertEqual(log.target_school, self.school_b)
        self.assertEqual(log.before_state.get('status'), 'ACTIVE')
        self.assertEqual(log.after_state.get('status'), 'SUSPENDED')

    # 8. TEST FEATURE FLAG ISOLATION
    def test_feature_flag_isolation(self):
        # Global
        PlatformFeatureFlag.objects.create(name="AI_TUTOR", code="AI_TUTOR", is_active=True, scope='GLOBAL')
        # Plan
        PlatformFeatureFlag.objects.create(name="ADVANCED_ANALYTICS", code="ADVANCED_ANALYTICS", plan=self.premium_plan, is_active=True, scope='PLAN')
        # School
        PlatformFeatureFlag.objects.create(name="BETA_PORTAL", code="BETA_PORTAL", school=self.school_a, is_active=True, scope='SCHOOL')
        
        # Test resolution for School A (Basic Plan)
        self.assertTrue(PlatformFeatureFlag.is_feature_active("AI_TUTOR", school=self.school_a))
        self.assertFalse(PlatformFeatureFlag.is_feature_active("ADVANCED_ANALYTICS", school=self.school_a))
        self.assertTrue(PlatformFeatureFlag.is_feature_active("BETA_PORTAL", school=self.school_a))
        
        # Test resolution for School B (Premium Plan)
        self.assertTrue(PlatformFeatureFlag.is_feature_active("AI_TUTOR", school=self.school_b))
        self.assertTrue(PlatformFeatureFlag.is_feature_active("ADVANCED_ANALYTICS", school=self.school_b))
        self.assertFalse(PlatformFeatureFlag.is_feature_active("BETA_PORTAL", school=self.school_b))


    # 10. TEST DASHBOARD METRICS
    def test_dashboard_metrics(self):
        self.client.login(username="superadmin_test", password="password")
        
        # We have 2 schools (both active initially), 2 students total.
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # In context, we should have metrics
        self.assertEqual(response.context['total_schools'], 2)
        self.assertEqual(response.context['active_schools'], 2)
        self.assertEqual(response.context['total_students'], 2)
        
        # We suspend one
        self.school_a.status = SchoolStatus.SUSPENDED
        self.school_a.is_active = False
        self.school_a.save()
        
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.context['active_schools'], 1)
        
    # 11. TEST REVENUE
    def test_platform_revenue(self):
        self.client.login(username="superadmin_test", password="password")
        response = self.client.get(reverse('platform:dashboard'))
        
        self.assertEqual(response.context['total_revenue'], Decimal('0.00'))
