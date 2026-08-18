from django.core.exceptions import PermissionDenied
from apps.students.models import StudentProfile
from apps.teachers.models import TeacherProfile
from .models import SchoolSubscription, SubscriptionStatus, TenantUsageMeter


class SubscriptionService:
    @staticmethod
    def check_student_limit(school):
        """
        Enforces tenant usage metering student limit against subscribed plan entitlements.
        """
        if not school:
            return True

        sub = SchoolSubscription.objects.filter(school=school, status=SubscriptionStatus.ACTIVE).first()
        if not sub:
            return True  # Dev default allow

        active_students = StudentProfile.objects.filter(school=school).count()
        if active_students >= sub.plan.max_students:
            raise PermissionDenied(f"Student limit of {sub.plan.max_students} reached for subscription plan '{sub.plan.name}'. Please upgrade.")
        return True

    @staticmethod
    def check_teacher_limit(school):
        """
        Enforces tenant usage metering teacher limit against subscribed plan entitlements.
        """
        if not school:
            return True

        sub = SchoolSubscription.objects.filter(school=school, status=SubscriptionStatus.ACTIVE).first()
        if not sub:
            return True

        active_teachers = TeacherProfile.objects.filter(school=school).count()
        if active_teachers >= sub.plan.max_teachers:
            raise PermissionDenied(f"Teacher limit of {sub.plan.max_teachers} reached for subscription plan '{sub.plan.name}'. Please upgrade.")
        return True


import uuid
import datetime
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.audit.services import AuditService
from .models import SubscriptionPayment, SubscriptionPlan


class SubscriptionPaymentService:
    @staticmethod
    def initialize_subscription_payment(school, user, amount: Decimal = None):
        """
        Initializes a Chapa payment transaction for subscription renewal.
        """
        sub = getattr(school, 'subscription', None)
        if not sub:
            plan = SubscriptionPlan.objects.filter(is_active=True).first()
            if not plan:
                plan = SubscriptionPlan.objects.create(name="EthioSchool SaaS Subscription", price_per_year_etb=Decimal('25000.00'))
            sub = SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SubscriptionStatus.TRIAL,
                end_date=datetime.date.today() + datetime.timedelta(days=14)
            )

        pay_amount = amount or sub.plan.price_per_year_etb or Decimal('25000.00')
        tx_ref = f"SUB-PAY-{uuid.uuid4().hex[:12].upper()}"

        payment = SubscriptionPayment.objects.create(
            school=school,
            tx_ref=tx_ref,
            amount_paid=pay_amount,
            payment_method='CHAPA',
            status='PENDING'
        )

        checkout_url = f"https://checkout.chapa.co/checkout/payment/{tx_ref}"

        return {
            'status': 'success',
            'checkout_url': checkout_url,
            'tx_ref': tx_ref,
            'payment_id': str(payment.id),
            'amount': pay_amount
        }

    @staticmethod
    @transaction.atomic
    def process_subscription_webhook(tx_ref: str, payment_status: str):
        """
        Processes Chapa webhook/callback for subscription payment idempotently.
        Extends subscription by 365 days on success.
        """
        try:
            payment = SubscriptionPayment.objects.select_for_update().get(tx_ref=tx_ref)
        except SubscriptionPayment.DoesNotExist:
            raise ValueError(f"Subscription payment reference {tx_ref} not found.")

        if payment.status == 'SUCCESS':
            return payment

        if payment_status.upper() in ['SUCCESS', 'SUCCESSFUL']:
            payment.status = 'SUCCESS'
            payment.receipt_no = f"REC-SUB-{uuid.uuid4().hex[:10].upper()}"
            payment.paid_at = timezone.now()
            payment.save()

            # Extend school subscription
            sub = payment.school.subscription
            sub.extend_subscription(days=365)

            # Audit log
            AuditService.log_action(
                school=payment.school,
                user=None,
                action='SUBSCRIPTION_RENEWED',
                after_val={'details': f"Subscription renewed for 365 days via Chapa ({payment.amount_paid} ETB). New end date: {sub.end_date}"}
            )
            return payment
        else:
            payment.status = 'FAILED'
            payment.save()
            return payment
