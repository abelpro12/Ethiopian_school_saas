import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.tenants.models import School
from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus, SubscriptionPlan, SubscriptionPayment
from apps.subscriptions.services import SubscriptionPaymentService


class UnifiedSubscriptionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Addis Model School",
            code="AMS",
            subdomain="ams",
            is_active=True
        )
        self.plan = SubscriptionPlan.objects.create(
            name="EthioSchool SaaS Standard Subscription",
            price_per_year_etb=Decimal('25000.00')
        )
        self.subscription = SchoolSubscription.objects.create(
            school=self.school,
            plan=self.plan,
            status=SubscriptionStatus.TRIAL,
            end_date=datetime.date.today() + datetime.timedelta(days=14)
        )
        self.school_admin = User.objects.create_user(
            username='school_admin_billing',
            email='admin@ams.edu.et',
            password='password',
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

    def test_days_remaining_calculation(self):
        self.assertEqual(self.subscription.days_remaining, 14)
        self.assertTrue(self.subscription.is_in_trial)
        self.assertFalse(self.subscription.is_expired)

    def test_expired_subscription_calculation(self):
        self.subscription.end_date = datetime.date.today() - datetime.timedelta(days=2)
        self.subscription.status = SubscriptionStatus.EXPIRED
        self.subscription.save()

        self.assertEqual(self.subscription.days_remaining, 0)
        self.assertTrue(self.subscription.is_expired)

    def test_subscription_extension(self):
        old_end_date = self.subscription.end_date
        self.subscription.extend_subscription(days=365)
        
        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(self.subscription.end_date, old_end_date + datetime.timedelta(days=365))
        self.assertGreater(self.subscription.days_remaining, 360)

    def test_chapa_subscription_payment_initialization(self):
        res = SubscriptionPaymentService.initialize_subscription_payment(self.school, self.school_admin)
        self.assertEqual(res['status'], 'success')
        self.assertTrue(res['tx_ref'].startswith('SUB-PAY-'))
        self.assertEqual(res['amount'], Decimal('25000.00'))

        payment = SubscriptionPayment.objects.get(tx_ref=res['tx_ref'])
        self.assertEqual(payment.status, 'PENDING')

    def test_chapa_subscription_webhook_processing(self):
        res = SubscriptionPaymentService.initialize_subscription_payment(self.school, self.school_admin)
        tx_ref = res['tx_ref']

        payment = SubscriptionPaymentService.process_subscription_webhook(tx_ref, 'SUCCESS')
        self.assertEqual(payment.status, 'SUCCESS')
        self.assertTrue(payment.receipt_no.startswith('REC-SUB-'))

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)
        self.assertGreater(self.subscription.days_remaining, 360)

    def test_billing_view_access(self):
        self.client.login(username='school_admin_billing', password='password')
        response = self.client.get(reverse('subscriptions:billing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "14")
        self.assertContains(response, "Days Remaining")

    def test_simulated_payment_post_flow(self):
        self.client.login(username='school_admin_billing', password='password')
        response = self.client.post(reverse('subscriptions:initiate_payment'), {'simulate': '1'})
        self.assertRedirects(response, reverse('subscriptions:billing'))

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)

    def test_subscription_expiration_middleware_lock(self):
        self.subscription.end_date = datetime.date.today() - datetime.timedelta(days=10)
        self.subscription.status = SubscriptionStatus.EXPIRED
        self.subscription.save()

        teacher_user = User.objects.create_user(
            username='teacher_sub_test',
            password='password',
            role=UserRole.TEACHER,
            school=self.school
        )
        self.client.login(username='teacher_sub_test', password='password')

        response = self.client.get(reverse('teacher_portal'))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Subscription Expired", status_code=403)

    def test_admin_can_access_billing_when_expired(self):
        # Even when expired, admin must be able to access billing to renew
        self.subscription.end_date = datetime.date.today() - datetime.timedelta(days=5)
        self.subscription.status = SubscriptionStatus.EXPIRED
        self.subscription.save()

        self.client.login(username='school_admin_billing', password='password')
        response = self.client.get(reverse('subscriptions:billing'))
        self.assertEqual(response.status_code, 200)

        # But admin is blocked from operational dashboard
        dash_response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(dash_response.status_code, 403)

    def test_dynamic_sync_locks_when_trial_reaches_zero_days(self):
        # Subscription is in TRIAL status in DB, but end_date has passed
        self.subscription.status = SubscriptionStatus.TRIAL
        self.subscription.end_date = datetime.date.today() - datetime.timedelta(days=1)
        self.subscription.save()

        # sync_status should dynamically transition it to EXPIRED
        self.subscription.sync_status()
        self.assertEqual(self.subscription.status, SubscriptionStatus.EXPIRED)
        self.assertFalse(self.subscription.is_usable())

    def test_super_admin_bypasses_expiration_lock(self):
        self.subscription.end_date = datetime.date.today() - datetime.timedelta(days=10)
        self.subscription.status = SubscriptionStatus.EXPIRED
        self.subscription.save()

        super_admin = User.objects.create_user(
            username='superadmin_test',
            email='sa@ams.edu.et',
            password='password',
            role=UserRole.SUPER_ADMIN,
            is_superuser=True,
            is_staff=True
        )
        self.client.login(username='superadmin_test', password='password')
        response = self.client.get(reverse('platform:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_per_seat_price_calculation(self):
        price = self.subscription.calculate_annual_price(student_count=100, staff_count=10)
        self.assertEqual(price, Decimal('8000.00'))
