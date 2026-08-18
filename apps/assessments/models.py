from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject
from apps.enrollment.models import StudentEnrollment

class MarkStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVED = 'APPROVED', 'Approved'
    PUBLISHED = 'PUBLISHED', 'Published'
    LOCKED = 'LOCKED', 'Locked'

class AssessmentComponent(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='assessment_components')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='assessment_components')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assessment_components')
    name = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.0)

    class Meta:
        unique_together = ('school', 'academic_year', 'period', 'subject', 'name')

    def __str__(self):
        return f"{self.subject.code} - {self.name} ({self.weight}%)"


class StudentMark(TenantAwareModel):
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='marks')
    assessment_component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE, related_name='student_marks')
    mark_value = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=MarkStatus.choices, default=MarkStatus.DRAFT)
    entered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'enrollment', 'assessment_component')
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', 'enrollment', 'status']),
        ]

    def __str__(self):
        return f"{self.enrollment.student.full_name} - {self.assessment_component.name}: {self.mark_value}"


class MarkChangeAudit(TenantAwareModel):
    mark = models.ForeignKey(StudentMark, on_delete=models.CASCADE, related_name='change_audits')
    old_value = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_value = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField()
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Mark Change Audit on {self.mark.id}: {self.old_value} -> {self.new_value}"

class ResultCorrectionRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'

class ResultCorrectionRequest(TenantAwareModel):
    mark = models.ForeignKey(StudentMark, on_delete=models.CASCADE, related_name='correction_requests')
    requested_value = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.TextField()
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mark_correction_requests')
    status = models.CharField(max_length=20, choices=ResultCorrectionRequestStatus.choices, default=ResultCorrectionRequestStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_mark_corrections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result Correction Request for {self.mark} to {self.requested_value}"


class ConductGrade(models.TextChoices):
    A = 'A', 'Excellent (A)'
    B = 'B', 'Good (B)'
    C = 'C', 'Satisfactory (C)'
    D = 'D', 'Needs Improvement (D)'


class StudentConduct(TenantAwareModel):
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='conduct_records')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='conduct_records')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='conduct_records')
    grade = models.CharField(max_length=2, choices=ConductGrade.choices, default=ConductGrade.B)
    remarks = models.TextField(blank=True, help_text="Teacher's remarks on conduct")
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_conducts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'enrollment', 'academic_year', 'period')

    def __str__(self):
        return f"{self.enrollment.student.full_name} Conduct: {self.get_grade_display()} - {self.academic_year.name} ({self.period.name})"


class AcademicPeriodResult(TenantAwareModel):
    """
    Stores the final computed result for a student in a specific period.
    Populated when the AcademicPeriod-Close Wizard is run by admin.
    """
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='period_results')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='student_results')
    total_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    subjects_passed = models.IntegerField(default=0)
    subjects_failed = models.IntegerField(default=0)
    
    # Attendance Tracking
    attendance_present = models.IntegerField(default=0)
    attendance_absent = models.IntegerField(default=0)
    attendance_late = models.IntegerField(default=0)
    
    section_rank = models.IntegerField(null=True, blank=True)
    grade_rank = models.IntegerField(null=True, blank=True)
    conduct_grade = models.CharField(max_length=2, blank=True, null=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    results_json = models.JSONField(default=dict, help_text="Detailed per-subject results cache")
    computed_at = models.DateTimeField(auto_now=True)

    @property
    def formatted_results(self):
        """
        Safely returns a list of subject result dicts regardless of whether
        results_json was stored as a list or a dict.
        """
        data = self.results_json
        if not data:
            return []
        if isinstance(data, list):
            res = []
            for item in data:
                if isinstance(item, dict):
                    norm = float(item.get('normalized', item.get('total', 0)))
                    tot = float(item.get('raw_score', item.get('total', 0)))
                    letter = item.get('letter') or ('A+' if norm >= 90 else ('A' if norm >= 83 else ('B' if norm >= 75 else ('C' if norm >= 65 else ('D' if norm >= 50 else 'F')))))
                    is_pass = item.get('passed') if 'passed' in item else (norm >= 50)
                    res.append({
                        'code': item.get('code', ''),
                        'name': item.get('name', 'Subject'),
                        'raw_score': round(tot, 2),
                        'normalized': round(norm, 2),
                        'letter': letter,
                        'passed': is_pass
                    })
            return res
        elif isinstance(data, dict):
            res = []
            for k, item in data.items():
                if isinstance(item, dict):
                    tot = float(item.get('total', item.get('raw_score', 0)))
                    norm = float(item.get('normalized', tot))
                    letter = item.get('letter') or ('A+' if norm >= 90 else ('A' if norm >= 83 else ('B' if norm >= 75 else ('C' if norm >= 65 else ('D' if norm >= 50 else 'F')))))
                    is_pass = item.get('passed') if 'passed' in item else (norm >= 50)
                    res.append({
                        'code': item.get('code', ''),
                        'name': item.get('name', f"Subject {k}"),
                        'raw_score': round(tot, 2),
                        'normalized': round(norm, 2),
                        'letter': letter,
                        'passed': is_pass
                    })
            return res
        return []

    def __str__(self):
        return f"{self.enrollment.student.full_name} - {self.period.name}: Avg {self.average_score}% (Rank #{self.section_rank})"


class AcademicPeriodPublishLog(TenantAwareModel):
    """Audit log of period result publish events."""
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='publish_logs')
    published_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    students_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    published_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AcademicPeriod Close: {self.period.name} by {self.published_by} on {self.published_at.strftime('%Y-%m-%d')}"


class SupplementaryExamStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    TAKEN = 'TAKEN', 'Taken'
    PASSED = 'PASSED', 'Passed'
    FAILED = 'FAILED', 'Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class SupplementaryExam(TenantAwareModel):
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='supplementary_exams')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='supplementary_exams')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='supplementary_exams')
    original_score = models.DecimalField(max_digits=5, decimal_places=2)
    supplementary_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    final_effective_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=SupplementaryExamStatus.choices, default=SupplementaryExamStatus.SCHEDULED)
    exam_date = models.DateField(null=True, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'enrollment', 'subject', 'academic_year')

    def __str__(self):
        return f"Supplementary Exam for {self.enrollment.student.full_name} ({self.subject.code}): {self.original_score} -> {self.supplementary_score or 'Pending'}"


class PromotionStatus(models.TextChoices):
    PROMOTED = 'PROMOTED', 'Promoted'
    REPEATED = 'REPEATED', 'Repeated'
    PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Review (Caution)'


class AnnualResult(TenantAwareModel):
    """
    Stores the final computed annual result for a student in an Academic Year.
    Used by the Annual Promotion Engine.
    """
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='annual_results')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='annual_results_agg')
    total_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Attendance Tracking
    attendance_present = models.IntegerField(default=0)
    attendance_absent = models.IntegerField(default=0)
    attendance_late = models.IntegerField(default=0)
    
    section_rank = models.IntegerField(null=True, blank=True)
    grade_rank = models.IntegerField(null=True, blank=True)
    promotion_status = models.CharField(max_length=20, choices=PromotionStatus.choices, default=PromotionStatus.PENDING_REVIEW)
    results_json = models.JSONField(default=dict, help_text="Detailed per-subject annual results cache")
    is_locked = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'enrollment', 'academic_year')

    def __str__(self):
        return f"{self.enrollment.student.full_name} - {self.academic_year.name}: {self.promotion_status}"
