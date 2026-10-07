import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.tenants.models import School
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.accounts.models import User, UserRole

def seed_parents_for_seattle():
    sch = School.objects.filter(code='SEA').first()
    if not sch:
        print("Seattle Academy not found!")
        return

    students = list(StudentProfile.objects.filter(school=sch).order_by('student_id'))
    print(f"Found {len(students)} students in {sch.name}")

    count = 0
    for i, stu in enumerate(students):
        p_phone = f"+251911{200000 + i:06d}"
        first_part = stu.middle_name or "Parent"
        last_part = stu.last_name or stu.first_name
        clean_code = stu.student_id.lower().replace("-", "_")
        username = f"p_{clean_code}"

        user, u_created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first_part,
                'last_name': last_part,
                'role': UserRole.PARENT,
                'school': sch,
                'phone': p_phone,
            }
        )
        user.first_name = first_part
        user.last_name = last_part
        user.role = UserRole.PARENT
        user.school = sch
        user.phone = p_phone
        user.set_password('parent123')
        user.save()

        parent_prof, p_created = ParentProfile.objects.get_or_create(
            user=user,
            school=sch,
            defaults={
                'phone': p_phone,
                'relationship': 'Father' if i % 4 != 0 else 'Mother',
                'preferred_language': 'am',
            }
        )
        parent_prof.phone = p_phone
        if i % 4 == 0:
            parent_prof.relationship = 'Mother'
        parent_prof.save()

        g_rel, g_created = GuardianRelationship.objects.get_or_create(
            school=sch,
            parent=parent_prof,
            student=stu,
            defaults={'is_primary': True}
        )
        count += 1
        print(f"[{count}] Linked Parent '{user.get_full_name()}' ({username}, {parent_prof.relationship}) -> Student '{stu.full_name}' ({stu.student_id})")

    print(f"\nDone! Successfully seeded {count} parent accounts for Seattle Academy.")
    print(f"Total parent users in SEA: {User.objects.filter(school=sch, role=UserRole.PARENT).count()}")
    print(f"Total parent profiles in SEA: {ParentProfile.objects.filter(school=sch).count()}")
    print(f"Total guardian relationships in SEA: {GuardianRelationship.objects.filter(school=sch).count()}")

if __name__ == '__main__':
    seed_parents_for_seattle()
