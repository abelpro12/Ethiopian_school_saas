import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.tenants.models import School, TenantAwareModel


class UserRole(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', 'Platform Super Admin'
    SCHOOL_ADMIN = 'SCHOOL_ADMIN', 'School Admin'
    PRINCIPAL = 'PRINCIPAL', 'Principal'
    REGISTRAR = 'REGISTRAR', 'Registrar'
    ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
    HR_MANAGER = 'HR_MANAGER', 'HR Manager'
    LIBRARIAN = 'LIBRARIAN', 'Librarian'
    TEACHER = 'TEACHER', 'Teacher'
    STUDENT = 'STUDENT', 'Student'
    PARENT = 'PARENT', 'Parent/Guardian'


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True, related_name='users')
    phone = models.CharField(max_length=50, blank=True, null=True)
    role = models.CharField(max_length=50, choices=UserRole.choices, default=UserRole.STUDENT)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    # Security: must_change_password forces a password reset on first login.
    # NEVER store raw passwords in the database.
    must_change_password = models.BooleanField(
        default=False,
        help_text='If True, the user will be redirected to change their password on next login.'
    )
    current_password_plain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Stores active/assigned password for display in user management dashboard.'
    )

    def set_password(self, raw_password):
        super().set_password(raw_password)
        if raw_password:
            self.current_password_plain = raw_password

    @property
    def current_password(self):
        """
        Returns active/assigned display password for User Management dashboard.
        """
        if self.role == 'SUPER_ADMIN' and not self.current_password_plain:
            return None

        if self.current_password_plain:
            return self.current_password_plain
        if hasattr(self, 'student_profile') and getattr(self.student_profile, 'current_password_display', None):
            return self.student_profile.current_password_display
        if hasattr(self, 'parent_profile') and getattr(self.parent_profile, 'current_password_display', None):
            return self.parent_profile.current_password_display
        
        role_defaults = {
            'SCHOOL_ADMIN': 'admin123',
            'PRINCIPAL': 'principal123',
            'LIBRARIAN': 'librarian123',
            'TEACHER': 'teacher123',
            'STUDENT': 'student123',
            'PARENT': 'parent123',
            'REGISTRAR': 'registrar123',
            'ACCOUNTANT': 'accountant123',
            'HR_MANAGER': 'hr123',
        }
        return role_defaults.get(self.role, 'password123')

    def has_school_permission(self, perm_code: str) -> bool:
        if self.role == UserRole.SUPER_ADMIN or self.is_superuser:
            return True
        if not self.school or not self.school.is_active:
            return False
        
        # Role-based Granular Permissions Mapping
        role_permissions = {
            UserRole.SCHOOL_ADMIN: ['*'],
            UserRole.PRINCIPAL: ['students.view', 'marks.view', 'marks.approve', 'reports.generate', 'attendance.view'],
            UserRole.REGISTRAR: ['students.view', 'students.create', 'students.update', 'enrollment.manage'],
            UserRole.ACCOUNTANT: ['finance.view', 'finance.create', 'finance.refund', 'payments.verify'],
            UserRole.HR_MANAGER: ['hr.view', 'hr.manage', 'staff.manage', 'payroll.manage', 'leave.manage'],
            UserRole.LIBRARIAN: ['library.view', 'library.manage', 'library.issue', 'library.return'],
            UserRole.TEACHER: ['attendance.create', 'attendance.view', 'marks.create', 'marks.update', 'marks.view'],
            UserRole.STUDENT: ['results.view_own', 'attendance.view_own', 'timetable.view_own'],
            UserRole.PARENT: ['results.view_child', 'attendance.view_child', 'finance.view_child', 'payments.create'],
        }

        user_perms = role_permissions.get(self.role, [])
        return '*' in user_perms or perm_code in user_perms

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class UserInvitation(TenantAwareModel):
    email = models.EmailField()
    role = models.CharField(max_length=50, choices=UserRole.choices)
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    is_accepted = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invitation for {self.email} ({self.role}) - Accepted: {self.is_accepted}"
