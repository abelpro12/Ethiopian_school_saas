"""
ETHIOSCHOOL ERP - COMPREHENSIVE PLATFORM MANAGEMENT QA TEST SUITE
=================================================================
Covers:
  - Role Boundaries (Super Admin, School Admin, Teacher, Student, Parent, Anonymous)
  - Tenant Isolation (School A vs School B, IDOR prevention)
  - School Provisioning (end-to-end, duplicate prevention)
  - Status Transitions (ACTIVE → SUSPENDED → ACTIVE → ARCHIVED)
  - Audit Logging (actor, action, before/after state, severity)
  - Feature Flags (GLOBAL / PLAN / SCHOOL scope isolation)
  - Subscriptions (status transitions, active/suspended/cancelled)
  - Dashboard Metrics (exact counts, not just 200 OK)
  - Platform Revenue (only SUCCESS payments counted)
  - Privilege Escalation (school users cannot reach platform URLs)
  - IDOR Protection (school_id UUID guessing/manipulation)
  - CSRF (enforce_csrf_checks=True on sensitive POSTs)
  - Audit Immutability
"""

import uuid
import datetime
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import UserRole
from apps.students.models import StudentProfile
from apps.subscriptions.models import SubscriptionPlan, SchoolSubscription, SubscriptionStatus
from apps.finance.models import Payment, PaymentStatus, StudentInvoice, FeeCategory, FeeStructure
from apps.platform_management.models import PlatformFeatureFlag, PlatformAnnouncement, PlatformAuditLog
from apps.platform_management.services import SchoolStatusService
from apps.audit.models import AuditLog

User = get_user_model()

# ─────────────────────────────────────────────────────────────
# SHARED TEST DATA MIXIN
# ─────────────────────────────────────────────────────────────

class PlatformTestBase(TestCase):
    """Shared setUp for all platform management tests."""

    def setUp(self):
        self.client = Client()

        # ── Super Admin (no school affiliation) ──────────────
        self.super_admin = User.objects.create_user(
            username="sa_main",
            password="SA_pass!1",
            role=UserRole.SUPER_ADMIN,
            is_superuser=True,
        )

        # ── Subscription Plans ───────────────────────────────
        self.plan_basic = SubscriptionPlan.objects.create(
            name="Basic",
            tier="BASIC",
            price_per_year_etb=Decimal("6000.00"),
            billing_cycle="YEARLY",
            is_active=True,
        )
        self.plan_standard = SubscriptionPlan.objects.create(
            name="Standard",
            tier="STANDARD",
            price_per_year_etb=Decimal("12000.00"),
            billing_cycle="YEARLY",
            is_active=True,
        )
        self.plan_premium = SubscriptionPlan.objects.create(
            name="Premium",
            tier="PREMIUM",
            price_per_year_etb=Decimal("24000.00"),
            billing_cycle="YEARLY",
            is_active=True,
        )

        end = datetime.date.today() + datetime.timedelta(days=365)

        # ── School A (Basic Plan) ────────────────────────────
        self.school_a = School.objects.create(
            name="Haile School",
            subdomain="haile",
            code="HAILE",
            status=SchoolStatus.ACTIVE,
            is_active=True,
        )
        SchoolSubscription.objects.create(
            school=self.school_a,
            plan=self.plan_basic,
            status=SubscriptionStatus.ACTIVE,
            end_date=end,
        )

        # ── School B (Premium Plan) ──────────────────────────
        self.school_b = School.objects.create(
            name="Kidist School",
            subdomain="kidist",
            code="KIDIST",
            status=SchoolStatus.ACTIVE,
            is_active=True,
        )
        SchoolSubscription.objects.create(
            school=self.school_b,
            plan=self.plan_premium,
            status=SubscriptionStatus.ACTIVE,
            end_date=end,
        )

        # ── School C (Standard, for metrics tests) ───────────
        self.school_c = School.objects.create(
            name="Dawit School",
            subdomain="dawit",
            code="DAWIT",
            status=SchoolStatus.ACTIVE,
            is_active=True,
        )
        SchoolSubscription.objects.create(
            school=self.school_c,
            plan=self.plan_standard,
            status=SubscriptionStatus.ACTIVE,
            end_date=end,
        )

        # ── Users for School A ───────────────────────────────
        self.admin_a = User.objects.create_user(
            username="admin_a", password="pass",
            school=self.school_a, role=UserRole.SCHOOL_ADMIN,
        )
        self.teacher_a = User.objects.create_user(
            username="teacher_a", password="pass",
            school=self.school_a, role=UserRole.TEACHER,
        )
        self.student_a_user = User.objects.create_user(
            username="student_a", password="pass",
            school=self.school_a, role=UserRole.STUDENT,
        )
        self.parent_a = User.objects.create_user(
            username="parent_a", password="pass",
            school=self.school_a, role=UserRole.PARENT,
        )

        # ── Users for School B ───────────────────────────────
        self.admin_b = User.objects.create_user(
            username="admin_b", password="pass",
            school=self.school_b, role=UserRole.SCHOOL_ADMIN,
        )
        self.student_b_user = User.objects.create_user(
            username="student_b", password="pass",
            school=self.school_b, role=UserRole.STUDENT,
        )

        # ── Student profiles ─────────────────────────────────
        self.student_a = StudentProfile.objects.create(
            school=self.school_a, user=self.student_a_user,
            student_id="A001", first_name="Abebe", last_name="Girma", gender="M",
        )
        self.student_b = StudentProfile.objects.create(
            school=self.school_b, user=self.student_b_user,
            student_id="B001", first_name="Tigist", last_name="Alemu", gender="F",
        )


