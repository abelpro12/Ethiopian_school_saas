from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.students.models import StudentProfile
from apps.academics.models import AcademicYear


class IncidentSeverity(models.TextChoices):
    MINOR = 'MINOR', 'Minor'
    MODERATE = 'MODERATE', 'Moderate'
    SERIOUS = 'SERIOUS', 'Serious'
    CRITICAL = 'CRITICAL', 'Critical'


class IncidentCategory(models.TextChoices):
    MISCONDUCT = 'MISCONDUCT', 'Misconduct / Disruptive Behaviour'
    BULLYING = 'BULLYING', 'Bullying / Harassment'
    FIGHTING = 'FIGHTING', 'Physical Altercation / Fighting'
    CHEATING = 'CHEATING', 'Academic Dishonesty / Cheating'
    DAMAGE = 'DAMAGE', 'Property Damage'
    ABSENCE = 'ABSENCE', 'Unauthorized Absence / Truancy'
    DRESS_CODE = 'DRESS_CODE', 'Dress Code Violation'
    SUBSTANCE = 'SUBSTANCE', 'Substance Use'
    WEAPONS = 'WEAPONS', 'Weapons / Dangerous Items'
    OTHER = 'OTHER', 'Other'


class IncidentStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open / Under Review'
    RESOLVED = 'RESOLVED', 'Resolved'
    ESCALATED = 'ESCALATED', 'Escalated to Principal'
    DISMISSED = 'DISMISSED', 'Dismissed'


class DisciplinaryActionType(models.TextChoices):
    VERBAL_WARNING = 'VERBAL_WARNING', 'Verbal Warning'
    WRITTEN_WARNING = 'WRITTEN_WARNING', 'Written Warning'
    DETENTION = 'DETENTION', 'Detention'
    PARENT_CALL = 'PARENT_CALL', 'Parent Notified / Called'
    SUSPENSION = 'SUSPENSION', 'Suspension (Days)'
    COMMUNITY_SERVICE = 'COMMUNITY_SERVICE', 'Community Service'
    EXPULSION = 'EXPULSION', 'Expulsion Recommended'
    OTHER = 'OTHER', 'Other Action'


class DisciplinaryIncident(TenantAwareModel):
    """Records a specific disciplinary incident involving one or more students."""
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='incidents')
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=IncidentCategory.choices, default=IncidentCategory.MISCONDUCT)
    severity = models.CharField(max_length=20, choices=IncidentSeverity.choices, default=IncidentSeverity.MINOR)
    status = models.CharField(max_length=20, choices=IncidentStatus.choices, default=IncidentStatus.OPEN)
    description = models.TextField()
    incident_date = models.DateField()
    location = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Classroom, Corridor, Canteen")
    students_involved = models.ManyToManyField(StudentProfile, related_name='disciplinary_incidents', blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reported_incidents')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_incidents')
    parent_notified = models.BooleanField(default=False)
    parent_notification_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title} ({self.incident_date})"


class DisciplinaryAction(TenantAwareModel):
    """A specific action taken as a result of an incident."""
    incident = models.ForeignKey(DisciplinaryIncident, on_delete=models.CASCADE, related_name='actions')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='disciplinary_actions')
    action_type = models.CharField(max_length=30, choices=DisciplinaryActionType.choices, default=DisciplinaryActionType.VERBAL_WARNING)
    description = models.TextField(blank=True, null=True)
    suspension_days = models.IntegerField(default=0, help_text="Number of suspension days (if applicable)")
    effective_date = models.DateField(null=True, blank=True)
    administered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_action_type_display()} for {self.student.full_name} (Incident: {self.incident.title})"
