import os
from django.db import models
from django.core.exceptions import ValidationError
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.students.models import StudentProfile
from apps.teachers.models import TeacherProfile


def validate_file_extension_and_size(value):
    ext = os.path.splitext(value.name)[1].lower()
    valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.docx']
    if ext not in valid_extensions:
        raise ValidationError(f"Unsupported file extension '{ext}'. Allowed: {', '.join(valid_extensions)}")
    
    max_size = 10 * 1024 * 1024  # 10MB limit
    if value.size > max_size:
        raise ValidationError("File size exceeds 10MB limit.")


class DocumentCategory(models.TextChoices):
    ADMISSION_DOC = 'ADMISSION_DOC', 'Student Admission Document'
    BIRTH_CERTIFICATE = 'BIRTH_CERTIFICATE', 'Birth Certificate'
    TEACHER_CREDENTIAL = 'TEACHER_CREDENTIAL', 'Teacher Qualification Credential'
    STUDENT_TRANSCRIPT = 'STUDENT_TRANSCRIPT', 'Official Transcript'
    OTHER = 'OTHER', 'Other School Document'


class SchoolDocument(TenantAwareModel):
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=DocumentCategory.choices, default=DocumentCategory.OTHER)
    file = models.FileField(upload_to='school_documents/', validators=[validate_file_extension_and_size])
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='documents')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"
