from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.tenants.models import TenantAwareModel


class GradeScaleRule(TenantAwareModel):
    grade_letter = models.CharField(max_length=5)  # e.g., A+, A, B+, B, C, D, F
    min_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_score = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    gpa_point = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    remark = models.CharField(max_length=50, blank=True, null=True)  # Excellent, Very Good, etc.

    class Meta:
        unique_together = ('school', 'grade_letter')
        ordering = ['-min_score']

    def __str__(self):
        return f"{self.grade_letter} ({self.min_score}% - {self.max_score}%)"
