import datetime
from django.db import models
from django.core.exceptions import ValidationError
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Section
from apps.students.models import StudentProfile


class ExamType(models.TextChoices):
    REGULAR = 'REGULAR', 'Regular'
    MAKEUP = 'MAKEUP', 'Make-up'
    SUPPLEMENTARY = 'SUPPLEMENTARY', 'Supplementary'


class ExamStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    ONGOING = 'ONGOING', 'Ongoing'
    COMPLETED = 'COMPLETED', 'Completed'
    LOCKED = 'LOCKED', 'Locked'


class Exam(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='exams')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='exams')
    name = models.CharField(max_length=100)  # e.g., "AcademicPeriod 1 Final Exam"
    exam_type = models.CharField(max_length=20, choices=ExamType.choices, default=ExamType.REGULAR)
    status = models.CharField(max_length=20, choices=ExamStatus.choices, default=ExamStatus.DRAFT)

    class Meta:
        unique_together = ('school', 'academic_year', 'period', 'name')

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class ExamSchedule(TenantAwareModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='schedules')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exam_schedules')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='exam_schedules')
    exam_date = models.DateField()
    room = models.CharField(max_length=50, blank=True, null=True)
    invigilator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ('school', 'exam', 'subject', 'section')

    def clean(self):
        """
        Invigilator Conflict Detection (Point 20):
        Prevents teacher from being assigned as invigilator in two halls/rooms on the same date.
        """
        if self.invigilator and self.exam_date:
            conflict = ExamSchedule.objects.filter(
                school=self.school,
                invigilator=self.invigilator,
                exam_date=self.exam_date
            ).exclude(pk=self.pk).first()

            if conflict:
                raise ValidationError(f"Invigilator {self.invigilator.username} is already assigned to Room '{conflict.room}' on {self.exam_date}.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.exam.name} - {self.subject.code} ({self.section.name})"


class ExamMark(TenantAwareModel):
    exam_schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name='marks')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='exam_marks')
    mark_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('school', 'exam_schedule', 'student')

    def __str__(self):
        return f"{self.student.full_name} - {self.exam_schedule}: {self.mark_obtained}"
