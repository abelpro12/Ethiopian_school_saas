import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.teachers.models import TeacherProfile, TeacherAssignment, EmploymentStatus
from apps.students.models import StudentProfile, StudentStatus
from apps.enrollment.models import StudentEnrollment, SubjectEnrollment, EnrollmentStatus, AdmissionType

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds Seattle Academy with 4 Grades (9, 10, 11, 12), 8 Sections, 8 Homeroom Teachers, Curriculum Subjects, and Unique Students."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE(">>> Setting up Seattle Academy (SEA)..."))

        # 1. School
        school, _ = School.objects.get_or_create(
            code="SEA",
            defaults={
                'name': "SEATTLE ACADEMY",
                'subdomain': "seattle",
                'motto': "Excellence in Ethiopian High School & STEM Education",
                'phone': "+251 11 888 3504",
                'email': "info@seattleacademyethiopia.com",
                'address': "Kality, Addis Ababa, Ethiopia",
                'city': "Addis Ababa",
                'status': SchoolStatus.ACTIVE,
                'is_active': True,
                'calendar_preference': "ETHIOPIAN",
                'logo': 'school_logos/seattle_academy_logo.png'
            }
        )
        school.name = "SEATTLE ACADEMY"
        school.logo = 'school_logos/seattle_academy_logo.png'
        school.status = SchoolStatus.ACTIVE
        school.is_active = True
        school.save()

        # 2. Academic Year
        # 2018 E.C. (2025/2026 G.C)
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            ethiopian_year=2018,
            defaults={
                'name': "2018 E.C. (2025/2026 G.C)",
                'gregorian_start_date': datetime.date(2025, 9, 11),
                'gregorian_end_date': datetime.date(2026, 7, 7),
                'is_active': True
            }
        )
        ay.is_active = True
        ay.save()

        # Academic Periods (Semesters)
        sem1, _ = AcademicPeriod.objects.get_or_create(
            school=school,
            academic_year=ay,
            name="Semester 1",
            defaults={
                'start_date': datetime.date(2025, 9, 11),
                'end_date': datetime.date(2026, 1, 25),
                'is_current': True
            }
        )
        sem1.is_current = True
        sem1.save()

        sem2, _ = AcademicPeriod.objects.get_or_create(
            school=school,
            academic_year=ay,
            name="Semester 2",
            defaults={
                'start_date': datetime.date(2026, 2, 5),
                'end_date': datetime.date(2026, 7, 7),
                'is_current': False
            }
        )

        # 3. Streams
        gen_stream, _ = Stream.objects.get_or_create(school=school, code="GEN", defaults={'name': "General Stream (Grades 9-10)"})
        nat_stream, _ = Stream.objects.get_or_create(school=school, code="NAT", defaults={'name': "Natural Science Stream (Grades 11-12)"})
        soc_stream, _ = Stream.objects.get_or_create(school=school, code="SOC", defaults={'name': "Social Science Stream (Grades 11-12)"})

        # 4. Grades
        g9, _ = Grade.objects.get_or_create(school=school, level=9, defaults={'name': "Grade 9"})
        g10, _ = Grade.objects.get_or_create(school=school, level=10, defaults={'name': "Grade 10"})
        g11, _ = Grade.objects.get_or_create(school=school, level=11, defaults={'name': "Grade 11"})
        g12, _ = Grade.objects.get_or_create(school=school, level=12, defaults={'name': "Grade 12"})

        # 5. The 8 Dedicated Teachers
        teachers_data = [
            # (username, first, last, gender, phone, qual, spec, dept, emp_id, target_section_key)
            ("dawit_teacher", "Dawit", "Tadesse", "M", "+251911440001", "B.Sc. Mathematics", "Calculus & Geometry", "Mathematics", "SEA-TCH-0001", "9A"),
            ("aster_teacher", "Aster", "Bekele", "F", "+251911440002", "B.Ed. English Literature", "Advanced Linguistics", "English", "SEA-TCH-0002", "9B"),
            ("solomon_teacher", "Solomon", "Hailemariam", "M", "+251911440003", "M.Sc. Physics", "Mechanics & Optics", "Natural Sciences", "SEA-TCH-0003", "10A"),
            ("bethlehem_teacher", "Bethlehem", "Girma", "F", "+251911440004", "B.Sc. Chemistry", "Organic Chemistry", "Natural Sciences", "SEA-TCH-0004", "10B"),
            ("yohannes_teacher", "Yohannes", "Worku", "M", "+251911440005", "M.Sc. Biology & Genetics", "Molecular Biology", "Natural Sciences", "SEA-TCH-0005", "11 NS"),
            ("tigist_teacher", "Tigist", "Assefa", "F", "+251911440006", "M.A. History & Heritage", "African & World History", "Social Sciences", "SEA-TCH-0006", "11 SS"),
            ("ermias_teacher", "Ermias", "Kebede", "M", "+251911440007", "M.Sc. Applied Mathematics", "Applied Calculus", "Mathematics", "SEA-TCH-0007", "12 NS"),
            ("selamawit_teacher", "Selamawit", "Alemu", "F", "+251911440008", "M.A. Economics", "Macroeconomics", "Social Sciences", "SEA-TCH-0008", "12 SS"),
        ]

        teacher_profiles = {}
        for uname, fname, lname, gdr, ph, qual, spec, dept, eid, sec_key in teachers_data:
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f"{uname}@seattleacademyethiopia.com",
                    'first_name': fname,
                    'last_name': lname,
                    'role': UserRole.TEACHER,
                    'school': school,
                    'is_staff': True,
                    'is_active': True
                }
            )
            u.first_name = fname
            u.last_name = lname
            u.school = school
            u.role = UserRole.TEACHER
            u.is_active = True
            u.set_password("teacher123")
            u.save()

            tp, _ = TeacherProfile.objects.get_or_create(
                school=school,
                employee_id=eid,
                defaults={
                    'user': u,
                    'gender': gdr,
                    'phone': ph,
                    'qualification': qual,
                    'specialization': spec,
                    'department': dept,
                    'employment_status': EmploymentStatus.FULL_TIME
                }
            )
            tp.user = u
            tp.qualification = qual
            tp.specialization = spec
            tp.department = dept
            tp.save()
            teacher_profiles[sec_key] = tp

        self.stdout.write(self.style.SUCCESS(f"Created/Verified {len(teacher_profiles)} teachers."))

        # 6. Sections (8 sections with assigned homeroom teachers)
        sections_config = [
            ("9A", g9, gen_stream, teacher_profiles["9A"].user),
            ("9B", g9, gen_stream, teacher_profiles["9B"].user),
            ("10A", g10, gen_stream, teacher_profiles["10A"].user),
            ("10B", g10, gen_stream, teacher_profiles["10B"].user),
            ("11 NS", g11, nat_stream, teacher_profiles["11 NS"].user),
            ("11 SS", g11, soc_stream, teacher_profiles["11 SS"].user),
            ("12 NS", g12, nat_stream, teacher_profiles["12 NS"].user),
            ("12 SS", g12, soc_stream, teacher_profiles["12 SS"].user),
        ]

        sections = {}
        for sname, sgrade, sstream, homeroom_user in sections_config:
            sec, _ = Section.objects.get_or_create(
                school=school,
                grade=sgrade,
                stream=sstream,
                name=sname,
                defaults={
                    'class_teacher': homeroom_user,
                    'capacity': 45,
                    'shift': 'FULL_DAY',
                    'is_active': True
                }
            )
            sec.class_teacher = homeroom_user
            sec.is_active = True
            sec.save()
            sections[sname] = sec
            self.stdout.write(f"  Section {sgrade.name} - {sname} -> Homeroom Teacher: {homeroom_user.get_full_name()}")

        # 7. Subjects (at least 5-10 subjects per grade & stream)
        subjects_spec = [
            # Grade 9 General
            ('ENG-09', 'English Language', 'እንግሊዝኛ', g9, gen_stream),
            ('MTH-09', 'Mathematics', 'ሒሳብ', g9, gen_stream),
            ('PHY-09', 'Physics', 'ፊዚክስ', g9, gen_stream),
            ('CHM-09', 'Chemistry', 'ኬሚስትሪ', g9, gen_stream),
            ('BIO-09', 'Biology', 'ባዮሎጂ', g9, gen_stream),
            ('AMH-09', 'Amharic', 'አማርኛ', g9, gen_stream),
            ('ICT-09', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g9, gen_stream),
            ('GEO-09', 'Geography', 'ጂኦግራፊ', g9, gen_stream),
            ('HIS-09', 'History', 'ታሪክ', g9, gen_stream),
            ('CIT-09', 'Citizenship', 'የዜግነት ትምህርት', g9, gen_stream),

            # Grade 10 General
            ('ENG-10', 'English Language', 'እንግሊዝኛ', g10, gen_stream),
            ('MTH-10', 'Mathematics', 'ሒሳብ', g10, gen_stream),
            ('PHY-10', 'Physics', 'ፊዚክስ', g10, gen_stream),
            ('CHM-10', 'Chemistry', 'ኬሚስትሪ', g10, gen_stream),
            ('BIO-10', 'Biology', 'ባዮሎጂ', g10, gen_stream),
            ('AMH-10', 'Amharic', 'አማርኛ', g10, gen_stream),
            ('ICT-10', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g10, gen_stream),
            ('GEO-10', 'Geography', 'ጂኦግራፊ', g10, gen_stream),
            ('HIS-10', 'History', 'ታሪክ', g10, gen_stream),
            ('CIT-10', 'Citizenship', 'የዜግነት ትምህርት', g10, gen_stream),

            # Grade 11 Natural Science (NAT)
            ('ENG-11N', 'English Language', 'እንግሊዝኛ', g11, nat_stream),
            ('MTH-11N', 'Mathematics', 'ሒሳብ', g11, nat_stream),
            ('PHY-11', 'Physics', 'ፊዚክስ', g11, nat_stream),
            ('CHM-11', 'Chemistry', 'ኬሚስትሪ', g11, nat_stream),
            ('BIO-11', 'Biology', 'ባዮሎጂ', g11, nat_stream),
            ('ICT-11', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g11, nat_stream),
            ('AGR-11', 'Agriculture', 'ግብርና', g11, nat_stream),

            # Grade 11 Social Science (SOC)
            ('ENG-11S', 'English Language', 'እንግሊዝኛ', g11, soc_stream),
            ('MTH-11S', 'Mathematics', 'ሒሳብ', g11, soc_stream),
            ('HIS-11', 'History', 'ታሪክ', g11, soc_stream),
            ('GEO-11', 'Geography', 'ጂኦግራፊ', g11, soc_stream),
            ('ECN-11', 'Economics', 'ኢኮኖሚክስ', g11, soc_stream),
            ('ICT-11S', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g11, soc_stream),
            ('CIT-11', 'Citizenship', 'የዜግነት ትምህርት', g11, soc_stream),

            # Grade 12 Natural Science (NAT)
            ('ENG-12N', 'English Language', 'እንግሊዝኛ', g12, nat_stream),
            ('MTH-12N', 'Mathematics', 'ሒሳብ', g12, nat_stream),
            ('PHY-12', 'Physics', 'ፊዚክስ', g12, nat_stream),
            ('CHM-12', 'Chemistry', 'ኬሚስትሪ', g12, nat_stream),
            ('BIO-12', 'Biology', 'ባዮሎጂ', g12, nat_stream),
            ('WEB-12', 'Web Design', 'ዌብ ዲዛይን', g12, nat_stream),
            ('ICT-12', 'Information Technology', 'ኢንፎርሜሽን ቴክኖሎጂ', g12, nat_stream),

            # Grade 12 Social Science (SOC)
            ('ENG-12S', 'English Language', 'እንግሊዝኛ', g12, soc_stream),
            ('MTH-12S', 'Mathematics', 'ሒሳብ', g12, soc_stream),
            ('HIS-12', 'History', 'ታሪክ', g12, soc_stream),
            ('GEO-12', 'Geography', 'ጂኦግራፊ', g12, soc_stream),
            ('ECN-12', 'Economics', 'ኢኮኖሚክስ', g12, soc_stream),
            ('CIT-12', 'Citizenship', 'የዜግነት ትምህርት', g12, soc_stream),
            ('AGR-12', 'Agriculture', 'ግብርና', g12, soc_stream),
        ]

        created_subjects = {}
        for code, name, amharic, sgrade, sstream in subjects_spec:
            sub, _ = Subject.objects.get_or_create(
                school=school,
                code=code,
                grade=sgrade,
                stream=sstream,
                defaults={'name': name, 'amharic_name': amharic}
            )
            sub.name = name
            sub.amharic_name = amharic
            sub.save()
            created_subjects[(sgrade.level, sstream.code, code)] = sub

        self.stdout.write(self.style.SUCCESS(f"Created {len(created_subjects)} curriculum subjects across grades & streams."))

        # Assign Teachers to Teach Subjects in their Sections
        all_tp_list = list(teacher_profiles.values())
        for sec_name, sec_obj in sections.items():
            subs = Subject.objects.filter(school=school, grade=sec_obj.grade, stream=sec_obj.stream)
            for idx, sub_obj in enumerate(subs):
                assigned_tp = all_tp_list[idx % len(all_tp_list)]
                TeacherAssignment.objects.get_or_create(
                    school=school,
                    academic_year=ay,
                    teacher=assigned_tp,
                    subject=sub_obj,
                    section=sec_obj
                )

        # 8. Unique Students Across All 8 Sections
        # Format: (id_suffix, first, middle, last, amharic, gender, dob_year, dob_month, dob_day, section_key)
        students_spec = [
            # Grade 9A
            ("9A01", "Biniam", "Tesfaye", "Alemayehu", "ቢኒያም ተስፋዬ አለማየሁ", "M", 2011, 4, 12, "9A"),
            ("9A02", "Hanan", "Mohammed", "Jemal", "ሀናን መሀመድ ጀማል", "F", 2011, 8, 23, "9A"),
            ("9A03", "Natnael", "Kassahun", "Demisse", "ናትናኤል ካሳሁን ደሚሴ", "M", 2011, 2, 19, "9A"),
            ("9A04", "Marta", "Getachew", "Wondimu", "ማርታ ጌታቸው ወንዲሙ", "F", 2011, 11, 5, "9A"),

            # Grade 9B
            ("9B01", "Robel", "Fikru", "Birhanu", "ሮቤል ፍቅሩ ብርሃኑ", "M", 2011, 5, 30, "9B"),
            ("9B02", "Sara", "Endale", "Mekonnen", "ሳራ እንዳለ መኮንን", "F", 2011, 9, 14, "9B"),
            ("9B03", "Yonatan", "Berhe", "Zewde", "ዮናታን በርሄ ዘውዴ", "M", 2011, 3, 21, "9B"),
            ("9B04", "Feven", "Girma", "Hailu", "ፌቨን ግርማ ሀይሉ", "F", 2011, 7, 8, "9B"),

            # Grade 10A
            ("10A01", "Kaleb", "Tsegaye", "Haile", "ካሌብ ፀጋዬ ሀይሌ", "M", 2010, 1, 15, "10A"),
            ("10A02", "Liya", "Solomon", "Negussie", "ሊያ ሰለሞን ንጉሴ", "F", 2010, 6, 27, "10A"),
            ("10A03", "Henok", "Melaku", "Belay", "ሄኖክ መላኩ በላይ", "M", 2010, 10, 9, "10A"),
            ("10A04", "Tsion", "Abraham", "Mulugeta", "ፂዮን አብርሃም ሙሉጌታ", "F", 2010, 3, 4, "10A"),

            # Grade 10B
            ("10B01", "Mikiyas", "Yared", "Shibashi", "ሚኪያስ ያሬድ ሽባሺ", "M", 2010, 4, 18, "10B"),
            ("10B02", "Ruth", "Daniel", "Kidane", "ሩት ዳንኤል ኪዳኔ", "F", 2010, 8, 22, "10B"),
            ("10B03", "Surafel", "Tefera", "Gebremariam", "ሱራፌል ተፈራ ገብረማርያም", "M", 2010, 12, 1, "10B"),
            ("10B04", "Kalkidan", "Bekele", "Ayalew", "ቃልኪዳን በቀለ አያሌው", "F", 2010, 7, 16, "10B"),

            # Grade 11 NS
            ("11NS01", "Eyob", "Sisay", "Teshome", "እዮብ ሲሳይ ተሾመ", "M", 2009, 2, 11, "11 NS"),
            ("11NS02", "Mahlet", "Desta", "Gashaw", "ማህሌት ደስታ ጋሻው", "F", 2009, 9, 3, "11 NS"),
            ("11NS03", "Blen", "Yohannes", "Asrat", "ብሌን ዮሐንስ አስራት", "F", 2009, 5, 29, "11 NS"),
            ("11NS04", "Kirubel", "Aschalew", "Kebede", "ኪሩቤል አስቻለው ከበደ", "M", 2009, 11, 24, "11 NS"),

            # Grade 11 SS
            ("11SS01", "Yafet", "Tamirat", "Zeleke", "ያፌት ታምራት ዘለቀ", "M", 2009, 3, 17, "11 SS"),
            ("11SS02", "Sosina", "Moges", "Worku", "ሶስና ሞገስ ወርቁ", "F", 2009, 10, 12, "11 SS"),
            ("11SS03", "Biruk", "Lemma", "Hailu", "ብሩክ ለማ ሀይሉ", "M", 2009, 1, 28, "11 SS"),
            ("11SS04", "Hirut", "Abebaw", "Dessie", "ሂሩት አበበው ደሴ", "F", 2009, 6, 7, "11 SS"),

            # Grade 12 NS (Includes Abel Derege Ababu)
            ("1001", "Abel", "Derege", "Ababu", "አቤል ደረጀ አባቡ", "M", 2008, 5, 14, "12 NS"),
            ("12NS02", "Helina", "Million", "Fisseha", "ሄሊና ሚሊዮን ፍስሀ", "F", 2008, 8, 19, "12 NS"),
            ("12NS03", "Dawit", "Amanuel", "Gebremedhin", "ዳዊት አማኑኤል ገብረመድህን", "M", 2008, 12, 5, "12 NS"),
            ("12NS04", "Rediet", "Sintayehu", "Kassa", "ረድኤት ስንታየሁ ካሳ", "F", 2008, 4, 30, "12 NS"),
            ("12NS05", "Fasil", "Habtamu", "Mengistu", "ፋሲል ሀብታሙ መንግስቱ", "M", 2008, 10, 22, "12 NS"),

            # Grade 12 SS
            ("12SS01", "Tamrat", "Aragaw", "Mengesha", "ታምራት አራጋው መንገሻ", "M", 2008, 1, 9, "12 SS"),
            ("12SS02", "Saron", "Elias", "Bayissa", "ሳሮን ኤልያስ ባይሳ", "F", 2008, 7, 25, "12 SS"),
            ("12SS03", "Leul", "Wondwossen", "Ayele", "ልዑል ወንድወሰን አየለ", "M", 2008, 11, 14, "12 SS"),
            ("12SS04", "Eden", "Tilahun", "Woldeyes", "ኤደን ጥላሁን ወልደየስ", "F", 2008, 3, 18, "12 SS"),
        ]

        total_enrolled = 0
        for sid_sfx, fn, mn, ln, amh_name, gender, y, m, d, sec_key in students_spec:
            full_stu_id = f"STU-SEA-{sid_sfx}"
            uname = f"stu_{sid_sfx.lower()}"
            sec_obj = sections[sec_key]

            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={
                    'email': f"{uname}@student.seattleacademyethiopia.com",
                    'first_name': fn,
                    'last_name': f"{mn} {ln}",
                    'role': UserRole.STUDENT,
                    'school': school,
                    'is_active': True
                }
            )
            u.first_name = fn
            u.last_name = f"{mn} {ln}"
            u.school = school
            u.role = UserRole.STUDENT
            u.is_active = True
            u.set_password("student123")
            u.save()

            sp, _ = StudentProfile.objects.get_or_create(
                school=school,
                student_id=full_stu_id,
                defaults={
                    'user': u,
                    'first_name': fn,
                    'middle_name': mn,
                    'last_name': ln,
                    'amharic_name': amh_name,
                    'gender': gender,
                    'date_of_birth': datetime.date(y, m, d),
                    'status': StudentStatus.ACTIVE,
                    'photo': 'student_photos/abel_student_portrait.jpg' if sid_sfx == '1001' else None
                }
            )
            sp.user = u
            sp.first_name = fn
            sp.middle_name = mn
            sp.last_name = ln
            sp.amharic_name = amh_name
            sp.gender = gender
            sp.date_of_birth = datetime.date(y, m, d)
            sp.status = StudentStatus.ACTIVE
            if sid_sfx == '1001':
                sp.photo = 'student_photos/abel_student_portrait.jpg'
            sp.save()

            # Active Enrollment in Section
            enr, _ = StudentEnrollment.objects.get_or_create(
                school=school,
                academic_year=ay,
                student=sp,
                defaults={
                    'grade': sec_obj.grade,
                    'stream': sec_obj.stream,
                    'section': sec_obj,
                    'status': EnrollmentStatus.ACTIVE,
                    'admission_type': AdmissionType.NEW,
                    'enrollment_number': f"ENR-2018-{sid_sfx}"
                }
            )
            enr.grade = sec_obj.grade
            enr.stream = sec_obj.stream
            enr.section = sec_obj
            enr.status = EnrollmentStatus.ACTIVE
            enr.save()

            # Subject Enrollments in all curriculum subjects for this grade & stream
            subs = Subject.objects.filter(school=school, grade=sec_obj.grade, stream=sec_obj.stream)
            for sub in subs:
                SubjectEnrollment.objects.get_or_create(
                    school=school,
                    enrollment=enr,
                    subject=sub,
                    defaults={'is_active': True}
                )

            total_enrolled += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {total_enrolled} unique students with enrollments & subjects."))
        self.stdout.write(self.style.SUCCESS(">>> SEATTLE ACADEMY FULL ACADEMIC SETUP COMPLETE!"))