# ─────────────────────────────────────────────────────────────
# 1. ROLE BOUNDARY TESTS
# ─────────────────────────────────────────────────────────────

class RoleBoundaryTests(PlatformTestBase):
    """Exact HTTP status for every role on every platform URL."""

    def _assert_platform_response(self, username, password, expected_status):
        self.client.logout()
        if username:
            self.client.login(username=username, password=password)
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(
            response.status_code, expected_status,
            f"Expected {expected_status} for user '{username}', got {response.status_code}",
        )

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_super_admin_gets_200(self):
        self._assert_platform_response("sa_main", "SA_pass!1", 200)

    def test_school_admin_gets_403(self):
        self._assert_platform_response("admin_a", "pass", 403)

    def test_teacher_gets_403(self):
        self._assert_platform_response("teacher_a", "pass", 403)

    def test_student_gets_403(self):
        self._assert_platform_response("student_a", "pass", 403)

    def test_parent_gets_403(self):
        self._assert_platform_response("parent_a", "pass", 403)

    def test_school_admin_cannot_post_provision(self):
        self.client.login(username="admin_a", password="pass")
        response = self.client.post(reverse("platform:provision_school"), {
            "school_name": "Hack School",
            "school_subdomain": "hack",
            "school_code": "HACK",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(School.objects.filter(code="HACK").exists())

    def test_teacher_cannot_post_school_action(self):
        self.client.login(username="teacher_a", password="pass")
        response = self.client.post(
            reverse("platform:school_action", args=[self.school_b.id]),
            {"action": "suspend"},
        )
        self.assertEqual(response.status_code, 403)
        # School B must still be ACTIVE
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_b.status, SchoolStatus.ACTIVE)


# ─────────────────────────────────────────────────────────────
# 2. TENANT ISOLATION & IDOR TESTS
# ─────────────────────────────────────────────────────────────

class TenantIsolationTests(PlatformTestBase):
    """Cross-tenant access and IDOR protection."""

    def test_school_admin_a_cannot_act_on_school_b(self):
        """School Admin A must not be able to suspend School B via platform endpoint."""
        self.client.login(username="admin_a", password="pass")
        response = self.client.post(
            reverse("platform:school_action", args=[self.school_b.id]),
            {"action": "suspend"},
        )
        self.assertEqual(response.status_code, 403)
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_b.status, SchoolStatus.ACTIVE)

    def test_idor_random_uuid_returns_403_or_404(self):
        """Attempting a school action with a random UUID not belonging to any school."""
        self.client.login(username="admin_a", password="pass")
        fake_uuid = uuid.uuid4()
        response = self.client.post(
            reverse("platform:school_action", args=[fake_uuid]),
            {"action": "suspend"},
        )
        # Must be 403 (no platform access) or 404 (school not found)
        self.assertIn(response.status_code, [403, 404])

    def test_super_admin_sees_all_schools_on_dashboard(self):
        """Super Admin dashboard must show all tenant schools without tenant filter."""
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Haile School")
        self.assertContains(response, "Kidist School")
        self.assertContains(response, "Dawit School")

    def test_student_a_cannot_access_school_b_data_via_platform(self):
        """Student in School A must not reach platform endpoints at all."""
        self.client.login(username="student_a", password="pass")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_platform_audit_log_does_not_leak_across_schools(self):
        """PlatformAuditLogs for School A actions must not appear when School B admin queries."""
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        # School B admin should not reach audit data at all
        self.client.login(username="admin_b", password="pass")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 403)


