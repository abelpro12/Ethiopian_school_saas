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
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)

    # Security: must_change_password forces a password reset on first login.
    # NEVER store raw passwords in the database.
    must_change_password = models.BooleanField(
        default=False,
        help_text='If True, the user will be redirected to change their password on next login.'
    )

    @property
    def is_activation_pending(self):
        """
        Returns True if the account has not yet completed initial setup / activation:
        1. Account has an unusable password (not self.has_usable_password()).
        2. Account has a usable temporary password, must_change_password=True, and has never logged in (last_login is None).
        Activated accounts (usable password with must_change_password=False, or active accounts with prior logins)
        return False.
        """
        if not self.has_usable_password():
            return True
        return bool(self.must_change_password and self.last_login is None)

    @property
    def presence_status(self):
        """
        Returns 'online' (<5m), 'away' (<30m), or 'offline'.
        """
        if not self.last_seen:
            return 'offline'
        from django.utils import timezone
        import datetime
        diff = timezone.now() - self.last_seen
        if diff < datetime.timedelta(minutes=5):
            return 'online'
        elif diff < datetime.timedelta(minutes=30):
            return 'away'
        return 'offline'

    @property
    def presence_label(self):
        status = self.presence_status
        if status == 'online':
            return 'Online'
        elif status == 'away':
            return 'Recently Active'
        return 'Offline'

    @property
    def presence_badge_classes(self):
        status = self.presence_status
        if status == 'online':
            return 'bg-emerald-50 text-emerald-700 border border-emerald-200'
        elif status == 'away':
            return 'bg-amber-50 text-amber-700 border border-amber-200'
        return 'bg-slate-100 text-slate-500 border border-slate-200'

    @property
    def presence_dot_class(self):
        status = self.presence_status
        if status == 'online':
            return 'bg-emerald-500'
        elif status == 'away':
            return 'bg-amber-500'
        return 'bg-slate-400'

    @property
    def last_seen_display(self):
        if not self.last_seen:
            return 'Never'
        from django.utils import timezone
        import datetime
        diff = timezone.now() - self.last_seen
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'Just now'
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        return self.last_seen.strftime('%b %d, %Y')

    @property
    def current_password(self):
        """
        Security: Plaintext password storage and retrieval has been deprecated
        and disabled (Stage 1 remediation). Always returns None to prevent
        credential exposure across UI, exports, and templates.
        """
        return None

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
