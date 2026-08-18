import datetime
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile


class EnrollmentStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    PROMOTED = 'PROMOTED', 'Promoted'
    PROMOTED_WITH_CONDITIONS = 'PROMOTED_WITH_CONDITIONS', 'Promoted with Conditions'
    RETAINED = 'RETAINED', 'Retained (Repeating Grade)'
    SPECIAL_REVIEW = 'SPECIAL_REVIEW', 'Special Review'
    GRADUATED = 'GRADUATED', 'Graduated'
    TRANSFERRED = 'TRANSFERRED', 'Transferred Out'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'
    SUSPENDED = 'SUSPENDED', 'Suspended'


class AdmissionType(models.TextChoices):
    NEW = 'NEW', 'New Admission'
    TRANSFER = 'TRANSFER', 'Transfer In'
    READMISSION = 'READMISSION', 'Readmission'


class StudentEnrollment(TenantAwareModel):
    enrollment_number = models.CharField(max_length=50, blank=True, null=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='enrollments')
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='enrollments')
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='enrollments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='enrollments')
    enrollment_date = models.DateField(default=datetime.date.today)
    status = models.CharField(max_length=30, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
    admission_type = models.CharField(max_length=20, choices=AdmissionType.choices, default=AdmissionType.NEW)
    previous_school = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ('school', 'academic_year', 'student')
        ordering = ['-academic_year__gregorian_start_date', '-grade__level', '-id']

    def __str__(self):
        return f"{self.student.full_name} - {self.section} ({self.academic_year.name})"


class SubjectEnrollment(TenantAwareModel):
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='subject_enrollments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'enrollment', 'subject')

    def __str__(self):
        return f"{self.enrollment.student.full_name} -> {self.subject.name}"


class PromotionDecisionType(models.TextChoices):
    PROMOTED = 'PROMOTED', 'Promoted'
    PROMOTED_WITH_CONDITIONS = 'PROMOTED_WITH_CONDITIONS', 'Promoted with Conditions'
    RETAINED = 'RETAINED', 'Retained (Repeating Grade)'
    SPECIAL_REVIEW = 'SPECIAL_REVIEW', 'Special Administrative Review'
    GRADUATED = 'GRADUATED', 'Graduated'
    TRANSFERRED = 'TRANSFERRED', 'Transferred Out'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'


class StudentPromotionDecision(TenantAwareModel):
    enrollment = models.OneToOneField(StudentEnrollment, on_delete=models.CASCADE, related_name='promotion_decision')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='promotion_decisions')
    policy_used = models.ForeignKey('academics.PromotionPolicy', on_delete=models.SET_NULL, null=True, blank=True)
    final_average = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    failed_subjects_count = models.IntegerField(default=0)
    failed_subjects_json = models.JSONField(default=list)
    section_rank = models.IntegerField(null=True, blank=True)
    grade_rank = models.IntegerField(null=True, blank=True)
    system_recommendation = models.CharField(max_length=30, choices=PromotionDecisionType.choices)
    admin_decision = models.CharField(max_length=30, choices=PromotionDecisionType.choices, null=True, blank=True)
    allocated_grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_promotion_decisions')
    allocated_stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_promotion_decisions')
    allocated_section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocated_promotion_decisions')
    conditions_notes = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('school', 'enrollment')

    def __str__(self):
        return f"Promotion Decision: {self.enrollment.student.full_name} -> {self.admin_decision or self.system_recommendation}"


class StudentStreamPreference(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='stream_preferences')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='stream_preferences')
    preference_1 = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='pref1_students')
    preference_2 = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name='pref2_students')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'student', 'academic_year')

    def __str__(self):
        return f"Stream Pref: {self.student.full_name} (1: {self.preference_1.name})"


class StudentWithdrawal(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='withdrawals')
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='withdrawals')
    reason = models.TextField()
    library_cleared = models.BooleanField(default=False)
    finance_cleared = models.BooleanField(default=False)
    property_cleared = models.BooleanField(default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    withdrawn_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Withdrawal: {self.student.full_name}"


class TransferType(models.TextChoices):
    INTERNAL = 'INTERNAL', 'Internal Section Transfer'
    EXTERNAL = 'EXTERNAL', 'External School Transfer'


class StudentTransfer(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='transfers')
    transfer_type = models.CharField(max_length=20, choices=TransferType.choices, default=TransferType.INTERNAL)
    reason = models.TextField()
    from_section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_from')
    to_section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_to')
    destination_school = models.CharField(max_length=200, blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer ({self.transfer_type}) for {self.student.full_name}"


class StreamChangeRequest(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='stream_changes')
    from_stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='stream_changes_from')
    to_stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='stream_changes_to')
    reason = models.TextField()
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Stream Change for {self.student.full_name}: {self.from_stream.code} -> {self.to_stream.code}"


class PromotionHistory(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='promotion_history')
    from_enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='promoted_from')
    to_enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='promoted_to')
    promoted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Promoted {self.student.full_name}: {self.from_enrollment.grade.name} -> {self.to_enrollment.grade.name}"

