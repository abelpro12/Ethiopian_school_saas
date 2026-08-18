import datetime
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from apps.tenants.models import School, TenantAwareModel


class PlanTier(models.TextChoices):
    BASIC = 'BASIC', 'Basic (Up to 500 Students)'
    STANDARD = 'STANDARD', 'Standard (Up to 1,500 Students)'
    PREMIUM = 'PREMIUM', 'Premium (Unlimited/Enterprise)'


class SubscriptionPlan(models.Model):
    BILLING_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('YEARLY', 'Yearly'),
    ]
    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=20, choices=PlanTier.choices, unique=True, default=PlanTier.BASIC)
    max_students = models.IntegerField(default=500)
    max_teachers = models.IntegerField(default=30)
    max_sms_per_month = models.IntegerField(default=1000)
    max_storage_mb = models.IntegerField(default=5000)
    price_per_year_etb = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CHOICES, default='YEARLY')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.price_per_year_etb} ETB/yr"


class SubscriptionStatus(models.TextChoices):
    TRIAL = 'TRIAL', 'Trial Period'
    ACTIVE = 'ACTIVE', 'Active'
    PAST_DUE = 'PAST_DUE', 'Past Due'
    GRACE_PERIOD = 'GRACE_PERIOD', 'Grace Period'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    CANCELLED = 'CANCELLED', 'Cancelled'
    EXPIRED = 'EXPIRED', 'Expired'


class SchoolSubscription(models.Model):
    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIAL)
    start_date = models.DateField(default=datetime.date.today)
    end_date = models.DateField()
    grace_period_end_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    # Per-Student & Per-Staff Seat Pricing Configuration
    price_per_student_etb = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('50.00'))
    price_per_staff_etb = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('100.00'))
    base_fee_etb = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('2000.00'))

    max_students_limit = models.IntegerField(default=500)
    max_staff_limit = models.IntegerField(default=50)

    custom_annual_price_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def calculate_annual_price(self, student_count=None, staff_count=None):
        if self.custom_annual_price_override and self.custom_annual_price_override > Decimal('0.00'):
            return self.custom_annual_price_override

        st_count = student_count if student_count is not None else self.max_students_limit
        stf_count = staff_count if staff_count is not None else self.max_staff_limit

        student_cost = Decimal(st_count) * self.price_per_student_etb
        staff_cost = Decimal(stf_count) * self.price_per_staff_etb

        return student_cost + staff_cost + self.base_fee_etb

    @property
    def current_calculated_price(self):
        from apps.students.models import StudentProfile
        from apps.accounts.models import User, UserRole

        active_students = StudentProfile.objects.filter(school=self.school).count()
        active_staff = User.objects.filter(
            school=self.school,
            role__in=[UserRole.TEACHER, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.LIBRARIAN]
        ).count()

        st_count = max(active_students, 10)
        stf_count = max(active_staff, 1)

        return self.calculate_annual_price(st_count, stf_count)

    @property
    def pricing_breakdown(self):
        from apps.students.models import StudentProfile
        from apps.accounts.models import User, UserRole

        active_students = StudentProfile.objects.filter(school=self.school).count()
        active_staff = User.objects.filter(
            school=self.school,
            role__in=[UserRole.TEACHER, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.LIBRARIAN]
        ).count()

        student_subtotal = Decimal(active_students) * self.price_per_student_etb
        staff_subtotal = Decimal(active_staff) * self.price_per_staff_etb

        total = student_subtotal + staff_subtotal + self.base_fee_etb
        if self.custom_annual_price_override and self.custom_annual_price_override > Decimal('0.00'):
            total = self.custom_annual_price_override

        return {
            'active_students': active_students,
            'price_per_student': self.price_per_student_etb,
            'student_subtotal': student_subtotal,
            'active_staff': active_staff,
            'price_per_staff': self.price_per_staff_etb,
            'staff_subtotal': staff_subtotal,
            'base_fee': self.base_fee_etb,
            'total_annual_price': total,
        }

    def sync_status(self):
        """Automatically checks and updates subscription status based on current date."""
        today = datetime.date.today()
        if self.end_date < today:
            if self.grace_period_end_date and today <= self.grace_period_end_date:
                if self.status != SubscriptionStatus.GRACE_PERIOD:
                    self.status = SubscriptionStatus.GRACE_PERIOD
                    self.save(update_fields=['status'])
            else:
                if self.status not in [SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED]:
                    self.status = SubscriptionStatus.EXPIRED
                    self.save(update_fields=['status'])
        elif self.status == SubscriptionStatus.EXPIRED and self.end_date > today:
            self.status = SubscriptionStatus.ACTIVE
            self.save(update_fields=['status'])
        return self.status

    def is_usable(self):
        today = datetime.date.today()
        if self.status in [SubscriptionStatus.SUSPENDED, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED]:
            if self.status == SubscriptionStatus.GRACE_PERIOD and self.grace_period_end_date and today <= self.grace_period_end_date:
                return True
            return False
        if self.end_date < today:
            if self.status == SubscriptionStatus.GRACE_PERIOD and self.grace_period_end_date and today <= self.grace_period_end_date:
                return True
            return False
        return self.status in [SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE_PERIOD]

    @property
    def days_remaining(self):
        if not self.end_date:
            return 0
        diff = (self.end_date - datetime.date.today()).days
        return max(0, diff)

    @property
    def is_in_trial(self):
        return self.status == SubscriptionStatus.TRIAL and self.days_remaining > 0

    @property
    def is_expired(self):
        return not self.is_usable()

    @property
    def status_badge_class(self):
        if self.days_remaining <= 0:
            return 'bg-red-500/20 text-red-400 border-red-500/30'
        elif self.days_remaining <= 7:
            return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
        elif self.status == SubscriptionStatus.TRIAL:
            return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'

    def extend_subscription(self, days=365):
        today = datetime.date.today()
        base_date = self.end_date if (self.end_date and self.end_date >= today) else today
        self.end_date = base_date + datetime.timedelta(days=days)
        self.status = SubscriptionStatus.ACTIVE
        self.save()

    def __str__(self):
        return f"{self.school.name} - {self.plan.name} ({self.status})"


class SubscriptionPayment(TenantAwareModel):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]
    tx_ref = models.CharField(max_length=100, unique=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='CHAPA')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    receipt_no = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Subscription Payment {self.tx_ref} ({self.amount_paid} ETB) - {self.status}"


class TenantUsageMeter(TenantAwareModel):
    current_students_count = models.IntegerField(default=0)
    current_teachers_count = models.IntegerField(default=0)
    sms_sent_this_month = models.IntegerField(default=0)
    storage_used_mb = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    last_reset_date = models.DateField(default=datetime.date.today)

    def check_limits_warning(self, plan: SubscriptionPlan):
        """
        Returns list of limit warning messages if usage > 85% of allowed limit.
        """
        warnings = []
        if self.current_students_count >= (plan.max_students * 0.85):
            warnings.append(f"Student limit warning: {self.current_students_count}/{plan.max_students} students used.")
        if self.current_teachers_count >= (plan.max_teachers * 0.85):
            warnings.append(f"Teacher limit warning: {self.current_teachers_count}/{plan.max_teachers} teachers used.")
        if self.sms_sent_this_month >= (plan.max_sms_per_month * 0.85):
            warnings.append(f"SMS limit warning: {self.sms_sent_this_month}/{plan.max_sms_per_month} SMS sent this month.")
        return warnings

    def __str__(self):
        return f"Usage Meter for {self.school.code}: {self.current_students_count} students, {self.sms_sent_this_month} SMS"
