import uuid
from django.db import models
from apps.tenants.models import TenantAwareModel, School


class DocumentType(models.TextChoices):
    REPORT_CARD = 'REPORT_CARD', 'Report Card'
    RECEIPT = 'RECEIPT', 'Payment Receipt'
    TRANSCRIPT = 'TRANSCRIPT', 'Student Transcript'
    CERTIFICATE = 'CERTIFICATE', 'Certificate'


class DocumentStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    GENERATED = 'GENERATED', 'Generated'
    APPROVED = 'APPROVED', 'Approved'
    PUBLISHED = 'PUBLISHED', 'Published'
    REVOKED = 'REVOKED', 'Revoked'


class DocumentVerification(TenantAwareModel):
    document_type = models.CharField(max_length=50, choices=DocumentType.choices)
    verification_token = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    doc_number = models.CharField(max_length=100)
    version = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.PUBLISHED)
    metadata_json = models.JSONField(default=dict)
    is_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_type} Verification [{self.doc_number}] v{self.version} ({self.status})"


class RegionalReportTemplate(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True, related_name='regional_templates')
    name = models.CharField(max_length=200)  # e.g., "Oromia Regional Annual Census Template"
    config_json = models.JSONField(default=dict)  # Configurable metric toggles
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report Template: {self.name}"

class HistoricalTranscriptYear(models.Model):
    """
    Stores legacy transcript data for students who completed earlier grades 
    before the school started using the SaaS.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='historical_transcripts')
    student = models.ForeignKey('students.StudentProfile', on_delete=models.CASCADE, related_name='historical_transcripts')
    
    grade_name = models.CharField(max_length=50, help_text="e.g. Grade 9, Grade 10")
    grade_level = models.IntegerField(help_text="Numeric level for sorting, e.g. 9, 10")
    academic_year_name = models.CharField(max_length=50, help_text="e.g. 2023/2024")
    
    # JSON structure: [{"name": "Math", "sem1": 85.0, "sem2": 90.0, "avg": 87.5, "letter": "A"}, ...]
    subjects_json = models.JSONField(default=list)
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['grade_level']
        unique_together = ('student', 'grade_level')

    def __str__(self):
        return f"Historical {self.grade_name} - {self.student.full_name}"
