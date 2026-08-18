import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
sys.path.insert(0, '.')
django.setup()

from apps.students.models import StudentProfile
from django.db import connection

with connection.cursor() as cur:
    cur.execute("SELECT id, student_id FROM students_studentprofile WHERE student_id='AIA-STU-001'")
    row = cur.fetchone()
    print("DB raw ID:", repr(row[0]))
    print("DB raw student_id:", repr(row[1]))

# How many students can we fetch by UUID object vs string?
for s in StudentProfile.objects.all():
    print(s.id, type(s.id))
    try:
        StudentProfile.objects.get(id=s.id)
    except Exception as e:
        print("Failed to fetch by s.id:", e)
    break