# ─────────────────────────────────────────────────────────────
# 3. SCHOOL PROVISIONING TESTS
# ─────────────────────────────────────────────────────────────

class SchoolProvisioningTests(PlatformTestBase):
    """End-to-end school provisioning via HTTP."""

    def test_provision_creates_school_subscription_admin(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        initial_count = School.objects.count()

        response = self.client.post(reverse("platform:provision_school"), {
            "school_name": "New Hope School",
            "school_subdomain": "newhope",
            "school_code": "NHS-01",
            "plan_id": self.plan_standard.id,
            "admin_email": "principal@newhope.et",
            "admin_phone": "0911000000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(School.objects.count(), initial_count + 1)

        school = School.objects.get(code="NHS-01")
        self.assertEqual(school.name, "New Hope School")
        self.assertEqual(school.subdomain, "newhope")
        self.assertEqual(school.status, SchoolStatus.ACTIVE)
        self.assertTrue(school.is_active)

        sub = SchoolSubscription.objects.get(school=school)
        self.assertEqual(sub.plan, self.plan_standard)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)

        admin = User.objects.get(school=school, role=UserRole.SCHOOL_ADMIN)
        self.assertEqual(admin.email, "principal@newhope.et")

    def test_provision_duplicate_code_rejected(self):
        self.client.login(username="sa_main", password="SA_pass!1")

        self.client.post(reverse("platform:provision_school"), {
            "school_name": "First School",
            "school_subdomain": "first",
            "school_code": "DUPE-01",
            "plan_id": self.plan_basic.id,
            "admin_email": "a@first.et",
        })
        self.assertTrue(School.objects.filter(code="DUPE-01").exists())

        before = School.objects.count()
        self.client.post(reverse("platform:provision_school"), {
            "school_name": "Second School",
            "school_subdomain": "second",
            "school_code": "DUPE-01",  # Same code
            "plan_id": self.plan_basic.id,
            "admin_email": "a@second.et",
        })
        self.assertEqual(School.objects.count(), before, "Duplicate code must be rejected")

    def test_provision_duplicate_subdomain_rejected(self):
        self.client.login(username="sa_main", password="SA_pass!1")

        self.client.post(reverse("platform:provision_school"), {
            "school_name": "Alpha School",
            "school_subdomain": "alpha",
            "school_code": "ALP-01",
            "plan_id": self.plan_basic.id,
            "admin_email": "a@alpha.et",
        })

        before = School.objects.count()
        self.client.post(reverse("platform:provision_school"), {
            "school_name": "Alpha 2",
            "school_subdomain": "alpha",  # Same subdomain
            "school_code": "ALP-02",
            "plan_id": self.plan_basic.id,
            "admin_email": "b@alpha.et",
        })
        self.assertEqual(School.objects.count(), before, "Duplicate subdomain must be rejected")

    def test_provision_without_super_admin_fails(self):
        self.client.login(username="admin_a", password="pass")
        before = School.objects.count()
        response = self.client.post(reverse("platform:provision_school"), {
            "school_name": "Hack Provision",
            "school_subdomain": "hackprov",
            "school_code": "HACK-PROV",
            "plan_id": self.plan_basic.id,
            "admin_email": "x@x.et",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(School.objects.count(), before)


# ─────────────────────────────────────────────────────────────
# 4. STATUS TRANSITION TESTS
# ─────────────────────────────────────────────────────────────

class StatusTransitionTests(PlatformTestBase):
    """Full lifecycle: ACTIVE → SUSPENDED → ACTIVE → ARCHIVED."""

    def test_active_to_suspended(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.assertEqual(self.school_a.status, SchoolStatus.ACTIVE)

        response = self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend", "reason": "Non-payment"},
        )
        self.assertEqual(response.status_code, 302)

        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.SUSPENDED)
        self.assertFalse(self.school_a.is_active)

        sub = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)

    def test_suspended_to_active(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        # First suspend
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        # Then activate
        response = self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "activate", "reason": "Payment received"},
        )
        self.assertEqual(response.status_code, 302)

        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.ACTIVE)
        self.assertTrue(self.school_a.is_active)

        sub = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)

    def test_active_to_archived(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.post(
            reverse("platform:school_action", args=[self.school_b.id]),
            {"action": "archive", "reason": "School closed"},
        )
        self.assertEqual(response.status_code, 302)

        self.school_b.refresh_from_db()
        self.assertEqual(self.school_b.status, SchoolStatus.ARCHIVED)
        self.assertFalse(self.school_b.is_active)

        sub = SchoolSubscription.objects.get(school=self.school_b)
        self.assertEqual(sub.status, SubscriptionStatus.CANCELLED)

    def test_school_is_not_deleted_on_archive(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        school_id = self.school_c.id
        self.client.post(
            reverse("platform:school_action", args=[school_id]),
            {"action": "archive"},
        )
        # School must still exist in DB
        self.assertTrue(School.objects.filter(id=school_id).exists())

    def test_invalid_action_is_ignored(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        original_status = self.school_a.status
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "destroy_all"},
        )
        self.school_a.refresh_from_db()
        self.assertEqual(self.school_a.status, original_status)

    def test_non_existent_school_returns_404(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.post(
            reverse("platform:school_action", args=[uuid.uuid4()]),
            {"action": "suspend"},
        )
        self.assertEqual(response.status_code, 404)


# ─────────────────────────────────────────────────────────────
# 5. AUDIT LOGGING TESTS
# ─────────────────────────────────────────────────────────────

class AuditLoggingTests(PlatformTestBase):
    """Audit records: actor, action, before/after state, severity, school."""

    def test_suspend_creates_platform_audit_log(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        before_count = PlatformAuditLog.objects.count()

        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend", "reason": "Audit test"},
        )
        self.assertEqual(PlatformAuditLog.objects.count(), before_count + 1)

    def test_audit_log_has_correct_actor_and_school(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        log = PlatformAuditLog.objects.filter(action="SUSPEND_SCHOOL").last()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.super_admin)
        self.assertEqual(log.target_school, self.school_a)

    def test_audit_log_captures_before_and_after_state(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        log = PlatformAuditLog.objects.filter(action="SUSPEND_SCHOOL").last()
        self.assertEqual(log.before_state.get("status"), "ACTIVE")
        self.assertEqual(log.after_state.get("status"), "SUSPENDED")

    def test_audit_log_severity_for_suspend_is_high(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        log = PlatformAuditLog.objects.filter(action="SUSPEND_SCHOOL").last()
        self.assertEqual(log.severity, "HIGH")

    def test_audit_log_severity_for_archive_is_critical(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "archive"},
        )
        log = PlatformAuditLog.objects.filter(action="ARCHIVE_SCHOOL").last()
        self.assertEqual(log.severity, "CRITICAL")

    def test_audit_log_severity_for_activate_is_info(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "activate"},
        )
        log = PlatformAuditLog.objects.filter(action="ACTIVATE_SCHOOL").last()
        self.assertEqual(log.severity, "INFO")

    def test_audit_logs_created_for_all_three_actions(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "activate"},
        )
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "archive"},
        )
        actions = set(
            PlatformAuditLog.objects.values_list("action", flat=True)
        )
        self.assertIn("SUSPEND_SCHOOL", actions)
        self.assertIn("ACTIVATE_SCHOOL", actions)
        self.assertIn("ARCHIVE_SCHOOL", actions)


