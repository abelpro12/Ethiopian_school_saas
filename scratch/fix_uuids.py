import os
import sys
import uuid
import django

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.db import connection

def fix_student_profile_uuids():
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("SELECT id, student_id FROM students_studentprofile")
        rows = cursor.fetchall()
        print(f"Total StudentProfile rows in DB: {len(rows)}")
        
        fixed_count = 0
        for old_id, student_id in rows:
            try:
                uuid.UUID(str(old_id))
            except ValueError:
                new_uuid = str(uuid.uuid4())
                print(f"Fixing old id '{old_id}' for student_id '{student_id}' -> new UUID '{new_uuid}'")
                
                # Update child foreign keys
                cursor.execute("UPDATE enrollment_studentenrollment SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE parents_guardianrelationship SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE attendance_attendancerecord SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE attendance_subjectattendancerecord SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE finance_studentinvoice SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE students_studentphotohistory SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                cursor.execute("UPDATE students_studentdemographics SET student_id = %s WHERE student_id = %s", [new_uuid, old_id])
                
                # Update main table primary key
                cursor.execute("UPDATE students_studentprofile SET id = %s WHERE id = %s", [new_uuid, old_id])
                fixed_count += 1

        cursor.execute("PRAGMA foreign_keys = ON;")
        print(f"Successfully fixed {fixed_count} invalid UUID primary keys in SQLite database!")

if __name__ == '__main__':
    fix_student_profile_uuids()
