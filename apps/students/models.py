import uuid
import datetime
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User


class StudentStatus(models.TextChoices):
    APPLICANT = 'APPLICANT', 'Applicant'
    REGISTERED = 'REGISTERED', 'Registered'
    ENROLLED = 'ENROLLED', 'Enrolled'
    ACTIVE = 'ACTIVE', 'Active'
    PROMOTED = 'PROMOTED', 'Promoted'
    TRANSFERRED = 'TRANSFERRED', 'Transferred'
    GRADUATED = 'GRADUATED', 'Graduated'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    RETAINED = 'RETAINED', 'Retained (Repeating)'


class StudentProfile(TenantAwareModel):
    # Internal UUID primary key (never used as public business identifier)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')

    # Separate Non-PK Identifiers (Requirement 3)
    student_id = models.CharField(max_length=50)  # School-scoped ID e.g. AIA-STU-001
    admission_number = models.CharField(max_length=50, blank=True, null=True)  # e.g. ADM-2016-042
    roll_number = models.CharField(max_length=50, blank=True, null=True)  # e.g. 12
    national_id = models.CharField(max_length=100, blank=True, null=True)  # e.g. ETH-NAT-98765
    previous_school_id = models.CharField(max_length=100, blank=True, null=True)  # e.g. OLD-SCH-101

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    # Ethiopian Amharic Name fields
    amharic_first_name = models.CharField(max_length=100, blank=True, null=True)
    amharic_last_name = models.CharField(max_length=100, blank=True, null=True)
    amharic_name = models.CharField(max_length=200, blank=True, null=True)

    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')])
    date_of_birth = models.DateField(blank=True, null=True)
    ethiopian_birth_date = models.CharField(max_length=50, blank=True, null=True)
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)
    thumbnail = models.ImageField(upload_to='student_photos/thumbnails/', blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    # Ethiopian Administrative Location Hierarchy
    region = models.CharField(max_length=100, blank=True, null=True)
    zone = models.CharField(max_length=100, blank=True, null=True)
    woreda = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    subcity = models.CharField(max_length=100, blank=True, null=True)
    kebele = models.CharField(max_length=100, blank=True, null=True)

    emergency_contact = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=StudentStatus.choices, default=StudentStatus.ACTIVE)

    class Meta:
        unique_together = ('school', 'student_id')

    @classmethod
    def generate_next_student_id(cls, school):
        """
        Generates the next sequential Student ID for a school.
        Format: <SCHOOL_CODE>-STU-<NUMBER:04d> e.g. AIA-STU-0042
        """
        if not school:
            return "STU-0001"
        code = school.code.upper().strip() if school.code else "SCH"
        count = cls.objects.filter(school=school).count() + 1
        candidate = f"{code}-STU-{count:04d}"
        while cls.objects.filter(school=school, student_id=candidate).exists():
            count += 1
            candidate = f"{code}-STU-{count:04d}"
        return candidate

    @property
    def latest_enrollment(self):
        return self.enrollments.order_by('-academic_year__gregorian_start_date', '-grade__level', '-id').first()

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p.strip() for p in parts if p and p.strip())

    @property
    def primary_guardian(self):
        rel = self.guardianships.select_related('parent__user').first()
        if rel and rel.parent:
            return rel.parent
        from apps.parents.models import ParentProfile
        parent_username = f"p_{self.student_id.lower()}"
        return ParentProfile.objects.filter(school=self.school, user__username=parent_username).first()

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"


