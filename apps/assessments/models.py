from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Grade, Section
from apps.enrollment.models import StudentEnrollment
from apps.students.models import StudentProfile


class MarkStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVED = 'APPROVED', 'Approved'
    PUBLISHED = 'PUBLISHED', 'Published'
    LOCKED = 'LOCKED', 'Locked'


class GradingScaleType(models.TextChoices):
    NUMERICAL = 'NUMERICAL', 'Numerical / Percentage'
    LETTER_GRADE = 'LETTER_GRADE', 'Letter / Grade'


class GradingScale(TenantAwareModel):
    name = models.CharField(max_length=100)
    scale_type = models.CharField(max_length=20, choices=GradingScaleType.choices, default=GradingScaleType.NUMERICAL)
    grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True, related_name='grading_scales', help_text="Specific grade level (leave blank for school default)")
    is_default = models.BooleanField(default=False)
    min_passing_mark = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    below_average_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=60.00, help_text="Threshold below which score is highlighted in red and flagged for intervention")
    high_performance_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=90.00, help_text="Threshold at or above which score is highlighted as high performance")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'name')
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_scale_type_display()})"

    @classmethod
    def get_effective_scale(cls, school, grade=None):
        if not school:
            return None
        if grade:
            g_scale = cls.objects.filter(school=school, grade=grade).first()
            if g_scale:
                return g_scale
        default_scale = cls.objects.filter(school=school, is_default=True).first()
        if default_scale:
            return default_scale
        first_scale = cls.objects.filter(school=school).first()
        if first_scale:
            return first_scale
        return cls.create_default_ethiopian_scale(school)

    @classmethod
    def create_default_ethiopian_scale(cls, school):
        scale, _ = cls.objects.get_or_create(
            school=school,
            name="Standard Ethiopian MOE Scale",
            defaults={
                'scale_type': GradingScaleType.NUMERICAL,
                'is_default': True,
                'min_passing_mark': 50.00,
                'below_average_threshold': 60.00,
                'high_performance_threshold': 90.00,
            }
        )
        if not scale.rules.exists():
            default_rules = [
                ('A+', 90.00, 100.00, 4.0, 'Outstanding', True, 1),
                ('A', 85.00, 89.99, 4.0, 'Excellent', True, 2),
                ('B+', 80.00, 84.99, 3.5, 'Very Good', True, 3),
                ('B', 75.00, 79.99, 3.0, 'Good', True, 4),
                ('C+', 65.00, 74.99, 2.5, 'Satisfactory', True, 5),
                ('C', 50.00, 64.99, 2.0, 'Passing', True, 6),
                ('D', 40.00, 49.99, 1.0, 'Conditional / Needs Improvement', False, 7),
                ('F', 0.00, 39.99, 0.0, 'Failing', False, 8),
            ]
            for letter, min_s, max_s, gpa, desc, is_pass, order in default_rules:
                GradingScaleRule.objects.create(
                    school=school,
                    scale=scale,
                    letter_grade=letter,
                    min_score=min_s,
                    max_score=max_s,
                    gpa_point=gpa,
                    description=desc,
                    is_passing=is_pass,
                    sort_order=order
                )
        return scale

    def evaluate_score(self, score, max_marks=100.0):
        if score is None:
            return {'letter': '-', 'gpa': 0.0, 'description': '-', 'is_passing': False, 'tier': 'NORMAL', 'percent': 0.0}
        try:
            val = float(score)
            max_m = float(max_marks) if max_marks and float(max_marks) > 0 else 100.0
            percent = (val / max_m) * 100.0
        except (ValueError, TypeError, ZeroDivisionError):
            percent = 0.0

        tier = 'NORMAL'
        if percent < float(self.below_average_threshold):
            tier = 'BELOW_AVERAGE'
        elif percent >= float(self.high_performance_threshold):
            tier = 'HIGH_PERFORMANCE'

        for rule in self.rules.all().order_by('-min_score'):
            if float(rule.min_score) <= percent <= float(rule.max_score) + 0.001:
                return {
                    'letter': rule.letter_grade,
                    'gpa': float(rule.gpa_point),
                    'description': rule.description,
                    'is_passing': rule.is_passing,
                    'tier': tier,
                    'percent': round(percent, 2),
                }

        is_pass = percent >= float(self.min_passing_mark)
        return {
            'letter': 'P' if is_pass else 'F',
            'gpa': 2.0 if is_pass else 0.0,
            'description': 'Pass' if is_pass else 'Fail',
            'is_passing': is_pass,
            'tier': tier,
            'percent': round(percent, 2),
        }


