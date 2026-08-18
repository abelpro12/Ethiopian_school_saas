import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment
from apps.finance.models import FeeCategory, StudentInvoice, InvoiceStatus


class Command(BaseCommand):
    help = "Seeds initial Ethiopian High School (Grades 9-12) demo data."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Ethiopian High School (Grades 9-12) demo structure...")

        # 1. School
        school, _ = School.objects.get_or_create(
            code="AIA-01",
            defaults={
                'name': "Addis International Secondary & Preparatory School",
                'subdomain': "addis",
                'motto': "Excellence in Ethiopian High School Education",
                'phone': "+251911121314",
                'email': "info@addisacademy.edu.et",
                'calendar_preference': "ETHIOPIAN"
            }
        )

        # 2. Ethiopian High School Grades (9, 10, 11, 12)
        g9, _ = Grade.objects.get_or_create(school=school, level=9, defaults={'name': "Grade 9"})
        g10, _ = Grade.objects.get_or_create(school=school, level=10, defaults={'name': "Grade 10"})
        g11, _ = Grade.objects.get_or_create(school=school, level=11, defaults={'name': "Grade 11"})
        g12, _ = Grade.objects.get_or_create(school=school, level=12, defaults={'name': "Grade 12"})

        # 3. High School Streams
        gen_stream, _ = Stream.objects.get_or_create(school=school, code="GEN", defaults={'name': "General Stream (Grades 9-10)"})
        nat_stream, _ = Stream.objects.get_or_create(school=school, code="NAT", defaults={'name': "Natural Science Stream (Grades 11-12)"})
        soc_stream, _ = Stream.objects.get_or_create(school=school, code="SOC", defaults={'name': "Social Science Stream (Grades 11-12)"})

        # 4. High School Subjects
        subjects_data = [
            # General (9-10)
            ('ENG-09', 'English Language', 'እንግሊዝኛ', g9, gen_stream),
            ('MTH-09', 'Mathematics', 'ሒሳብ', g9, gen_stream),
            ('PHY-09', 'Physics', 'ፊዚክስ', g9, gen_stream),
            ('CHM-09', 'Chemistry', 'ኬሚስትሪ', g9, gen_stream),
            ('BIO-09', 'Biology', 'ባዮሎጂ', g9, gen_stream),
            ('AMH-09', 'Amharic', 'አማርኛ', g9, gen_stream),
            ('ICT-09', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g9, gen_stream),

            # Natural Science (11-12)
            ('PHY-11', 'Physics (Natural)', 'ፊዚክስ', g11, nat_stream),
            ('CHM-11', 'Chemistry (Natural)', 'ኬሚስትሪ', g11, nat_stream),
            ('BIO-11', 'Biology (Natural)', 'ባዮሎጂ', g11, nat_stream),
            ('MTH-11N', 'Mathematics (Natural)', 'ሒሳብ', g11, nat_stream),
            ('ENG-11', 'English Language', 'እንግሊዝኛ', g11, nat_stream),

            # Social Science (11-12)
            ('HIS-11', 'History (Social)', 'ታሪክ', g11, soc_stream),
            ('GEO-11', 'Geography (Social)', 'ጂኦግራፊ', g11, soc_stream),
            ('ECN-11', 'Economics (Social)', 'ኢኮኖሚክስ', g11, soc_stream),
            ('MTH-11S', 'Mathematics (Social)', 'ሒሳብ', g11, soc_stream),
        ]

        for code, name, amharic, gr, st in subjects_data:
            Subject.objects.get_or_create(
                school=school,
                code=code,
                grade=gr,
                stream=st,
                defaults={'name': name, 'amharic_name': amharic}
            )

        # 5. Super Admin
        superadmin, _ = User.objects.get_or_create(
            username="superadmin",
            defaults={'email': "superadmin@saas.et", 'role': UserRole.SUPER_ADMIN, 'is_staff': True, 'is_superuser': True}
        )
        superadmin.set_password("admin123")
        superadmin.save()

        # 6. School Admin
        schooladmin, _ = User.objects.get_or_create(
            username="schooladmin",
            defaults={'email': "admin@addisacademy.edu.et", 'school': school, 'role': UserRole.SCHOOL_ADMIN, 'is_staff': True}
        )
        schooladmin.set_password("admin123")
        schooladmin.save()

        # 7. Teacher
        teacher_u, _ = User.objects.get_or_create(
            username="teacher",
            defaults={'first_name': "Alemayehu", 'last_name': "Tessema", 'school': school, 'role': UserRole.TEACHER}
        )
        teacher_u.set_password("teacher123")
        teacher_u.save()

        teacher_p, _ = TeacherProfile.objects.get_or_create(
            school=school,
            employee_id="EMP-101",
            defaults={'user': teacher_u, 'qualification': "M.Sc. Physics", 'specialization': "Physics"}
        )

        # 8. Parent & Student
        parent_u, _ = User.objects.get_or_create(
            username="parent",
            defaults={'first_name': "Kebede", 'last_name': "Tadesse", 'school': school, 'role': UserRole.PARENT}
        )
        parent_u.set_password("parent123")
        parent_u.save()

        parent_p, _ = ParentProfile.objects.get_or_create(
            school=school,
            user=parent_u,
            defaults={'phone': "+251911000000", 'relationship': "Father"}
        )

        student_u, _ = User.objects.get_or_create(
            username="student",
            defaults={'first_name': "Abebe", 'last_name': "Kebede", 'school': school, 'role': UserRole.STUDENT}
        )
        student_u.set_password("student123")
        student_u.save()

        student_p, _ = StudentProfile.objects.get_or_create(
            school=school,
            student_id="AIA-STU-001",
            defaults={'user': student_u, 'first_name': "Abebe", 'middle_name': "Kebede", 'last_name': "Tadesse", 'gender': "M"}
        )

        GuardianRelationship.objects.get_or_create(school=school, parent=parent_p, student=student_p, defaults={'is_primary': True})

        # 9. Academic Year & Sections
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            name="2016 E.C. (2023/24)",
            defaults={'ethiopian_year': 2016, 'gregorian_start_date': datetime.date(2023, 9, 12), 'gregorian_end_date': datetime.date(2024, 6, 30), 'is_active': True}
        )

        sem1, _ = AcademicPeriod.objects.get_or_create(
            school=school,
            academic_year=ay,
            name="AcademicPeriod 1",
            defaults={'start_date': datetime.date(2023, 9, 12), 'end_date': datetime.date(2024, 1, 20), 'is_current': True}
        )

        sec11_nat, _ = Section.objects.get_or_create(school=school, academic_year=ay, grade=g11, stream=nat_stream, name="11-Nat-1")
        sec9_gen, _ = Section.objects.get_or_create(school=school, academic_year=ay, grade=g9, stream=gen_stream, name="9-A")

        physics_11 = Subject.objects.get(school=school, code="PHY-11")

        TeacherAssignment.objects.get_or_create(school=school, academic_year=ay, teacher=teacher_p, subject=physics_11, section=sec11_nat)
        StudentEnrollment.objects.get_or_create(school=school, academic_year=ay, student=student_p, defaults={'grade': g11, 'stream': nat_stream, 'section': sec11_nat})

        # Invoice
        fee_cat, _ = FeeCategory.objects.get_or_create(school=school, name="Tuition Fee")
        StudentInvoice.objects.get_or_create(
            school=school,
            invoice_number="INV-2016-001",
            defaults={'student': student_p, 'academic_year': ay, 'period': sem1, 'total_amount': Decimal('5000.00'), 'due_date': datetime.date(2024, 2, 1), 'status': InvoiceStatus.UNPAID}
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded Ethiopian High School (Grades 9-12) structure!"))
