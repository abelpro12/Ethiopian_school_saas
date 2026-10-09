import datetime
from django.utils import timezone
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
    # Teacher Recruitment & Onboarding (Priority 2)
    onboarding_status = models.CharField(
        max_length=30,
        default='ACTIVE',
        choices=[
            ('APPLIED', 'Application Received'),
            ('INTERVIEWED', 'Interviewed'),
            ('OFFERED', 'Offer Made'),
            ('ONBOARDING', 'Onboarding & Document Submission'),
            ('ACTIVE', 'Fully Onboarded & Active'),
            ('REJECTED', 'Application Rejected')
        ]
    )
    background_check_completed = models.BooleanField(default=True)
    contract_signed = models.BooleanField(default=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = models.CharField(max_length=50, blank=True, null=True)

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
    CERTIFICATE = 'CERTIFICATE', 'Professional Certificate / Degree'
    CONTRACT = 'CONTRACT', 'Employment Contract'
    IDENTIFICATION = 'IDENTIFICATION', 'Identification Document (ID/Passport)'
    RECOMMENDATION = 'RECOMMENDATION', 'Letter of Recommendation'
    HR_OTHER = 'HR_OTHER', 'Other HR Document'


class StaffDocument(TenantAwareModel):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='staff_documents')
    document_type = models.CharField(max_length=50, choices=StaffDocumentType.choices, default=StaffDocumentType.EMPLOYMENT)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='staff_documents/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verification_status = models.CharField(
        max_length=20,
        default='PENDING',
        choices=[
            ('PENDING', 'Pending Verification'),
            ('VERIFIED', 'Verified / Approved'),
            ('REJECTED', 'Rejected'),
        ]
    )
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_staff_documents')
    verified_at = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        owner = self.teacher.employee_id if self.teacher else (self.staff.employee_id if self.staff else 'Unknown')
        return f"{self.title} ({self.get_document_type_display()}) for {owner}"


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


# --- Teacher Vacancy & Candidate Recruitment Module (Requirement 9) ---

class VacancyStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    OPEN = 'OPEN', 'Open (Accepting Applications)'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    CLOSED = 'CLOSED', 'Closed'
    FILLED = 'FILLED', 'Position Filled'


class CandidateApplicationStatus(models.TextChoices):
    SUBMITTED = 'SUBMITTED', 'Application Submitted'
    SHORTLISTED = 'SHORTLISTED', 'Shortlisted'
    TEST_SCHEDULED = 'TEST_SCHEDULED', 'Written Test Scheduled'
    INTERVIEW_SCHEDULED = 'INTERVIEW_SCHEDULED', 'Interview Scheduled'
    OFFERED = 'OFFERED', 'Offer Made'
    ACCEPTED = 'ACCEPTED', 'Accepted & Appointed'
    REJECTED = 'REJECTED', 'Application Rejected'


class TeacherVacancy(TenantAwareModel):
    title = models.CharField(max_length=150)  # e.g. "Senior Physics Teacher (Grades 11-12)"
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='vacancies')
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='vacancies')
    required_qualification = models.CharField(max_length=150, help_text="e.g. B.Sc or B.Ed in Physics")
    min_years_experience = models.PositiveIntegerField(default=2)
    employment_type = models.CharField(max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.FULL_TIME)
    open_positions = models.PositiveIntegerField(default=1)
    application_deadline = models.DateField()
    description = models.TextField()
    requirements = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=VacancyStatus.choices, default=VacancyStatus.OPEN)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_vacancies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} [{self.get_status_display()}] - {self.school.name}"

    @property
    def applications_count(self):
        return self.applications.count()


class TeacherApplication(TenantAwareModel):
    vacancy = models.ForeignKey(TeacherVacancy, on_delete=models.CASCADE, related_name='applications')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    highest_qualification = models.CharField(max_length=100)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    years_of_experience = models.PositiveIntegerField(default=0)
    cv_resume = models.FileField(upload_to='teacher_applications/cv/', blank=True, null=True)
    cover_letter = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=CandidateApplicationStatus.choices, default=CandidateApplicationStatus.SUBMITTED)

    # Examination & Assessment
    test_date = models.DateField(blank=True, null=True)
    test_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    interview_date = models.DateField(blank=True, null=True)
    interview_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    interviewer_notes = models.TextField(blank=True, null=True)

    # Appointment & Onboarding Conversion
    appointment_date = models.DateField(blank=True, null=True)
    employment_start_date = models.DateField(blank=True, null=True)
    converted_teacher = models.ForeignKey(TeacherProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='source_application')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} -> {self.vacancy.title} ({self.get_status_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def convert_to_teacher(self, initial_password=None):
        """
        1-click conversion from accepted candidate to active Teacher profile.
        Eliminates duplicate manual data entry (Requirement 9).
        """
        from apps.accounts.models import UserRole
        from django.utils.crypto import get_random_string
        from apps.audit.services import AuditService

        if self.converted_teacher:
            return self.converted_teacher

        # Generate unique username
        base_username = f"tch_{self.first_name.lower().strip()}_{self.last_name.lower().strip()}"
        candidate_username = base_username
        suffix = 1
        while User.objects.filter(username=candidate_username).exists():
            candidate_username = f"{base_username}{suffix}"
            suffix += 1

        password = initial_password or f"Teacher@{get_random_string(6, '0123456789')}"

        new_user = User.objects.create_user(
            username=candidate_username,
            email=self.email,
            password=password,
            first_name=self.first_name,
            last_name=self.last_name,
            role=UserRole.TEACHER,
            school=self.school
        )

        emp_id = TeacherProfile.generate_next_employee_id(self.school)
        hire_d = self.employment_start_date or datetime.date.today()

        profile = TeacherProfile.objects.create(
            school=self.school,
            user=new_user,
            employee_id=emp_id,
            qualification=self.highest_qualification,
            specialization=self.specialization or (self.vacancy.subject.name if self.vacancy.subject else ""),
            department_obj=self.vacancy.department,
            department=self.vacancy.department.name if self.vacancy.department else "",
            hire_date=hire_d,
            phone=self.phone,
            onboarding_status='ACTIVE',
            employment_status=self.vacancy.employment_type
        )

        # Attach CV document if uploaded
        if self.cv_resume:
            StaffDocument.objects.create(
                school=self.school,
                teacher=profile,
                document_type=StaffDocumentType.CERTIFICATE,
                title=f"Curriculum Vitae - {self.full_name}",
                file=self.cv_resume,
                verification_status='VERIFIED',
                verified_by=new_user,
                verified_at=timezone.now()
            )

        self.status = CandidateApplicationStatus.ACCEPTED
        self.converted_teacher = profile
        self.save()

        AuditService.log_action(
            school=self.school,
            user=new_user,
            action="CONVERT_CANDIDATE_TO_TEACHER",
            object_type="TeacherProfile",
            object_id=str(profile.id),
            details={
                "candidate": self.full_name,
                "username": candidate_username,
                "employee_id": emp_id,
                "vacancy": self.vacancy.title
            }
        )
        return profile

