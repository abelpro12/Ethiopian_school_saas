from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User


class AuditLog(TenantAwareModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)  # LOGIN, MARK_CHANGE, FEE_OVERRIDE, RESULT_PUBLISH
    object_type = models.CharField(max_length=100, blank=True, null=True)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    before_value = models.JSONField(default=dict, blank=True)
    after_value = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.school.code}] {self.user} - {self.action} at {self.timestamp}"


class LoginAuditLog(TenantAwareModel):
    LOGIN_STATUS = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('SUSPICIOUS', 'Suspicious'),
        ('BLOCKED', 'Blocked'),
    ]
    username_attempted = models.CharField(max_length=150)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_audits')
    status = models.CharField(max_length=20, choices=LOGIN_STATUS, default='SUCCESS')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    failure_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Login {self.status} for {self.username_attempted} from {self.ip_address} at {self.timestamp}"
