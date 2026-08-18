from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.academics.models import AcademicYear, AcademicPeriod, Section, Stream, Grade
from apps.students.models import StudentProfile


class StudentRanking(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    total_score = models.DecimalField(max_digits=7, decimal_places=2)
    average_score = models.DecimalField(max_digits=5, decimal_places=2)
    section_rank = models.IntegerField()
    stream_rank = models.IntegerField()
    grade_rank = models.IntegerField()

    class Meta:
        unique_together = ('school', 'academic_year', 'period', 'student')
        ordering = ['section_rank']

    def __str__(self):
        return f"{self.student.full_name}: Sec Rank {self.section_rank}, Avg {self.average_score}%"