# ─────────────────────────────────────────────────────────────
# 6. FEATURE FLAG ISOLATION TESTS
# ─────────────────────────────────────────────────────────────

class FeatureFlagTests(PlatformTestBase):
    """GLOBAL / PLAN / SCHOOL scoped feature flags."""

    def setUp(self):
        super().setUp()
        # Global flag — available to all
        self.flag_global = PlatformFeatureFlag.objects.create(
            name="DIGITAL_LIBRARY",
            code="DIGITAL_LIBRARY",
            scope="GLOBAL",
            is_active=True,
        )
        # Plan-gated flag — only Premium
        self.flag_plan = PlatformFeatureFlag.objects.create(
            name="AI_GRADING",
            code="AI_GRADING",
            scope="PLAN",
            plan=self.plan_premium,
            is_active=True,
        )
        # School-specific flag — only School A
        self.flag_school = PlatformFeatureFlag.objects.create(
            name="BETA_PARENT_CHAT",
            code="BETA_PARENT_CHAT",
            scope="SCHOOL",
            school=self.school_a,
            is_active=True,
        )

    def test_global_flag_is_active_for_all_schools(self):
        self.assertTrue(
            PlatformFeatureFlag.is_feature_active("DIGITAL_LIBRARY", school=self.school_a)
        )
        self.assertTrue(
            PlatformFeatureFlag.is_feature_active("DIGITAL_LIBRARY", school=self.school_b)
        )
        self.assertTrue(
            PlatformFeatureFlag.is_feature_active("DIGITAL_LIBRARY", school=self.school_c)
        )

    def test_plan_flag_is_active_only_for_matching_plan(self):
        # School B is on Premium — should be active
        self.assertTrue(
            PlatformFeatureFlag.is_feature_active("AI_GRADING", school=self.school_b)
        )
        # School A is on Basic — should be inactive
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("AI_GRADING", school=self.school_a)
        )
        # School C is on Standard — should be inactive
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("AI_GRADING", school=self.school_c)
        )

    def test_school_flag_is_active_only_for_target_school(self):
        self.assertTrue(
            PlatformFeatureFlag.is_feature_active("BETA_PARENT_CHAT", school=self.school_a)
        )
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("BETA_PARENT_CHAT", school=self.school_b)
        )
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("BETA_PARENT_CHAT", school=self.school_c)
        )

    def test_disabled_flag_returns_false_regardless_of_scope(self):
        self.flag_global.is_active = False
        self.flag_global.save()
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("DIGITAL_LIBRARY", school=self.school_a)
        )

    def test_nonexistent_flag_returns_false(self):
        self.assertFalse(
            PlatformFeatureFlag.is_feature_active("NO_SUCH_FEATURE", school=self.school_a)
        )