class GradingScaleRule(TenantAwareModel):
    scale = models.ForeignKey(GradingScale, on_delete=models.CASCADE, related_name='rules')
    letter_grade = models.CharField(max_length=10)
    min_score = models.DecimalField(max_digits=5, decimal_places=2)
    max_score = models.DecimalField(max_digits=5, decimal_places=2)
    gpa_point = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    description = models.CharField(max_length=100, blank=True)
    is_passing = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['-min_score']

    def save(self, *args, **kwargs):
        if not self.school_id and self.scale_id:
            self.school = self.scale.school
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.scale.name}: {self.letter_grade} ({self.min_score}-{self.max_score}%)"


class AssessmentComponent(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='assessment_components')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='assessment_components')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assessment_components')
    name = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.0)
    assessment_type = models.CharField(
        max_length=20,
        choices=[('NUMERICAL', 'Numerical / Percentage'), ('LETTER_GRADE', 'Letter / Grade')],
        default='NUMERICAL'
    )
    min_passing_mark = models.DecimalField(max_digits=5, decimal_places=2, default=50.0)

    class Meta:
        unique_together = ('school', 'academic_year', 'period', 'subject', 'name')

    def __str__(self):
        return f"{self.subject.code} - {self.name} ({self.weight}%)"


class StudentMark(TenantAwareModel):
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='marks')
    assessment_component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE, related_name='student_marks')
    mark_value = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    letter_grade = models.CharField(max_length=10, blank=True, null=True)
    grade_points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
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
        return f"{self.enrollment.student.full_name} - {self.assessment_component.name}: {self.mark_value} ({self.letter_grade or '-'})"

    def save(self, *args, **kwargs):
        if self.mark_value is not None and not self.letter_grade:
            try:
                g_target = getattr(self.enrollment, 'grade', None)
                scale = GradingScale.get_effective_scale(self.school, grade=g_target)
                if scale:
                    max_m = float(getattr(self.assessment_component, 'max_marks', 100.0) or 100.0)
                    eval_res = scale.evaluate_score(self.mark_value, max_marks=max_m)
                    self.letter_grade = eval_res['letter']
                    self.grade_points = eval_res['gpa']
            except Exception:
                pass
        super().save(*args, **kwargs)


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
    - Assessment Component (individual component e.g. Midterm, Final)
    - Academic Year and Period (scoping lock to active term)
    """
    LOCK_TYPES = [
        ('GRADE', 'By Grade'),
        ('SUBJECT', 'By Subject'),
        ('TEACHER', 'By Teacher'),
        ('SECTION', 'By Section'),
        ('COMPONENT', 'By Assessment Component'),
        ('CUSTOM', 'Custom / Targeted'),
    ]

    lock_type = models.CharField(max_length=20, choices=LOCK_TYPES, default='CUSTOM')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_locks')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_locks')

    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')
    assessment_component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE, null=True, blank=True, related_name='mark_entry_locks')

    is_active = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. Grading deadline closed, Administrative review, etc.")
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_mark_locks')
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='unlocked_mark_locks')
    unlock_reason = models.CharField(max_length=255, blank=True, null=True)
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
        if self.assessment_component:
            desc.append(f"Component: {self.assessment_component.name}")
        if self.teacher:
            desc.append(f"Teacher: {self.teacher.get_full_name() or self.teacher.username}")
        if self.section:
            desc.append(f"Section: {self.section.name}")
        scope = ", ".join(desc) if desc else "General"
        status = "Locked" if self.is_active else "Unlocked"
        return f"[{self.school.code}] {scope} - {status}"

    @classmethod
    def check_lock(cls, school, academic_year=None, period=None, grade=None, subject=None, teacher=None, section=None, assessment_component=None):
        """
        Evaluates whether mark entry is locked for the given context.
        Returns a tuple: (is_locked: bool, reason: str, lock_rule: MarkEntryLock or None)
        """
        from apps.academics.models import PeriodStatus
        if period and getattr(period, 'status', None) in [PeriodStatus.LOCKED, PeriodStatus.CLOSED, PeriodStatus.ARCHIVED]:
            status_label = period.get_status_display() if hasattr(period, 'get_status_display') else period.status
            return True, f"Academic term '{period.name}' is {status_label} and marks cannot be altered.", None

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

            # Check Assessment Component match
            if lock.assessment_component and assessment_component and lock.assessment_component_id != getattr(assessment_component, 'id', assessment_component):
                continue
            if lock.assessment_component and not assessment_component:
                continue

            # Rule matched!
            if lock.grade or lock.subject or lock.teacher or lock.section or lock.period or lock.assessment_component:
                scope_parts = []
                if lock.grade:
                    scope_parts.append(f"Grade {lock.grade.name}")
                if lock.subject:
                    scope_parts.append(f"Subject '{lock.subject.name}'")
                if lock.assessment_component:
                    scope_parts.append(f"Component '{lock.assessment_component.name}'")
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


class InterventionType(models.TextChoices):
    TUTORIAL = 'TUTORIAL', 'Tutorial / Remedial Class'
    PARENT_MEETING = 'PARENT_MEETING', 'Parent Conference / Meeting'
    COUNSELING = 'COUNSELING', 'Academic Counseling'
    PEER_TUTORING = 'PEER_TUTORING', 'Peer Tutoring'
    BEHAVIOR_CONTRACT = 'BEHAVIOR_CONTRACT', 'Study Plan Contract'
    CUSTOM = 'CUSTOM', 'Custom Intervention'


class InterventionStatus(models.TextChoices):
    IDENTIFIED = 'IDENTIFIED', 'Identified (Pending Action)'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    RESOLVED = 'RESOLVED', 'Resolved (Performance Improved)'
    ESCALATED = 'ESCALATED', 'Escalated to Administration'
    CLOSED = 'CLOSED', 'Closed'


class AcademicIntervention(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='academic_interventions')
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='interventions')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='interventions')
    assessment_component = models.ForeignKey(AssessmentComponent, on_delete=models.SET_NULL, null=True, blank=True, related_name='interventions')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='interventions')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='interventions')

    trigger_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Score that triggered the intervention (<60%)")
    threshold_applied = models.DecimalField(max_digits=5, decimal_places=2, default=60.00)

    intervention_type = models.CharField(max_length=30, choices=InterventionType.choices, default=InterventionType.TUTORIAL)
    status = models.CharField(max_length=30, choices=InterventionStatus.choices, default=InterventionStatus.IDENTIFIED)

    assigned_teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_interventions')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_interventions')

    action_plan = models.TextField(help_text="Prescribed remediation plan, remedial topics, or meeting agenda")
    scheduled_date = models.DateField(null=True, blank=True)

    # Parent Communication
    parent_notified = models.BooleanField(default=False)
    parent_notified_at = models.DateTimeField(null=True, blank=True)
    parent_notification_channel = models.CharField(
        max_length=20,
        default='SMS',
        choices=[('SMS', 'SMS'), ('PORTAL', 'In-App Portal'), ('PHONE', 'Phone Call'), ('IN_PERSON', 'In Person')]
    )

    # Follow-up and Outcome
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Retest / reassessment mark")
    outcome_notes = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Intervention for {self.student.full_name} ({self.subject.code}) - {self.get_status_display()}"


