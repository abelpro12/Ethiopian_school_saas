from django.db import models
from apps.accounts.models import User
from apps.tenants.models import School
from apps.subscriptions.models import SubscriptionPlan

class PlatformFeatureFlag(models.Model):
    SCOPE_CHOICES = [
        ('GLOBAL', 'Global (All Schools)'),
        ('PLAN', 'Subscription Plan'),
        ('SCHOOL', 'Specific School'),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100, unique=True, help_text="e.g. messaging, chapa_payments")
    is_active = models.BooleanField(default=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default='GLOBAL')
    
    # Optional targeting based on scope
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, null=True, blank=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('code', 'scope', 'plan', 'school')

    def __str__(self):
        target = "Global"
        if self.scope == 'PLAN': target = f"Plan: {self.plan}"
        if self.scope == 'SCHOOL': target = f"School: {self.school}"
        status = "ON" if self.is_active else "OFF"
        return f"{self.name} ({target}) - {status}"

    @classmethod
    def is_feature_active(cls, code, school=None, plan=None):
        try:
            flag = cls.objects.get(code=code)
            if not flag.is_active:
                return False
            if flag.scope == 'GLOBAL':
                return True
            if flag.scope == 'PLAN':
                # Target plan might be derived from school if not provided
                check_plan = plan or (school.subscription.plan if (school and hasattr(school, 'subscription')) else None)
                return check_plan == flag.plan
            if flag.scope == 'SCHOOL':
                return school == flag.school
            return False
        except cls.DoesNotExist:
            return False


class PlatformAnnouncement(models.Model):
    TARGET_CHOICES = [
        ('ALL', 'All Schools'),
        ('PLAN', 'Selected Plan'),
        ('SCHOOL', 'Selected School'),
        ('ADMINS', 'Platform Administrators'),
    ]

    title = models.CharField(max_length=200)
    content = models.TextField()
    target_audience = models.CharField(max_length=20, choices=TARGET_CHOICES, default='ALL')
    
    # Optional targeting
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, null=True, blank=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_target_audience_display()})"


class PlatformAuditLog(models.Model):
    SEVERITY_CHOICES = [
        ('INFO', 'Information'),
        ('LOW', 'Low Warning'),
        ('MEDIUM', 'Medium Alert'),
        ('HIGH', 'High Alert'),
        ('CRITICAL', 'Critical Event'),
    ]

    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='platform_audit_logs')
    action = models.CharField(max_length=150)
    target_object = models.CharField(max_length=255, blank=True, null=True)
    target_school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    reason = models.CharField(max_length=255, blank=True, null=True)
    before_state = models.JSONField(default=dict, blank=True, null=True)
    after_state = models.JSONField(default=dict, blank=True, null=True)
    
    is_success = models.BooleanField(default=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='INFO')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.timestamp}"
