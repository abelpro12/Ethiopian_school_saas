from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Subject, Section


class EmploymentStatus(models.TextChoices):
    FULL_TIME = 'FULL_TIME', 'Full Time'
    PART_TIME = 'PART_TIME', 'Part Time'
    CONTRACT = 'CONTRACT', 'Contract'
    INACTIVE = 'INACTIVE', 'Inactive'


class Department(TenantAwareModel):
    name = models.CharField(max_length=100)  # e.g. "Mathematics & ICT", "Natural Sciences"
    code = models.CharField(max_length=20)   # e.g. "MATH", "SCI"
    description = models.TextField(blank=True, null=True)
    head_of_department = models.ForeignKey(
        'TeacherProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'code')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def teacher_count(self):
        return self.teachers.count()

    @property
    def subject_count(self):
        return self.subjects.count()


class TeacherProfile(TenantAwareModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    employee_id = models.CharField(max_length=50)
    qualification = models.CharField(max_length=100, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')], blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    department_obj = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teachers'
    )
    hire_date = models.DateField(blank=True, null=True)
    employment_status = models.CharField(max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.FULL_TIME)
    max_weekly_periods = models.PositiveIntegerField(
        default=25,
        help_text="Maximum allowed teaching periods per week (Standard Ethiopian curriculum: 20-30)"
    )
    max_daily_periods = models.PositiveIntegerField(
        default=6,
        help_text="Maximum allowed teaching periods per single day"
    )

    class Meta:
        unique_together = ('school', 'employee_id')

    @classmethod
    def generate_next_employee_id(cls, school):
        """
        Generates the next sequential Teacher Employee ID for a school.
        Format: <SCHOOL_CODE>-TCH-<NUMBER:04d> e.g. AIA-TCH-0001
        """
        if not school:
            return "TCH-0001"
        code = school.code.upper().strip() if school.code else "SCH"
        count = cls.objects.filter(school=school).count() + 1
        candidate = f"{code}-TCH-{count:04d}"
        while cls.objects.filter(school=school, employee_id=candidate).exists():
            count += 1
            candidate = f"{code}-TCH-{count:04d}"
        return candidate

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.employee_id})"

    @property
    def homeroom_section(self):
        return self.user.managed_sections.filter(is_active=True).first()

    @property
    def homeroom_display(self):
        sections = self.user.managed_sections.filter(is_active=True).select_related('grade')
        if sections.exists():
            return ", ".join([f"{s.grade.name} - {s.name}" for s in sections])
        return None

    @property
    def total_weekly_periods(self):
        from apps.academics.models import TimetableSlot
        slots = TimetableSlot.objects.filter(school=self.school, teacher=self).count()
        if slots > 0:
            return slots
        assign_count = self.assignments.count()
        return assign_count * 4 if assign_count > 0 else 0

    @property
    def workload_percentage(self):
        assigned = self.total_weekly_periods
        if not self.max_weekly_periods:
            return 0
        return round((assigned / self.max_weekly_periods) * 100, 1)

    @property
    def workload_status(self):
        pct = self.workload_percentage
        if pct > 100:
            return 'OVER'
        elif pct < 60:
            return 'UNDER'
        return 'OPTIMAL'

    @property
    def assigned_subjects(self):
        return self.assignments.values_list('subject__name', flat=True).distinct()

    @property
    def assigned_sections(self):
        return self.assignments.values_list('section__name', flat=True).distinct()

    def save(self, *args, **kwargs):
        if self.department_obj and not self.department:
            self.department = self.department_obj.name
        super().save(*args, **kwargs)


class TeacherAssignment(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='teacher_assignments')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teacher_assignments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='teacher_assignments')

    class Meta:
        unique_together = ('school', 'academic_year', 'teacher', 'subject', 'section')

    def __str__(self):
        return f"{self.teacher.user.username} -> {self.subject.code} ({self.section.name})"


# --- Non-Teaching School Staff Module & Staff Documents (Requirement 8) ---

class StaffPosition(models.TextChoices):
    PRINCIPAL = 'PRINCIPAL', 'Principal'
    VICE_PRINCIPAL = 'VICE_PRINCIPAL', 'Vice Principal'
    REGISTRAR = 'REGISTRAR', 'Registrar'
    ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
    SECRETARY = 'SECRETARY', 'Secretary'
    LIBRARIAN = 'LIBRARIAN', 'Librarian'
    COUNSELOR = 'COUNSELOR', 'Counselor'
    IT_ADMINISTRATOR = 'IT_ADMINISTRATOR', 'IT Administrator'
    SECURITY_STAFF = 'SECURITY_STAFF', 'Security Staff'
    OTHER = 'OTHER', 'Other Staff'


class StaffEmploymentStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ON_LEAVE = 'ON_LEAVE', 'On Leave'
    TERMINATED = 'TERMINATED', 'Terminated'
    RETIRED = 'RETIRED', 'Retired'


class StaffProfile(TenantAwareModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=50)
    department = models.CharField(max_length=100)
    position = models.CharField(max_length=50, choices=StaffPosition.choices, default=StaffPosition.OTHER)
    hire_date = models.DateField(blank=True, null=True)
    employment_status = models.CharField(max_length=20, choices=StaffEmploymentStatus.choices, default=StaffEmploymentStatus.ACTIVE)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('school', 'employee_id')

    @classmethod
    def generate_next_employee_id(cls, school):
        """
        Generates the next sequential Staff Employee ID for a school.
        Format: <SCHOOL_CODE>-STF-<NUMBER:04d> e.g. AIA-STF-0001
        """
        if not school:
            return "STF-0001"
        code = school.code.upper().strip() if school.code else "SCH"
        count = cls.objects.filter(school=school).count() + 1
        candidate = f"{code}-STF-{count:04d}"
        while cls.objects.filter(school=school, employee_id=candidate).exists():
            count += 1
            candidate = f"{code}-STF-{count:04d}"
        return candidate

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_position_display()} ({self.employee_id})"


class StaffDocumentType(models.TextChoices):
    EMPLOYMENT = 'EMPLOYMENT', 'Employment Document'
    CERTIFICATE = 'CERTIFICATE', 'Professional Certificate'
    CONTRACT = 'CONTRACT', 'Employment Contract'
    IDENTIFICATION = 'IDENTIFICATION', 'Identification Document (ID/Passport)'
    HR_OTHER = 'HR_OTHER', 'Other HR Document'


class StaffDocument(TenantAwareModel):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=StaffDocumentType.choices, default=StaffDocumentType.EMPLOYMENT)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='staff_documents/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) for {self.staff.employee_id}"


# --- Staff Leave Management Module (Requirement 10) ---

class LeaveType(models.TextChoices):
    ANNUAL = 'ANNUAL', 'Annual Leave'
    SICK = 'SICK', 'Sick Leave'
    MATERNITY = 'MATERNITY', 'Maternity Leave'
    PATERNITY = 'PATERNITY', 'Paternity Leave'
    PERSONAL = 'PERSONAL', 'Personal Leave'
    OTHER = 'OTHER', 'Other Leave'


class LeaveRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


class StaffLeaveRequest(TenantAwareModel):
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='staff_leave_requests')
    leave_type = models.CharField(max_length=30, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=LeaveRequestStatus.choices, default=LeaveRequestStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_staff_leaves')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Leave Request ({self.get_leave_type_display()}) for {self.staff_user.username}: {self.start_date} to {self.end_date} [{self.status}]"
