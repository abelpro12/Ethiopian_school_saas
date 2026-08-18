import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.academics.models import AcademicYear
from apps.tenants.models import School

for school in School.objects.all():
    years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')
    if years.exists():
        # Keep the most recent one active, set others to inactive
        most_recent = years.first()
        most_recent.is_active = True
        most_recent.save()
        
        years.exclude(id=most_recent.id).update(is_active=False)
        print(f"Set active year for {school.name} to {most_recent.name}")

print("Fixed active years!")
