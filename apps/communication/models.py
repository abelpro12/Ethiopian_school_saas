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


# ============================================================================
# Priority 3B: Configurable SMS Templates, Parent Meeting Requests & Payment Reminders
# ============================================================================

class SMSTemplateType(models.TextChoices):
    STUDENT_ABSENCE = 'STUDENT_ABSENCE', 'Student Absence Alert'
    PARENT_MEETING = 'PARENT_MEETING', 'Parent Meeting Invitation'
    PAYMENT_REMINDER = 'PAYMENT_REMINDER', 'Payment Due Warning'
    PAYMENT_OVERDUE = 'PAYMENT_OVERDUE', 'Payment Overdue Notice'
    BELOW_AVERAGE_ALERT = 'BELOW_AVERAGE_ALERT', 'Below Average Performance Alert'
    GENERAL_ANNOUNCEMENT = 'GENERAL_ANNOUNCEMENT', 'General Announcement'
    CUSTOM = 'CUSTOM', 'Custom Message'


class SMSTemplate(TenantAwareModel):
    """
    Tenant-configurable SMS message templates supporting English and Amharic.
    Placeholders: {student_name}, {date}, {school_name}, {reason},
                 {invoice_number}, {amount}, {due_date},
                 {meeting_date}, {meeting_time}, {location}, {contact_person}, {contact_phone}
    """
    name = models.CharField(max_length=150)
    template_type = models.CharField(max_length=50, choices=SMSTemplateType.choices)
    body_en = models.TextField(help_text="English message body with {placeholders}")
    body_am = models.TextField(help_text="Amharic message body with {placeholders}")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'template_type')
        ordering = ['template_type']

    def __str__(self):
        return f"[{self.school.code}] {self.get_template_type_display()} ({self.name})"


class ParentMeetingCategory(models.TextChoices):
    ACADEMIC = 'ACADEMIC', 'Academic Performance'
    CONDUCT = 'CONDUCT', 'Conduct & Behavior'
    DISCIPLINARY = 'DISCIPLINARY', 'Disciplinary Concern'
    ATTENDANCE = 'ATTENDANCE', 'Attendance Issue'
    HEALTH = 'HEALTH', 'Health / Well-being'
    ADMINISTRATIVE = 'ADMINISTRATIVE', 'Administrative / Tuition'
    OTHER = 'OTHER', 'General / Other'


class ParentMeetingStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    RESCHEDULED = 'RESCHEDULED', 'Rescheduled'


class ParentMeetingRequest(TenantAwareModel):
    """
    Formal parent meeting invitations requested by teachers, principals, or staff.
    Dispatches automated SMS invitations and records meeting outcomes.
    """
    student = models.ForeignKey('students.StudentProfile', on_delete=models.CASCADE, related_name='parent_meetings')
    parent = models.ForeignKey('parents.ParentProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='meeting_requests')
    category = models.CharField(max_length=30, choices=ParentMeetingCategory.choices, default=ParentMeetingCategory.ACADEMIC)
    reason = models.TextField()
    meeting_date = models.DateField()
    meeting_time = models.TimeField()
    location = models.CharField(max_length=150, default="Principal Office / Staff Conference Room")
    contact_person = models.CharField(max_length=150)
    contact_phone = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, choices=ParentMeetingStatus.choices, default=ParentMeetingStatus.SCHEDULED)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_parent_meetings')
    sms_sent = models.BooleanField(default=False)
    outcome_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-meeting_date', '-meeting_time']

    def __str__(self):
        return f"Meeting for {self.student.full_name} on {self.meeting_date} ({self.status})"


class PaymentReminderStage(models.TextChoices):
    SEVEN_DAYS_BEFORE = '7_DAYS_BEFORE', '7 Days Before Due Date'
    THREE_DAYS_BEFORE = '3_DAYS_BEFORE', '3 Days Before Due Date'
    DUE_DATE = 'DUE_DATE', 'On Due Date'
    OVERDUE = 'OVERDUE', 'Overdue Notice'


class PaymentReminderLog(TenantAwareModel):
    """
    Tracks automated invoice reminder SMS dispatches to avoid repeated spam.
    Ensures each invoice stage (7d, 3d, due, overdue) is only alerted once.
    """
    invoice = models.ForeignKey('finance.StudentInvoice', on_delete=models.CASCADE, related_name='reminder_logs')
    reminder_stage = models.CharField(max_length=30, choices=PaymentReminderStage.choices)
    recipient_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_payment_reminders')
    recipient_phone = models.CharField(max_length=50)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='SENT')

    class Meta:
        unique_together = ('school', 'invoice', 'reminder_stage')
        ordering = ['-sent_at']

    def __str__(self):
        return f"Reminder {self.reminder_stage} for Invoice {self.invoice.invoice_number} ({self.recipient_phone})"

