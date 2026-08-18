import uuid
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
        return f"{self.first_name} {self.middle_name} {self.last_name}".strip()

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
