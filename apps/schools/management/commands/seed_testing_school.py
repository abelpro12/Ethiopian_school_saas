import datetime
import random
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import StudentEnrollment
from apps.library.models import Book, BookCopy, BookCategory, BookStatus

TEST_SCHOOL_CODE = "ADDIS-01"
TEST_SCHOOL_SUBDOMAIN = "addis"

ETHIOPIAN_FIRST_NAMES = [
    "Abebe", "Almaz", "Bekele", "Chala", "Dawit", "Eyob", "Fikirte", "Getachew", "Hana", "Iyasu",
    "Jemal", "Kaleb", "Lidetu", "Marta", "Nigest", "Omer", "Petros", "Rahel", "Selam", "Tadesse",
    "Yosef", "Zenebe", "Aster", "Biniam", "Daniel", "Eden", "Fikru", "Girma", "Helina", "Kassahun"
]
ETHIOPIAN_LAST_NAMES = [
    "Kebede", "Demissie", "Worku", "Tadesse", "Assefa", "Yilma", "Solomon", "Mohammed", "Haile", "Tekle",
    "Girma", "Bekele", "Alemu", "Teshale", "Desta", "Berhanu", "Ayalew", "Gebre", "Mekonnen", "Kassa"
]

class Command(BaseCommand):
    help = "Seeds a complete new school environment ('Addis Model Secondary School') with 10 sections, 100 students, 10 teachers, subjects, parents, and library books for testing."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Wipes the test school data before re-seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get('reset')
        self.stdout.write("Initializing Addis Model Secondary School Testing Environment...")

        if reset:
            self.stdout.write(self.style.WARNING(f"Resetting testing school ({TEST_SCHOOL_CODE})..."))
            User.objects.filter(username__startswith="addis_").delete()
            User.objects.filter(school__code=TEST_SCHOOL_CODE).delete()
            School.objects.filter(code=TEST_SCHOOL_CODE).delete()

        # 1. School Setup
        school, created = School.objects.get_or_create(
            code=TEST_SCHOOL_CODE,
            defaults={
                'name': "Addis Model Secondary School",
                'subdomain': TEST_SCHOOL_SUBDOMAIN,
                'motto': "Education for Tomorrow's Leaders",
                'phone': "+251911223344",
                'email': "info@addismodel.edu.et",
                'calendar_preference': "ETHIOPIAN"
            }
        )

        # 2. Academic Year & Period
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            name="2017 E.C. (2024/25)",
            defaults={
                'ethiopian_year': 2017,
                'gregorian_start_date': datetime.date(2024, 9, 11),
                'gregorian_end_date': datetime.date(2025, 6, 30),
                'ethiopian_start_date': "Meskerem 01, 2017 E.C.",
                'ethiopian_end_date': "Sene 23, 2017 E.C.",
                'is_active': True,
                'status': 'ACTIVE'
            }
        )

        period, _ = AcademicPeriod.objects.get_or_create(
            school=school,
            academic_year=ay,
            name="Semester 1",
            defaults={
                'start_date': datetime.date(2024, 9, 11),
                'end_date': datetime.date(2025, 1, 30),
                'is_current': True
            }
        )

        # 3. Grades & Streams
        g9, _ = Grade.objects.get_or_create(school=school, level=9, defaults={'name': "Grade 9", 'stream_type': 'GEN'})
        g10, _ = Grade.objects.get_or_create(school=school, level=10, defaults={'name': "Grade 10", 'stream_type': 'GEN'})
        g11_n, _ = Grade.objects.get_or_create(school=school, level=11, defaults={'name': "Grade 11 (NS)", 'stream_type': 'NAT'})
        g11_s, _ = Grade.objects.get_or_create(school=school, level=11, defaults={'name': "Grade 11 (SS)", 'stream_type': 'SOC'})
        g12_n, _ = Grade.objects.get_or_create(school=school, level=12, defaults={'name': "Grade 12 (NS)", 'stream_type': 'NAT'})
        g12_s, _ = Grade.objects.get_or_create(school=school, level=12, defaults={'name': "Grade 12 (SS)", 'stream_type': 'SOC'})

        gen_stream, _ = Stream.objects.get_or_create(school=school, code="GEN", defaults={'name': "General Stream"})
        nat_stream, _ = Stream.objects.get_or_create(school=school, code="NAT", defaults={'name': "Natural Science"})
        soc_stream, _ = Stream.objects.get_or_create(school=school, code="SOC", defaults={'name': "Social Science"})

        # 4. Operational Staff Accounts
        def create_staff_user(username, email, first_name, last_name, role, password):
            u, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email, 'school': school, 'role': role,
                    'first_name': first_name, 'last_name': last_name, 'is_staff': True
                }
            )
            u.set_password(password)
            u.save()
            return u

        admin_user = create_staff_user("addis_admin", "admin@addismodel.edu.et", "Kassahun", "Worku", UserRole.SCHOOL_ADMIN, "admin123")
        principal_user = create_staff_user("addis_principal", "principal@addismodel.edu.et", "Dr. Solomon", "Haile", UserRole.PRINCIPAL, "principal123")
        registrar_user = create_staff_user("addis_registrar", "registrar@addismodel.edu.et", "Martha", "Berhanu", UserRole.REGISTRAR, "registrar123")
        librarian_user = create_staff_user("addis_librarian", "librarian@addismodel.edu.et", "Eden", "Desta", UserRole.LIBRARIAN, "librarian123")

        # 5. 10 Teachers & Profiles
        teachers = []
        teacher_names = [
            ("Abebe", "Demissie", "Mathematics"),
            ("Betelhem", "Tadesse", "Physics"),
            ("Chala", "Girma", "Chemistry"),
            ("Dawit", "Kebede", "English"),
            ("Eyob", "Mengistu", "Amharic"),
            ("Fikirte", "Worku", "Biology"),
            ("Getachew", "Assefa", "History"),
            ("Hana", "Yilma", "Geography"),
            ("Iyasu", "Solomon", "Marketing"),
            ("Jemal", "Mohammed", "Mathematics & Physics"),
        ]

        for idx, (fn, ln, spec) in enumerate(teacher_names, start=1):
            u = create_staff_user(f"addis_teacher_{idx}", f"teacher{idx}@addismodel.edu.et", fn, ln, UserRole.TEACHER, "teacher123")
            tp, _ = TeacherProfile.objects.get_or_create(
                school=school, employee_id=f"EMP-ADDIS-00{idx}",
                defaults={'user': u, 'qualification': "B.Ed / M.Sc", 'specialization': spec, 'employment_status': 'FULL_TIME'}
            )
            teachers.append(tp)

        # 6. Sections (10 Class Sections) & Homeroom Teacher Assignments
        section_configs = [
            ("9-A", g9, gen_stream, teachers[0]),
            ("9-B", g9, gen_stream, teachers[1]),
            ("10-A", g10, gen_stream, teachers[2]),
            ("10-B", g10, gen_stream, teachers[3]),
            ("11-NS-A", g11_n, nat_stream, teachers[4]),
            ("11-NS-B", g11_n, nat_stream, teachers[5]),
            ("11-SS-A", g11_s, soc_stream, teachers[6]),
            ("11-SS-B", g11_s, soc_stream, teachers[7]),
            ("12-NS-A", g12_n, nat_stream, teachers[8]),
            ("12-NS-B", g12_n, nat_stream, teachers[9]),
        ]

        section_objs = {}
        for sname, gr, st, hr_teacher in section_configs:
            sec, _ = Section.objects.get_or_create(
                school=school, name=sname, grade=gr, stream=st,
                defaults={'capacity': 40, 'class_teacher': hr_teacher.user}
            )
            section_objs[sname] = sec

        # 7. Subjects & Teacher Assignments
        # General Stream (Grades 9 & 10) Subjects
        gen_subjects_data = [
            ("MTH", "Mathematics"), ("PHY", "Physics"), ("CHM", "Chemistry"), ("AMH", "Amharic"), ("ENG", "English")
        ]
        # Natural Science (Grades 11 & 12) Subjects
        ns_subjects_data = [
            ("MTH", "Mathematics"), ("ENG", "English"), ("CHM", "Chemistry"), ("PHY", "Physics"), ("BIO", "Biology")
        ]
        # Social Science (Grades 11 & 12) Subjects
        ss_subjects_data = [
            ("HIS", "History"), ("GEO", "Geography"), ("MKT", "Marketing / Economics"), ("MTH", "Mathematics"), ("ENG", "English")
        ]

        def seed_grade_subjects(gr, st, subject_list):
            created_subs = []
            for code_prefix, sname in subject_list:
                code = f"{code_prefix}-{gr.level}"
                if st.code != 'GEN':
                    code += f"-{st.code}"
                sub, _ = Subject.objects.get_or_create(
                    school=school, code=code, grade=gr, stream=st,
                    defaults={'name': sname}
                )
                created_subs.append(sub)
            return created_subs

        sub_g9 = seed_grade_subjects(g9, gen_stream, gen_subjects_data)
        sub_g10 = seed_grade_subjects(g10, gen_stream, gen_subjects_data)
        sub_g11_n = seed_grade_subjects(g11_n, nat_stream, ns_subjects_data)
        sub_g11_s = seed_grade_subjects(g11_s, soc_stream, ss_subjects_data)
        sub_g12_n = seed_grade_subjects(g12_n, nat_stream, ns_subjects_data)
        sub_g12_s = seed_grade_subjects(g12_s, soc_stream, ss_subjects_data)

        # Assign subjects to teachers across sections
        for sname, sec in section_objs.items():
            subs = []
            if "9-" in sname: subs = sub_g9
            elif "10-" in sname: subs = sub_g10
            elif "11-NS" in sname: subs = sub_g11_n
            elif "11-SS" in sname: subs = sub_g11_s
            elif "12-NS" in sname: subs = sub_g12_n
            elif "12-SS" in sname: subs = sub_g12_s

            for i, sub in enumerate(subs):
                assigned_teacher = teachers[i % len(teachers)]
                TeacherAssignment.objects.get_or_create(
                    school=school, academic_year=ay, teacher=assigned_teacher, subject=sub, section=sec
                )

        # 8. Seed 100 Students (10 per section) & Parents
        student_counter = 1
        created_students = []

        for sname, sec in section_objs.items():
            for idx in range(1, 11):
                fn = ETHIOPIAN_FIRST_NAMES[(student_counter * 3) % len(ETHIOPIAN_FIRST_NAMES)]
                ln = ETHIOPIAN_LAST_NAMES[(student_counter * 5) % len(ETHIOPIAN_LAST_NAMES)]
                stu_id = f"ADDIS-S{student_counter:03d}"
                username = f"addis_stu_{student_counter:03d}"

                u_stu, _ = User.objects.get_or_create(
                    username=username,
                    defaults={'email': f"{username}@addismodel.edu.et", 'school': school, 'role': UserRole.STUDENT, 'first_name': fn, 'last_name': ln}
                )
                u_stu.set_password("student123")
                u_stu.save()

                sp, _ = StudentProfile.objects.get_or_create(
                    school=school, student_id=stu_id,
                    defaults={'user': u_stu, 'first_name': fn, 'last_name': ln, 'gender': 'M' if idx % 2 == 1 else 'F'}
                )

                # Enrollment for active year 2017 E.C.
                StudentEnrollment.objects.get_or_create(
                    school=school, student=sp, academic_year=ay,
                    defaults={'grade': sec.grade, 'stream': sec.stream, 'section': sec, 'status': 'ACTIVE'}
                )

                # Parent Account (1 Parent per 2 students)
                if idx % 2 == 1:
                    p_idx = (student_counter + 1) // 2
                    p_fn = ETHIOPIAN_FIRST_NAMES[(p_idx * 7) % len(ETHIOPIAN_FIRST_NAMES)]
                    p_ln = ln
                    u_par, _ = User.objects.get_or_create(
                        username=f"addis_parent_{p_idx:02d}",
                        defaults={'email': f"parent{p_idx}@addismodel.edu.et", 'school': school, 'role': UserRole.PARENT, 'first_name': p_fn, 'last_name': p_ln}
                    )
                    u_par.set_password("parent123")
                    u_par.save()

                    pp, _ = ParentProfile.objects.get_or_create(
                        school=school, user=u_par,
                        defaults={'phone': f"+251911{p_idx:06d}", 'relationship': 'Father' if p_idx % 2 == 1 else 'Mother'}
                    )
                    GuardianRelationship.objects.get_or_create(
                        school=school, parent=pp, student=sp,
                        defaults={'is_primary': True}
                    )

                created_students.append(sp)
                student_counter += 1

        # 9. 5 Library Books & Copies
        books_data = [
            ("Grade 9 Mathematics Textbook", "Dr. Worku & Team", "MTH-9001", BookCategory.TEXTBOOK, "Mathematics", "Grade 9", 10),
            ("Grade 10 Physics Textbook", "Dr. Tadesse Kebede", "PHY-1002", BookCategory.TEXTBOOK, "Physics", "Grade 10", 10),
            ("Ethiopian History & Heritage Reference", "Prof. Lapiso G. Dilebo", "HIS-REF-01", BookCategory.REFERENCE, "History", "Grade 9-12", 5),
            ("Grade 11 Chemistry (Natural Science)", "Ministry of Education ET", "CHM-1101", BookCategory.TEXTBOOK, "Chemistry", "Grade 11", 10),
            ("Grade 12 Geography (Social Science)", "Dr. Berhanu Desta", "GEO-1201", BookCategory.TEXTBOOK, "Geography", "Grade 12", 10),
        ]

        for title, author, isbn, category, subject, grade_level, total_copies in books_data:
            b, _ = Book.objects.get_or_create(
                school=school, isbn=isbn,
                defaults={
                    'title': title, 'author': author, 'category': category,
                    'subject': subject, 'grade_level': grade_level, 'total_copies': total_copies
                }
            )
            for c_idx in range(1, total_copies + 1):
                BookCopy.objects.get_or_create(
                    school=school, book=b, copy_number=f"COPY-{c_idx:03d}",
                    defaults={'status': BookStatus.AVAILABLE}
                )

        self.stdout.write(self.style.SUCCESS("Successfully seeded 'Addis Model Secondary School'!"))
        self.stdout.write(self.style.SUCCESS("--------------------------------------------------"))
        self.stdout.write("School Subdomain: addis")
        self.stdout.write("Academic Year:    2017 E.C. (2024/25)")
        self.stdout.write("Class Sections:   10 Sections (9-A, 9-B, 10-A, 10-B, 11-NS-A, 11-NS-B, 11-SS-A, 11-SS-B, 12-NS-A, 12-NS-B)")
        self.stdout.write("Total Students:   100 Students (10 in each class)")
        self.stdout.write("Total Teachers:   10 Teachers (assigned as Homeroom Teachers for all 10 sections)")
        self.stdout.write("Subjects:         5 Subjects per stream/grade")
        self.stdout.write("Library Books:    5 Library Books with multiple copies")
        self.stdout.write("--------------------------------------------------")
        self.stdout.write("DEMO CREDENTIALS FOR TESTING:")
        self.stdout.write("  School Admin:   addis_admin / admin123")
        self.stdout.write("  Principal:      addis_principal / principal123")
        self.stdout.write("  Registrar:      addis_registrar / registrar123")
        self.stdout.write("  Librarian:      addis_librarian / librarian123")
        self.stdout.write("  Teacher (9A):   addis_teacher_1 / teacher123")
        self.stdout.write("  Student (9A):   addis_stu_001 / student123")
        self.stdout.write("  Parent:         addis_parent_01 / parent123")
        self.stdout.write("--------------------------------------------------")