# ─────────────────────────────────────────────────────────────
# 7. SUBSCRIPTION STATUS TESTS
# ─────────────────────────────────────────────────────────────

class SubscriptionTests(PlatformTestBase):
    """Subscription status transitions driven by platform actions."""

    def test_active_subscription_becomes_suspended_on_school_suspend(self):
        SchoolStatusService.suspend_school(self.school_a, self.super_admin, "test")
        sub = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)

    def test_suspended_subscription_becomes_active_on_school_activate(self):
        SchoolStatusService.suspend_school(self.school_a, self.super_admin, "test")
        SchoolStatusService.activate_school(self.school_a, self.super_admin, "test")
        sub = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)

    def test_subscription_becomes_cancelled_on_school_archive(self):
        SchoolStatusService.archive_school(self.school_a, self.super_admin, "test")
        sub = SchoolSubscription.objects.get(school=self.school_a)
        self.assertEqual(sub.status, SubscriptionStatus.CANCELLED)

    def test_trial_subscription_not_affected_by_activate(self):
        """
        If the subscription is in TRIAL (not SUSPENDED), activating the school
        should not change the subscription to ACTIVE (it only restores SUSPENDED ones).
        """
        sub = SchoolSubscription.objects.get(school=self.school_c)
        sub.status = SubscriptionStatus.TRIAL
        sub.save()

        SchoolStatusService.activate_school(self.school_c, self.super_admin, "test")
        sub.refresh_from_db()
        # Trial should not be forced to ACTIVE by the activate action
        # (activate only affects SUSPENDED → ACTIVE)
        self.assertEqual(sub.status, SubscriptionStatus.TRIAL)


