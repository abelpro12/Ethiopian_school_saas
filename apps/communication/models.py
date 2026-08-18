from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User, UserRole
from apps.academics.models import Grade, Section


class AnnouncementTarget(models.TextChoices):
    SCHOOL = 'SCHOOL', 'Entire School'
    GRADE = 'GRADE', 'Specific Grade'
    SECTION = 'SECTION', 'Specific Section'
    PARENTS = 'PARENTS', 'All Parents'
    STUDENTS = 'STUDENTS', 'All Students'
    TEACHERS = 'TEACHERS', 'All Teachers'


class Announcement(TenantAwareModel):
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_type = models.CharField(max_length=30, choices=AnnouncementTarget.choices, default=AnnouncementTarget.SCHOOL)
    target_role = models.CharField(max_length=50, choices=UserRole.choices, null=True, blank=True)
    target_grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True)
    target_section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.school.code}] {self.title} ({self.target_type})"


class NotificationChannel(models.TextChoices):
    IN_APP = 'IN_APP', 'In-App'
    SMS = 'SMS', 'SMS'
    TELEGRAM = 'TELEGRAM', 'Telegram'
    EMAIL = 'EMAIL', 'Email'


class NotificationLog(TenantAwareModel):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices, default=NotificationChannel.IN_APP)
    subject = models.CharField(max_length=200, blank=True, null=True)
    message = models.TextField()
    status = models.CharField(max_length=20, default='SENT')  # PENDING, SENT, FAILED, RETRYING
    retry_count = models.IntegerField(default=0)
    failure_reason = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification to {self.recipient.username} via {self.channel} ({self.status})"


class TelegramAccountLink(TenantAwareModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='telegram_link')
    telegram_chat_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    verification_code = models.CharField(max_length=20, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Telegram link for {self.user.username} (Verified: {self.is_verified})"


class UserNotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences')
    attendance_alerts = models.BooleanField(default=True)
    payment_alerts = models.BooleanField(default=True)
    announcement_alerts = models.BooleanField(default=True)
    marketing_alerts = models.BooleanField(default=False)

    def __str__(self):
        return f"Preferences for {self.user.username}"
