import datetime
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Subject, Section, Grade


class HomeworkStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active / Open'
    CLOSED = 'CLOSED', 'Closed / Past Due'
    DRAFT = 'DRAFT', 'Draft'


class HomeworkAssignment(TenantAwareModel):
    """A homework or assignment posted by a teacher."""
    title = models.CharField(max_length=200)
    description = models.TextField()
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='homework_assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='homework_assignments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='homework_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_homework')
    assigned_date = models.DateField(default=datetime.date.today)
    due_date = models.DateField()
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=10.0, null=True, blank=True)
    status = models.CharField(max_length=20, choices=HomeworkStatus.choices, default=HomeworkStatus.ACTIVE)
    attachment = models.FileField(upload_to='homework_attachments/', blank=True, null=True)

    class Meta:
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.subject.code} - {self.title} (Due: {self.due_date})"

    @property
    def is_overdue(self):
        return self.due_date < datetime.date.today() and self.status == HomeworkStatus.ACTIVE

    @property
    def submission_count(self):
        return self.submissions.count()


class SubmissionStatus(models.TextChoices):
    SUBMITTED = 'SUBMITTED', 'Submitted'
    LATE = 'LATE', 'Submitted Late'
    GRADED = 'GRADED', 'Graded'
    MISSING = 'MISSING', 'Missing / Not Submitted'


class HomeworkSubmission(TenantAwareModel):
    """A student's submission for a homework assignment."""
    homework = models.ForeignKey(HomeworkAssignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='homework_submissions')
    notes = models.TextField(blank=True, null=True)
    attachment = models.FileField(upload_to='homework_submissions/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.SUBMITTED)
    marks_awarded = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    teacher_feedback = models.TextField(blank=True, null=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_homework')

    class Meta:
        unique_together = ('school', 'homework', 'student')

    def __str__(self):
        return f"{self.student.get_full_name()} - {self.homework.title}"
