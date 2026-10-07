from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Grade, Section
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


class MarkEntryLock(TenantAwareModel):
    """
    Granular mark entry locking mechanism.
    Supports locking mark entry by:
    - Grade (all sections and subjects within the grade)
    - Subject (all grades or specific grade/section)
    - Teacher (specific teacher account)
    - Section (specific class section)
    - Academic Year and Period (scoping lock to active term)
    """
    LOCK_TYPES = [
        ('GRADE', 'By Grade'),
        ('SUBJECT', 'By Subject'),
        ('TEACHER', 'By Teacher'),
        ('SECTION', 'By Section'),
        ('CUSTOM', 'Custom / Targeted'),
    ]

    lock_type = models.CharField(max_length=20, choices=LOCK_TYPES, default='CUSTOM')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_locks')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_locks')

    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')

    is_active = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. Grading deadline closed, Administrative review, etc.")
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_mark_locks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        desc = []
        if self.grade:
            desc.append(f"Grade: {self.grade.name}")
        if self.subject:
            desc.append(f"Subject: {self.subject.name}")
        if self.teacher:
            desc.append(f"Teacher: {self.teacher.get_full_name() or self.teacher.username}")
        if self.section:
            desc.append(f"Section: {self.section.name}")
        scope = ", ".join(desc) if desc else "General"
        status = "Locked" if self.is_active else "Unlocked"
        return f"[{self.school.code}] {scope} - {status}"

    @classmethod
    def check_lock(cls, school, academic_year=None, period=None, grade=None, subject=None, teacher=None, section=None):
        """
        Evaluates whether mark entry is locked for the given context.
        Returns a tuple: (is_locked: bool, reason: str, lock_rule: MarkEntryLock or None)
        """
        from apps.academics.models import PeriodStatus
        if period and getattr(period, 'status', None) == PeriodStatus.LOCKED:
            return True, f"Academic term '{period.name}' is globally locked by School Administration.", None

        if not school:
            return False, "", None

        locks_qs = cls.objects.filter(school=school, is_active=True)
        if academic_year:
            locks_qs = locks_qs.filter(models.Q(academic_year__isnull=True) | models.Q(academic_year=academic_year))
        if period:
            locks_qs = locks_qs.filter(models.Q(period__isnull=True) | models.Q(period=period))

        for lock in locks_qs:
            # Check Grade match
            if lock.grade and grade and lock.grade_id != getattr(grade, 'id', grade):
                continue
            if lock.grade and not grade:
                continue

            # Check Subject match
            if lock.subject and subject and lock.subject_id != getattr(subject, 'id', subject):
                continue
            if lock.subject and not subject:
                continue

            # Check Teacher match
            if lock.teacher and teacher and lock.teacher_id != getattr(teacher, 'id', teacher):
                continue
            if lock.teacher and not teacher:
                continue

            # Check Section match
            if lock.section and section and lock.section_id != getattr(section, 'id', section):
                continue
            if lock.section and not section:
                continue

            # Rule matched!
            if lock.grade or lock.subject or lock.teacher or lock.section or lock.period:
                scope_parts = []
                if lock.grade:
                    scope_parts.append(f"Grade {lock.grade.name}")
                if lock.subject:
                    scope_parts.append(f"Subject '{lock.subject.name}'")
                if lock.teacher:
                    scope_parts.append(f"Teacher {lock.teacher.get_full_name() or lock.teacher.username}")
                if lock.section:
                    scope_parts.append(f"Section {lock.section.name}")

                scope_str = " & ".join(scope_parts)
                reason_str = f"Mark entry is LOCKED for {scope_str}."
                if lock.reason:
                    reason_str += f" (Reason: {lock.reason})"
                return True, reason_str, lock

        return False, "", None

