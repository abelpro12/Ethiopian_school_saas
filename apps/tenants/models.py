import uuid
from django.db import models
from django.core.exceptions import PermissionDenied


class SchoolStatus(models.TextChoices):
    PENDING_SETUP = 'PENDING_SETUP', 'Pending Setup'
    TRIAL = 'TRIAL', 'Trial'
    ACTIVE = 'ACTIVE', 'Active'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    ARCHIVED = 'ARCHIVED', 'Archived'


class School(models.Model):
    CALENDAR_CHOICES = [
        ('ETHIOPIAN', 'Ethiopian Calendar'),
        ('GREGORIAN', 'Gregorian Calendar'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)
    motto = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    woreda = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=10, default='ETB')
    logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
    stamp = models.ImageField(upload_to='school_stamps/', blank=True, null=True)
    calendar_preference = models.CharField(max_length=20, choices=CALENDAR_CHOICES, default='ETHIOPIAN')
    status = models.CharField(max_length=20, choices=SchoolStatus.choices, default=SchoolStatus.PENDING_SETUP)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def display_status(self):
        if not self.is_active or self.status == SchoolStatus.SUSPENDED:
            return {'label': 'Suspended', 'badge': 'badge-red'}
        if self.status == SchoolStatus.ARCHIVED:
            return {'label': 'Archived', 'badge': 'badge-gray'}
        
        sub = getattr(self, 'subscription', None)
        if sub:
            sub.sync_status()
            if sub.is_expired:
                return {'label': 'Expired', 'badge': 'badge-red'}
            if sub.status == 'GRACE_PERIOD':
                return {'label': 'Grace Period', 'badge': 'badge-yellow'}
            if sub.status == 'TRIAL':
                return {'label': f'Trial ({sub.days_remaining}d)', 'badge': 'badge-blue'}
            if sub.status == 'ACTIVE':
                return {'label': 'Active', 'badge': 'badge-green'}
                
        if self.is_active:
            return {'label': 'Active', 'badge': 'badge-green'}
        return {'label': self.get_status_display(), 'badge': 'badge-gray'}

    @property
    def subscription_safe(self):
        try:
            return self.subscription
        except Exception:
            return None


class SchoolDomain(models.Model):
    domain = models.CharField(max_length=255, unique=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='domains')
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.domain} -> {self.school.name}"


class TenantQuerySet(models.QuerySet):
    def for_school(self, school):
        if school is None:
            return self.none()
        return self.filter(school=school)


class TenantManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_school(self, school):
        return self.get_queryset().for_school(school)


class TenantAwareModel(models.Model):
    """
    Abstract model enforcing explicit tenant isolation.
    Every tenant model inherits from this class.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, db_index=True, related_name="%(class)s_objects")

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.school_id:
            raise ValueError("TenantAwareModel requires an explicit school reference before saving.")
        super().save(*args, **kwargs)
