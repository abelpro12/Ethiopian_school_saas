import uuid
import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password

from apps.accounts.models import User, UserRole
from apps.tenants.models import School, SchoolStatus
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile, StudentStatus
from apps.teachers.models import TeacherProfile, EmploymentStatus
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus

class Command(BaseCommand):
    help = 'Seeds the database with demo data for Addis International Academy'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting demo data seeding...")

        # 1. Create School
        school, created = School.objects.get_or_create(
            subdomain='addis-academy',
            defaults={
                'name': 'Addis International Academy',
                'code': 'AIA-001',
                'motto': 'Excellence in Education',
                'phone': '+251911234567',
                'email': 'info@addisacademy.edu.et',
                'city': 'Addis Ababa',
                'currency': 'ETB',
                'status': SchoolStatus.ACTIVE,
                'is_active': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created school: {school.name}'))
        else:
            self.stdout.write(f'School {school.name} already exists.')

        # 2. Create Academic Year and AcademicPeriod
        academic_year, ay_created = AcademicYear.objects.get_or_create(
            school=school,
            name='2026/2027 Academic Year',
            defaults={
                'ethiopian_year': 2018,
                'gregorian_start_date': datetime.date(2026, 9, 1),
                'gregorian_end_date': datetime.date(2027, 6, 30),
                'is_active': True
            }
        )

        period, sem_created = AcademicPeriod.objects.get_or_create(
            academic_year=academic_year,
            school=school,
            name='AcademicPeriod 1',
            defaults={
                'start_date': datetime.date(2026, 9, 1),
                'end_date': datetime.date(2027, 1, 31),
                'is_current': True
            }
        )

        # 3. Create Streams, Grades, Sections
        stream_gen, _ = Stream.objects.get_or_create(school=school, code='GEN', defaults={'name': 'General'})
        
        grade_9, g_created = Grade.objects.get_or_create(school=school, level=9, stream_type='GEN', defaults={'name': 'Grade 9'})
        grade_10, _ = Grade.objects.get_or_create(school=school, level=10, stream_type='GEN', defaults={'name': 'Grade 10'})
        
        section_9a, s_created = Section.objects.get_or_create(
            school=school, 
            grade=grade_9, 
            stream=stream_gen,
            name='A', 
            defaults={'capacity': 40}
        )

        # 4. Create Subjects
        math, _ = Subject.objects.get_or_create(school=school, code='MATH09', grade=grade_9, stream=stream_gen, defaults={'name': 'Mathematics'})
        english, _ = Subject.objects.get_or_create(school=school, code='ENG09', grade=grade_9, stream=stream_gen, defaults={'name': 'English'})
        physics, _ = Subject.objects.get_or_create(school=school, code='PHY09', grade=grade_9, stream=stream_gen, defaults={'name': 'Physics'})

        # 5. Create Demo Users (Password: password123)
        password = make_password('password123')

        users_to_create = [
            {'username': 'admin@addisacademy.edu.et', 'role': UserRole.SCHOOL_ADMIN, 'first_name': 'Abebe', 'last_name': 'Kebede'},
            {'username': 'principal@addisacademy.edu.et', 'role': UserRole.PRINCIPAL, 'first_name': 'Aster', 'last_name': 'Mekonnen'},
            {'username': 'teacher@addisacademy.edu.et', 'role': UserRole.TEACHER, 'first_name': 'Tilahun', 'last_name': 'Gessesse'},
            {'username': 'student@addisacademy.edu.et', 'role': UserRole.STUDENT, 'first_name': 'Dawit', 'last_name': 'Tilahun'},
            {'username': 'parent@addisacademy.edu.et', 'role': UserRole.PARENT, 'first_name': 'Tadesse', 'last_name': 'Alemu'},
            {'username': 'hr@addisacademy.edu.et', 'role': UserRole.SCHOOL_ADMIN, 'first_name': 'HR', 'last_name': 'Manager'},
            {'username': 'finance@addisacademy.edu.et', 'role': UserRole.ACCOUNTANT, 'first_name': 'Sara', 'last_name': 'Finance'},
        ]

        created_users = {}
        for u_data in users_to_create:
            user, created = User.objects.get_or_create(
                username=u_data['username'],
                defaults={
                    'email': u_data['username'],
                    'first_name': u_data['first_name'],
                    'last_name': u_data['last_name'],
                    'role': u_data['role'],
                    'school': school,
                    'password': password,
                    'is_staff': True if u_data['role'] in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN] else False
                }
            )
            created_users[u_data['role']] = user
            if created:
                self.stdout.write(f"Created {u_data['role']}: {u_data['username']}")

        # 6. Set up Teacher Profile
        teacher_user = created_users[UserRole.TEACHER]
        teacher_profile, _ = TeacherProfile.objects.get_or_create(
            user=teacher_user,
            school=school,
            defaults={
                'employee_id': 'TCH-001',
                'gender': 'M'
            }
        )
        section_9a.class_teacher = teacher_user
        section_9a.save()

        # 7. Set up Student Profile & Enrollment
        student_user = created_users[UserRole.STUDENT]
        student_profile, _ = StudentProfile.objects.get_or_create(
            user=student_user,
            school=school,
            defaults={
                'first_name': 'Dawit',
                'last_name': 'Tilahun',
                'admission_number': 'STU-001',
                'date_of_birth': datetime.date(2010, 5, 15),
                'gender': 'M',
                'status': StudentStatus.ACTIVE,
                'current_password_display': 'student123'
            }
        )
        student_profile.current_password_display = 'student123'
        student_profile.save()

        StudentEnrollment.objects.get_or_create(
            student=student_profile,
            school=school,
            academic_year=academic_year,
            grade=grade_9,
            stream=stream_gen,
            section=section_9a,
            defaults={'status': EnrollmentStatus.ACTIVE, 'enrollment_date': datetime.date(2026, 8, 25)}
        )

        # 8. Set up Parent Profile & Guardianship
        parent_user = created_users[UserRole.PARENT]
        parent_profile, _ = ParentProfile.objects.get_or_create(
            user=parent_user,
            school=school,
            defaults={
                'phone': '+251911998877',
                'relationship': 'Father',
                'current_password_display': 'parent123'
            }
        )
        parent_profile.current_password_display = 'parent123'
        parent_profile.save()
        GuardianRelationship.objects.get_or_create(
            parent=parent_profile,
            student=student_profile,
            school=school,
            defaults={'is_primary': True}
        )

        # 9. Set up 2nd Child for Parent Demo Testing
        student2_user, _ = User.objects.get_or_create(
            username='student2.demo',
            defaults={
                'email': 'meron.tilahun@demo.school.et',
                'first_name': 'Meron',
                'last_name': 'Tilahun',
                'role': UserRole.STUDENT,
                'school': school,
                'password': 'password123',
                'is_staff': False
            }
        )
        student2_user.set_password('password123')
        student2_user.save()

        student2_profile, _ = StudentProfile.objects.get_or_create(
            user=student2_user,
            school=school,
            defaults={
                'first_name': 'Meron',
                'last_name': 'Tilahun',
                'student_id': 'STU-DEMO-002',
                'admission_number': 'STU-DEMO-002',
                'date_of_birth': datetime.date(2008, 3, 10),
                'gender': 'F',
                'status': StudentStatus.ACTIVE,
                'current_password_display': 'student123'
            }
        )
        student2_profile.current_password_display = 'student123'
        student2_profile.save()

        # Grade 11 Natural Science
        grade_11 = Grade.objects.filter(school=school, level=11).first() or Grade.objects.create(school=school, level=11, name='Grade 11')
        stream_nat = Stream.objects.filter(school=school, code='NS').first() or Stream.objects.create(school=school, code='NS', name='Natural Science')
        section_11a = Section.objects.filter(school=school, grade=grade_11, stream=stream_nat, name='A').first() or Section.objects.create(school=school, grade=grade_11, stream=stream_nat, name='A')

        StudentEnrollment.objects.get_or_create(
            student=student2_profile,
            school=school,
            academic_year=academic_year,
            grade=grade_11,
            stream=stream_nat,
            section=section_11a,
            defaults={'status': EnrollmentStatus.ACTIVE, 'enrollment_date': datetime.date(2026, 8, 25)}
        )

        GuardianRelationship.objects.get_or_create(
            parent=parent_profile,
            student=student2_profile,
            school=school,
            defaults={'is_primary': True}
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded demo data for Addis International Academy!"))
        self.stdout.write(self.style.WARNING("You can now log in with the generated demo accounts using password 'password123'"))
