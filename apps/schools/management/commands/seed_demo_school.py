import datetime
import random
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment
from apps.finance.models import FeeCategory, StudentInvoice, InvoiceStatus

QA_SCHOOL_CODE = "QA-DEMO-01"
QA_SCHOOL_SUBDOMAIN = "qa-demo"

class Command(BaseCommand):
    help = "Seeds a comprehensive Ethiopian demo school environment for QA and testing."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Wipes the QA demo school data before seeding. Only affects the dedicated QA school.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get('reset')
        
        self.stdout.write("Initializing QA Demo School Environment...")

        if reset:
            self.stdout.write(self.style.WARNING(f"Resetting QA demo school ({QA_SCHOOL_CODE})..."))
            User.objects.filter(username__icontains="qa-").delete()
            User.objects.filter(school__code=QA_SCHOOL_CODE).delete()
            for s in School.objects.filter(code=QA_SCHOOL_CODE):
                s.delete()

        # 1. School
        school, created = School.objects.get_or_create(
            code=QA_SCHOOL_CODE,
            defaults={
                'name': "QA Demo High School (Testing Only)",
                'subdomain': QA_SCHOOL_SUBDOMAIN,
                'motto': "Testing Excellence",
                'phone': "+251911000000",
                'email': "testadmin@qa.saas.et",
                'calendar_preference': "ETHIOPIAN"
            }
        )
        if not created and not reset:
             self.stdout.write(self.style.WARNING("QA Demo School already exists. Use --reset to recreate."))

        # 2. Grades
        g9, _ = Grade.objects.get_or_create(school=school, level=9, defaults={'name': "Grade 9"})
        g10, _ = Grade.objects.get_or_create(school=school, level=10, defaults={'name': "Grade 10"})
        g11, _ = Grade.objects.get_or_create(school=school, level=11, defaults={'name': "Grade 11"})
        g12, _ = Grade.objects.get_or_create(school=school, level=12, defaults={'name': "Grade 12"})

        # 3. Streams
        gen_stream, _ = Stream.objects.get_or_create(school=school, code="GEN", defaults={'name': "General Stream"})
        nat_stream, _ = Stream.objects.get_or_create(school=school, code="NAT", defaults={'name': "Natural Science"})
        soc_stream, _ = Stream.objects.get_or_create(school=school, code="SOC", defaults={'name': "Social Science"})

        # 4. Subjects
        subjects = [
            ('ENG-09', 'English 9', g9, gen_stream),
            ('MTH-09', 'Mathematics 9', g9, gen_stream),
            ('PHY-09', 'Physics 9', g9, gen_stream),
            ('ENG-10', 'English 10', g10, gen_stream),
            ('MTH-10', 'Mathematics 10', g10, gen_stream),
            ('PHY-11', 'Physics 11', g11, nat_stream),
            ('HIS-11', 'History 11', g11, soc_stream)
        ]
        subject_objs = {}
        for code, name, gr, st in subjects:
            sub, _ = Subject.objects.get_or_create(
                school=school, code=code, grade=gr, stream=st, defaults={'name': name}
            )
            subject_objs[code] = sub

        # 5. Admin User
        admin_u, _ = User.objects.get_or_create(
            username=f"{QA_SCHOOL_SUBDOMAIN}_admin",
            defaults={'email': "admin@qa.saas.et", 'school': school, 'role': UserRole.SCHOOL_ADMIN, 'is_staff': True}
        )
        admin_u.set_password("admin123")
        admin_u.save()

        # 6. Academic Year
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            name="QA Test Year 2016",
            defaults={
                'ethiopian_year': 2016, 
                'gregorian_start_date': datetime.date(2023, 9, 12), 
                'gregorian_end_date': datetime.date(2024, 6, 30), 
                'is_active': True
            }
        )

        sem1, _ = AcademicPeriod.objects.get_or_create(
            school=school, academic_year=ay, name="Period 1",
            defaults={'start_date': datetime.date(2023, 9, 12), 'end_date': datetime.date(2024, 1, 20), 'is_current': True}
        )
        
        # Sections
        sec9a, _ = Section.objects.get_or_create(school=school, grade=g9, stream=gen_stream, name="9-A")
        sec10a, _ = Section.objects.get_or_create(school=school, grade=g10, stream=gen_stream, name="10-A")
        sec11nat, _ = Section.objects.get_or_create(school=school, grade=g11, stream=nat_stream, name="11-Nat-A")
        sec11soc, _ = Section.objects.get_or_create(school=school, grade=g11, stream=soc_stream, name="11-Soc-A")
        sec12nat, _ = Section.objects.get_or_create(school=school, grade=g12, stream=nat_stream, name="12-Nat-A")
        sec12soc, _ = Section.objects.get_or_create(school=school, grade=g12, stream=soc_stream, name="12-Soc-A")

        # 7. Generate 50 Realistic Students
        self.stdout.write("Generating 50 students, parents, and enrollments with edge cases...")
        
        fee_cat, _ = FeeCategory.objects.get_or_create(school=school, name="Tuition Fee")
        
        first_names = ["Abebe", "Kebede", "Aster", "Tigist", "Biniam", "Dawit", "Emebet", "Fikru", "Girma", "Hana", "Meron", "Samuel", "Tadesse", "Yonas"]
        last_names = ["Tessema", "Mulugeta", "Bekele", "Alemu", "Hailu", "Assefa", "Tadesse", "Kassa", "Woldemariam"]

        for i in range(1, 51):
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            student_id = f"QA-STU-{i:03d}"
            
            # Student User
            s_u, _ = User.objects.get_or_create(
                username=student_id.lower(),
                defaults={'first_name': fname, 'last_name': lname, 'school': school, 'role': UserRole.STUDENT}
            )
            s_u.school = school
            s_u.set_password("student123")
            s_u.save()

            # Student Profile
            s_p, _ = StudentProfile.objects.get_or_create(
                user=s_u,
                defaults={'school': school, 'student_id': student_id, 'first_name': fname, 'middle_name': lname, 'last_name': "Gizaw", 'gender': random.choice(["M", "F"])}
            )
            s_p.school = school
            s_p.student_id = student_id
            s_p.current_password_display = "student123"
            s_p.save()

            # Parent User
            p_u, _ = User.objects.get_or_create(
                username=f"p_{student_id.lower()}",
                defaults={'first_name': lname, 'last_name': "Gizaw", 'school': school, 'role': UserRole.PARENT}
            )
            p_u.school = school
            p_u.set_password("parent123")
            p_u.save()
            
            p_p, _ = ParentProfile.objects.get_or_create(
                user=p_u,
                defaults={'school': school, 'phone': f"+25191100{i:03d}", 'relationship': "Father", 'current_password_display': "parent123"}
            )
            p_p.school = school
            p_p.current_password_display = "parent123"
            p_p.save()
            
            GuardianRelationship.objects.get_or_create(school=school, parent=p_p, student=s_p, defaults={'is_primary': True})

            # Enrollment & Invoicing
            if i <= 20:
                 enr_g = g9; enr_st = gen_stream; enr_sec = sec9a
            elif i <= 35:
                 enr_g = g10; enr_st = gen_stream; enr_sec = sec10a
            else:
                 enr_g = g11; enr_st = nat_stream; enr_sec = sec11nat
                 
            StudentEnrollment.objects.get_or_create(school=school, academic_year=ay, student=s_p, defaults={'grade': enr_g, 'stream': enr_st, 'section': enr_sec})
            
            # Create a mix of paid and unpaid invoices
            inv_status = InvoiceStatus.PAID if i % 3 != 0 else InvoiceStatus.UNPAID
            StudentInvoice.objects.get_or_create(
                school=school, invoice_number=f"QA-INV-{i:03d}",
                defaults={'student': s_p, 'academic_year': ay, 'period': sem1, 'total_amount': Decimal('5000.00'), 'due_date': datetime.date(2024, 2, 1), 'status': inv_status}
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded QA Demo School! Log in with: {QA_SCHOOL_SUBDOMAIN}_admin / admin123"))