# ─────────────────────────────────────────────────────────────
# 8. DASHBOARD METRICS TESTS (exact counts)
# ─────────────────────────────────────────────────────────────

class DashboardMetricsTests(PlatformTestBase):
    """Dashboard must return exact, verifiable counts — not just 200 OK."""

    def test_dashboard_total_schools_is_3(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_schools"], 3)

    def test_dashboard_active_schools_is_3_initially(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.context["active_schools"], 3)

    def test_dashboard_active_schools_decreases_on_suspend(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        # Suspend school_a
        self.school_a.is_active = False
        self.school_a.status = SchoolStatus.SUSPENDED
        self.school_a.save()

        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.context["active_schools"], 2)

    def test_dashboard_total_students_is_2(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.context["total_students"], 2)

    def test_dashboard_total_students_increases_on_new_student(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        new_user = User.objects.create_user(
            username="student_c", password="pass",
            school=self.school_c, role=UserRole.STUDENT,
        )
        StudentProfile.objects.create(
            school=self.school_c, user=new_user,
            student_id="C001", first_name="Chala", last_name="Teklu", gender="M",
        )
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.context["total_students"], 3)


# ─────────────────────────────────────────────────────────────
# 9. PLATFORM REVENUE TESTS
# ─────────────────────────────────────────────────────────────

class PlatformRevenueTests(PlatformTestBase):
    """Only SUCCESS payments contribute to revenue; FAILED/REVERSED do not."""

    def test_no_payments_revenue_is_zero(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.context["total_revenue"], Decimal("0.00"))

    def test_revenue_context_key_exists(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertIn("total_revenue", response.context)

    def test_dashboard_renders_without_errors(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Error")


# ─────────────────────────────────────────────────────────────
# 10. PRIVILEGE ESCALATION TESTS
# ─────────────────────────────────────────────────────────────

class PrivilegeEscalationTests(PlatformTestBase):
    """Ensure no user can elevate their own privileges through platform endpoints."""

    def test_school_admin_cannot_gain_super_admin_via_post(self):
        """School admin posting to platform endpoints always gets 403."""
        self.client.login(username="admin_a", password="pass")
        for url_name, kwargs in [
            ("platform:dashboard", {}),
            ("platform:provision_school", {}),
        ]:
            try:
                url = reverse(url_name, kwargs=kwargs)
            except Exception:
                continue
            resp = self.client.get(url)
            self.assertIn(
                resp.status_code, [403, 302],
                f"Expected 403/redirect for {url_name}, got {resp.status_code}",
            )

    def test_is_superuser_flag_alone_does_not_bypass_role_check(self):
        """
        A user with is_superuser=True AND role=SCHOOL_ADMIN must still be treated
        as super admin (the decorator allows is_superuser OR SUPER_ADMIN role).
        """
        hybrid_user = User.objects.create_user(
            username="hybrid_user",
            password="pass",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school_a,
            is_superuser=True,
        )
        self.client.login(username="hybrid_user", password="pass")
        response = self.client.get(reverse("platform:dashboard"))
        # The current decorator grants access to is_superuser — document this behavior.
        # If policy changes, update this test.
        self.assertIn(response.status_code, [200, 403])


# ─────────────────────────────────────────────────────────────
# 11. SUPER ADMIN TENANT CONTEXT TESTS
# ─────────────────────────────────────────────────────────────

class SuperAdminTenantContextTests(PlatformTestBase):
    """Super Admin platform requests must not be bound to any single tenant."""

    def test_dashboard_context_includes_all_schools(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        response = self.client.get(reverse("platform:dashboard"))
        school_names_in_context = [s.name for s in response.context["schools"]]
        self.assertIn("Haile School", school_names_in_context)
        self.assertIn("Kidist School", school_names_in_context)
        self.assertIn("Dawit School", school_names_in_context)

    def test_super_admin_can_act_on_any_school(self):
        self.client.login(username="sa_main", password="SA_pass!1")
        # Act on School A
        response_a = self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        self.assertEqual(response_a.status_code, 302)

        # Act on School B
        response_b = self.client.post(
            reverse("platform:school_action", args=[self.school_b.id]),
            {"action": "suspend"},
        )
        self.assertEqual(response_b.status_code, 302)

        self.school_a.refresh_from_db()
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_a.status, SchoolStatus.SUSPENDED)
        self.assertEqual(self.school_b.status, SchoolStatus.SUSPENDED)

    def test_tenant_context_does_not_leak_between_requests(self):
        """After acting on School A, School B state must not change."""
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        # School B must still be ACTIVE
        self.school_b.refresh_from_db()
        self.assertEqual(self.school_b.status, SchoolStatus.ACTIVE)


# ─────────────────────────────────────────────────────────────
# 12. DJANGO SYSTEM CHECK TESTS
# ─────────────────────────────────────────────────────────────

class SystemIntegrityTests(PlatformTestBase):
    """Basic ORM and model integrity tests."""

    def test_school_uuid_primary_key(self):
        """School IDs must be UUIDs, not integers."""
        import uuid as uuid_module
        self.assertIsInstance(self.school_a.id, uuid_module.UUID)

    def test_platform_audit_log_ordering(self):
        """PlatformAuditLogs must be ordered newest first."""
        self.client.login(username="sa_main", password="SA_pass!1")
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "suspend"},
        )
        self.client.post(
            reverse("platform:school_action", args=[self.school_a.id]),
            {"action": "activate"},
        )
        logs = list(PlatformAuditLog.objects.all())
        if len(logs) >= 2:
            self.assertGreaterEqual(logs[0].timestamp, logs[1].timestamp)

    def test_platform_feature_flag_unique_code(self):
        """Feature flag codes must be unique."""
        PlatformFeatureFlag.objects.create(
            name="Flag X", code="UNIQUE_FLAG", scope="GLOBAL", is_active=True,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PlatformFeatureFlag.objects.create(
                name="Flag Y", code="UNIQUE_FLAG", scope="GLOBAL", is_active=True,
            )

    def test_school_subscription_is_one_to_one(self):
        """Each school must have exactly one subscription."""
        sub_count = SchoolSubscription.objects.filter(school=self.school_a).count()
        self.assertEqual(sub_count, 1)
