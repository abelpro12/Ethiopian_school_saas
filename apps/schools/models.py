from django.db import models
from apps.tenants.models import TenantAwareModel, School


class HierarchyLevel(models.TextChoices):
    FEDERAL = 'FEDERAL', 'Federal Ministry of Education'
    REGION = 'REGION', 'Regional Education Bureau'
    ZONE = 'ZONE', 'Zone Education Department'
    WOREDA = 'WOREDA', 'Woreda Education Office'
    SCHOOL = 'SCHOOL', 'School Level'


class AdministrativeHierarchy(models.Model):
    name = models.CharField(max_length=200)  # e.g., "Oromia Region", "Bole Woreda 03"
    level = models.CharField(max_length=20, choices=HierarchyLevel.choices, default=HierarchyLevel.REGION)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"


class SchoolSetting(TenantAwareModel):
    key = models.CharField(max_length=100)
    value = models.TextField()

    class Meta:
        unique_together = ('school', 'key')

    def __str__(self):
        return f"{self.school.code} - {self.key}: {self.value}"


class SchoolNews(TenantAwareModel):
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100, default='General')
    badge_text = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField()
    location = models.CharField(max_length=200, blank=True, null=True)
    image = models.ImageField(upload_to='school_news/', blank=True, null=True)
    image_url = models.CharField(max_length=500, blank=True, null=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SchoolGallery(TenantAwareModel):
    title = models.CharField(max_length=255)
    caption = models.CharField(max_length=255, blank=True, null=True)
    category = models.CharField(max_length=100, default='Campus Life')
    image = models.ImageField(upload_to='school_gallery/', blank=True, null=True)
    image_url = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SchoolContactMessage(TenantAwareModel):
    sender_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender_name} - {self.subject} ({self.created_at.strftime('%Y-%m-%d')})"