class StudentPhotoHistory(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='photo_history')
    photo = models.ImageField(upload_to='student_photos/history/')
    thumbnail = models.ImageField(upload_to='student_photos/thumbnails/', blank=True, null=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Photo History for {self.student.full_name} ({self.uploaded_at.strftime('%Y-%m-%d')})"


class StudentDemographics(TenantAwareModel):
    student = models.OneToOneField(StudentProfile, on_delete=models.CASCADE, related_name='demographics')
    gender_identity = models.CharField(max_length=50, blank=True, null=True)
    custom_demographics = models.JSONField(default=dict)

    def __str__(self):
        return f"Demographics for {self.student.full_name}"


class ApplicationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Review'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    REGISTERED = 'REGISTERED', 'Registered into School'


class StudentApplication(TenantAwareModel):
    application_number = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')])
    grade_level = models.IntegerField(default=9)
    previous_school = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=20, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Application {self.application_number}: {self.first_name} {self.last_name} ({self.status})"


# --- Student Clearance & Withdrawal System (Priority 2) ---

class WithdrawalReason(models.TextChoices):
    TRANSFER = 'TRANSFER', 'Transfer to Another School'
    RELOCATION = 'RELOCATION', 'Family Relocation / Moving'
    FINANCIAL = 'FINANCIAL', 'Financial Reasons'
    MEDICAL = 'MEDICAL', 'Health / Medical Reasons'
    GRADUATION = 'GRADUATION', 'Graduation / Completed Studies'
    PERSONAL = 'PERSONAL', 'Personal / Family Reasons'
    DISCIPLINARY = 'DISCIPLINARY', 'Disciplinary Expulsion'
    OTHER = 'OTHER', 'Other'


class ClearanceStatus(models.TextChoices):
    INITIATED = 'INITIATED', 'Initiated (Pending Clearances)'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Department Review'
    APPROVED = 'APPROVED', 'Fully Cleared & Approved'
    REJECTED = 'REJECTED', 'Clearance Rejected / Blocked'
    WITHDRAWN = 'WITHDRAWN', 'Official Withdrawal Finalized'


class StudentClearance(TenantAwareModel):
    student = models.ForeignKey('StudentProfile', on_delete=models.CASCADE, related_name='clearances')
    enrollment = models.ForeignKey('enrollment.StudentEnrollment', on_delete=models.SET_NULL, null=True, blank=True, related_name='clearances')
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE, related_name='clearances')

    clearance_number = models.CharField(max_length=50)
    withdrawal_reason = models.CharField(max_length=30, choices=WithdrawalReason.choices, default=WithdrawalReason.TRANSFER)
    reason_details = models.TextField(blank=True, null=True)
    destination_school = models.CharField(max_length=200, blank=True, null=True, help_text="Destination school transferred to")
    effective_date = models.DateField(default=datetime.date.today)

    status = models.CharField(max_length=30, choices=ClearanceStatus.choices, default=ClearanceStatus.INITIATED)

    # 1. Library Clearance (Book return check)
    library_cleared = models.BooleanField(default=False)
    library_cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cleared_library_clearances')
    library_cleared_at = models.DateTimeField(null=True, blank=True)
    library_remarks = models.TextField(blank=True, null=True)

    # 2. Finance Clearance (Fee & invoice balance settlement)
    finance_cleared = models.BooleanField(default=False)
    finance_cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cleared_finance_clearances')
    finance_cleared_at = models.DateTimeField(null=True, blank=True)
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    finance_remarks = models.TextField(blank=True, null=True)

    # 3. Class Teacher / Academic Clearance (Textbooks, lockers, grades submitted)
    academic_cleared = models.BooleanField(default=False)
    academic_cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cleared_academic_clearances')
    academic_cleared_at = models.DateTimeField(null=True, blank=True)
    academic_remarks = models.TextField(blank=True, null=True)

    # 4. Property & Sports Store Clearance (Uniforms, athletic gear, laboratory items)
    property_cleared = models.BooleanField(default=False)
    property_cleared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cleared_property_clearances')
    property_cleared_at = models.DateTimeField(null=True, blank=True)
    property_remarks = models.TextField(blank=True, null=True)

    # 5. Final Registrar / Principal Approval
    final_approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_final_clearances')
    final_approved_at = models.DateTimeField(null=True, blank=True)
    final_remarks = models.TextField(blank=True, null=True)

    # Certificate Tracking
    certificate_issued = models.BooleanField(default=False)
    certificate_number = models.CharField(max_length=50, blank=True, null=True)
    certificate_issued_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='initiated_clearances')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'clearance_number')
        ordering = ['-created_at']

    @classmethod
    def generate_next_clearance_number(cls, school):
        if not school:
            return "CLR-0001"
        code = school.code.upper().strip() if school.code else "SCH"
        year = datetime.date.today().year
        count = cls.objects.filter(school=school).count() + 1
        candidate = f"{code}-CLR-{year}-{count:04d}"
        while cls.objects.filter(school=school, clearance_number=candidate).exists():
            count += 1
            candidate = f"{code}-CLR-{year}-{count:04d}"
        return candidate

    @property
    def all_departments_cleared(self):
        return self.library_cleared and self.finance_cleared and self.academic_cleared and self.property_cleared

    @property
    def cleared_departments_count(self):
        return sum([self.library_cleared, self.finance_cleared, self.academic_cleared, self.property_cleared])

    def __str__(self):
        return f"{self.clearance_number} - {self.student.full_name} ({self.get_status_display()})"
