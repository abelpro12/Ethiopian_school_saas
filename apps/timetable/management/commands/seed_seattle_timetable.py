import datetime
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import School
from apps.academics.models import (
    AcademicYear, Grade, Stream, Section, Subject, PeriodSlot, TimetableSlot, DayOfWeek
)
from apps.teachers.models import TeacherProfile

# Data structure matching Seattle Academy weekly timetable
SECTIONS_DEF = [
    # Grade 9 (General)
    {'level': 9, 'stream': 'GEN', 'name': '9A'},
    {'level': 9, 'stream': 'GEN', 'name': '9B'},
    {'level': 9, 'stream': 'GEN', 'name': '9C'},
    {'level': 9, 'stream': 'GEN', 'name': '9D'},
    {'level': 9, 'stream': 'GEN', 'name': '9E'},
    # Grade 10 (General)
    {'level': 10, 'stream': 'GEN', 'name': '10A'},
    {'level': 10, 'stream': 'GEN', 'name': '10B'},
    {'level': 10, 'stream': 'GEN', 'name': '10C'},
    {'level': 10, 'stream': 'GEN', 'name': '10D'},
    # Grade 11 (Natural / Social)
    {'level': 11, 'stream': 'NAT', 'name': '11A'},
    {'level': 11, 'stream': 'NAT', 'name': '11B'},
    {'level': 11, 'stream': 'SOC', 'name': '11C'},
    # Grade 12 (Natural / Social)
    {'level': 12, 'stream': 'NAT', 'name': '12A'},
    {'level': 12, 'stream': 'NAT', 'name': '12B'},
    {'level': 12, 'stream': 'SOC', 'name': '12C'},
    {'level': 12, 'stream': 'SOC', 'name': '12D'},
]

PERIODS_DEF = [
    ('Period 1', datetime.time(8, 30), datetime.time(9, 15)),
    ('Period 2', datetime.time(9, 15), datetime.time(10, 0)),
    ('Period 3', datetime.time(10, 15), datetime.time(11, 0)),
    ('Period 4', datetime.time(11, 0), datetime.time(11, 45)),
    ('Period 5', datetime.time(12, 45), datetime.time(13, 30)),
    ('Period 6', datetime.time(13, 30), datetime.time(14, 15)),
    ('Period 7', datetime.time(14, 15), datetime.time(15, 0)),
]

SUBJECT_NAMES = {
    'ENGL': 'English Language',
    'MATH': 'Mathematics',
    'PHYS': 'Physics',
    'CHEM': 'Chemistry',
    'BIOL': 'Biology',
    'GEOG': 'Geography',
    'HIST': 'History',
    'ECON': 'Economics',
    'CITZ': 'Citizenship Education',
    'AMHA': 'Amharic Language',
    'A.ORO': 'Afan Oromo',
    'HPE': 'Health & Physical Education',
    'ICT': 'Information Communication Tech',
    'CTEW': 'Career Tech Ed - Workshop',
    'CTEM': 'Career Tech Ed - Manufacturing',
    'AGRI': 'General Agriculture',
    'LIBRY': 'Library & Research Period',
}

# 16 sections in order: 9A, 9B, 9C, 9D, 9E, 10A, 10B, 10C, 10D, 11A, 11B, 11C, 12A, 12B, 12C, 12D
SCHEDULE_DATA = {
    DayOfWeek.MONDAY.value: [
        ['ENGL', 'A.ORO', 'MATH', 'PHYS', 'BIOL', 'GEOG', 'AMHA', 'MATH', 'CHEM', 'GEOG', 'ICT', 'PHYS', 'GEOG', 'HIST', 'CHEM', 'MATH'],
        ['MATH', 'ENGL', 'PHYS', 'BIOL', 'A.ORO', 'AMHA', 'ECON', 'CITZ', 'GEOG', 'HIST', 'BIOL', 'ICT', 'GEOG', 'CTEM', 'MATH', 'PHYS'],
        ['PHYS', 'MATH', 'ENGL', 'A.ORO', 'HPE', 'ECON', 'GEOG', 'AMHA', 'MATH', 'ICT', 'PHYS', 'BIOL', 'HIST', 'CTEM', 'AGRI', 'CHEM'],
        ['A.ORO', 'PHYS', 'BIOL', 'MATH', 'PHYS', 'CITZ', 'CHEM', 'GEOG', 'HIST', 'CTEM', 'CTEW', 'MATH', 'ENGL', 'ICT', 'PHYS', 'BIOL'],
        ['BIOL', 'ECON', 'CHEM', 'HPE', 'MATH', 'HIST', 'CITZ', 'CHEM', 'AMHA', 'CTEM', 'CTEW', 'ENGL', 'ICT', 'ENGL', 'BIOL', 'AGRI'],
        ['ECON', 'CHEM', 'A.ORO', 'ENGL', 'HIST', 'CHEM', 'MATH', 'HIST', 'ENGL', 'ENGL', 'MATH', 'CTEW', 'ECON', 'MATH', 'ENGL', 'ICT'],
        ['CHEM', 'BIOL', 'ECON', 'HIST', 'ENGL', 'MATH', 'HIST', 'ENGL', 'HPE', 'MATH', 'ENGL', 'CTEW', 'MATH', 'ECON', 'ICT', 'ENGL'],
    ],
    DayOfWeek.TUESDAY.value: [
        ['AMHA', 'ENGL', 'MATH', 'ICT', 'CITZ', 'MATH', 'BIOL', 'ICT', 'HIST', 'HIST', 'CHEM', 'BIOL', 'LIBRY', 'GEOG', 'CHEM', 'CTEW'],
        ['CHEM', 'AMHA', 'ENGL', 'CITZ', 'BIOL', 'BIOL', 'ECON', 'GEOG', 'ICT', 'CTEM', 'AGRI', 'CHEM', 'HIST', 'GEOG', 'BIOL', 'CTEW'],
        ['ENGL', 'MATH', 'AMHA', 'BIOL', 'ICT', 'ICT', 'MATH', 'HPE', 'GEOG', 'CTEM', 'LIBRY', 'CTEW', 'GEOG', 'HIST', 'AGRI', 'BIOL'],
        ['MATH', 'GEOG', 'CHEM', 'AMHA', 'GEOG', 'ENGL', 'CHEM', 'BIOL', 'PHYS', 'GEOG', 'MATH', 'CTEW', 'ECON', 'MATH', 'MATH', 'CHEM'],
        ['HIST', 'CHEM', 'ICT', 'GEOG', 'AMHA', 'HPE', 'ENGL', 'PHYS', 'BIOL', 'ENGL', 'BIOL', 'MATH', 'MATH', 'ECON', 'CTEW', 'MATH'],
        ['GEOG', 'ICT', 'HIST', 'CHEM', 'ECON', 'CHEM', 'PHYS', 'ENGL', 'MATH', 'ECON', 'ENGL', 'PHYS', 'ENGL', 'ICT', 'CTEW', 'ENGL'],
        ['ICT', 'HIST', 'GEOG', 'ECON', 'CHEM', 'PHYS', 'HPE', 'MATH', 'ENGL', 'MATH', 'PHYS', 'ENGL', 'ICT', 'ENGL', 'ENGL', 'AGRI'],
    ],
    DayOfWeek.WEDNESDAY.value: [
        ['CITZ', 'GEOG', 'BIOL', 'ICT', 'CHEM', 'ECON', 'AMHA', 'MATH', 'PHYS', 'MATH', 'CHEM', 'ENGL', 'GEOG', 'CTEM', 'LIBRY', 'CTEW'],
        ['GEOG', 'BIOL', 'CITZ', 'CHEM', 'A.ORO', 'AMHA', 'HPE', 'ECON', 'MATH', 'ENGL', 'MATH', 'CHEM', 'GEOG', 'CTEM', 'AGRI', 'CTEW'],
        ['HPE', 'CITZ', 'A.ORO', 'GEOG', 'ICT', 'PHYS', 'MATH', 'AMHA', 'ECON', 'HIST', 'ENGL', 'MATH', 'CTEM', 'LIBRY', 'AGRI', 'BIOL'],
        ['BIOL', 'A.ORO', 'GEOG', 'CITZ', 'GEOG', 'MATH', 'PHYS', 'CHEM', 'A.ORO', 'ECON', 'CTEW', 'ICT', 'ENGL', 'MATH', 'ICT', 'MATH'],
        ['HIST', 'ENGL', 'HPE', 'A.ORO', 'CITZ', 'GEOG', 'A.ORO', 'PHYS', 'CITZ', 'ECON', 'CTEW', 'AGRI', 'MATH', 'ENGL', 'MATH', 'ICT'],
        ['A.ORO', 'HIST', 'ENGL', 'MATH', 'ENGL', 'ENGL', 'GEOG', 'A.ORO', 'HIST', 'ICT', 'AGRI', 'BIOL', 'HIST', 'ECON', 'ENGL', 'PHYS'],
        ['ENGL', 'HPE', 'HIST', 'ENGL', 'MATH', 'A.ORO', 'ENGL', 'HIST', 'CHEM', 'GEOG', 'BIOL', 'LIBRY', 'ECON', 'HIST', 'PHYS', 'ENGL'],
    ],
    DayOfWeek.THURSDAY.value: [
        ['MATH', 'CHEM', 'GEOG', 'BIOL', 'PHYS', 'BIOL', 'MATH', 'ECON', 'CITZ', 'ICT', 'CHEM', 'CTEW', 'HIST', 'CTEM', 'CHEM', 'MATH'],
        ['CHEM', 'PHYS', 'AMHA', 'PHYS', 'ENGL', 'CITZ', 'BIOL', 'ICT', 'MATH', 'GEOG', 'ICT', 'CTEW', 'CTEM', 'HIST', 'MATH', 'PHYS'],
        ['CITZ', 'AMHA', 'HPE', 'ENGL', 'BIOL', 'MATH', 'CITZ', 'BIOL', 'ECON', 'HIST', 'CTEW', 'CHEM', 'CTEM', 'GEOG', 'BIOL', 'LIBRY'],
        ['PHYS', 'GEOG', 'CHEM', 'HPE', 'MATH', 'ICT', 'CHEM', 'ENGL', 'BIOL', 'CTEM', 'CTEW', 'MATH', 'MATH', 'ECON', 'PHYS', 'CHEM'],
        ['AMHA', 'HPE', 'PHYS', 'MATH', 'CHEM', 'CHEM', 'ICT', 'PHYS', 'ENGL', 'CTEM', 'ENGL', 'PHYS', 'ECON', 'MATH', 'CTEM', 'AGRI'],
        ['HPE', 'MATH', 'CITZ', 'CHEM', 'HIST', 'HIST', 'ENGL', 'CITZ', 'PHYS', 'MATH', 'PHYS', 'ENGL', 'ENGL', 'ICT', 'CTEW', 'ENGL'],
        ['GEOG', 'CITZ', 'MATH', 'HIST', 'HPE', 'ENGL', 'HIST', 'MATH', 'ICT', 'ENGL', 'MATH', 'AGRI', 'ICT', 'ENGL', 'ENGL', 'PHYS'],
    ],
    DayOfWeek.FRIDAY.value: [
        ['ECON', 'BIOL', 'MATH', 'HIST', 'ECON', 'A.ORO', 'PHYS', 'HIST', 'AMHA', 'ICT', 'PHYS', 'ENGL', 'CTEM', 'GEOG', 'CTEW', 'CHEM'],
        ['BIOL', 'PHYS', 'ECON', 'MATH', 'HIST', 'PHYS', 'HIST', 'A.ORO', 'GEOG', 'GEOG', 'ENGL', 'ICT', 'CTEM', 'HIST', 'CTEW', 'PHYS'],
        ['PHYS', 'HIST', 'BIOL', 'ECON', 'MATH', 'HIST', 'ICT', 'CHEM', 'A.ORO', 'ENGL', 'ICT', 'AGRI', 'HIST', 'CTEM', 'CHEM', 'CTEW'],
        ['HIST', 'ECON', 'PHYS', 'GEOG', 'AMHA', 'ENGL', 'A.ORO', 'BIOL', 'CHEM', 'MATH', 'BIOL', 'PHYS', 'ENGL', 'CTEM', 'MATH', 'CTEW'],
        ['ENGL', 'ICT', 'HIST', 'AMHA', 'GEOG', 'HPE', 'BIOL', 'A.ORO', 'ENGL', 'LIBRY', 'AGRI', 'BIOL', 'ECON', 'ENGL', 'PHYS', 'ENGL'],
        ['ICT', 'MATH', 'ENGL', 'PHYS', 'ENGL', 'BIOL', 'GEOG', 'ENGL', 'HPE', 'ENGL', 'MATH', 'MATH', 'MATH', 'ECON', 'ENGL', 'ICT'],
        ['MATH', 'ENGL', 'ICT', 'ENGL', 'PHYS', 'GEOG', 'ENGL', 'HPE', 'BIOL', 'ECON', 'MATH', 'CHEM', 'GEOG', 'MATH', 'ICT', 'ENGL'],
    ]
}


class Command(BaseCommand):
    help = "Seeds Seattle Academy's official weekly timetable matching the Seattle Academy Weekly Time Table, 2026/27 (2019 E.C)"

    def add_arguments(self, parser):
        parser.add_argument('--school-code', type=str, default=None, help='Target school code')

    @transaction.atomic
    def handle(self, *args, **options):
        school_code = options.get('school_code')
        if school_code:
            school = School.objects.filter(code=school_code).first()
        else:
            school = School.objects.filter(code='SEA').first() or School.objects.first()

        if not school:
            self.stdout.write(self.style.ERROR("No school found. Please create or seed it first."))
            return

        self.stdout.write(f"Configuring Seattle Academy ({school.name}) Weekly Timetable...")

        # 1. Ensure Academic Year 2026/27 (2019 E.C)
        ay, _ = AcademicYear.objects.get_or_create(
            school=school,
            name="2026/27",
            defaults={
                'ethiopian_year': 2019,
                'gregorian_start_date': datetime.date(2026, 9, 1),
                'gregorian_end_date': datetime.date(2027, 6, 30),
                'is_active': True,
            }
        )
        if not ay.is_active:
            AcademicYear.objects.filter(school=school).update(is_active=False)
            ay.is_active = True
            ay.ethiopian_year = 2019
            ay.save()

        # 2. Setup 7 Standard Periods
        periods = []
        for name, start_time, end_time in PERIODS_DEF:
            period, _ = PeriodSlot.objects.update_or_create(
                school=school,
                name=name,
                defaults={
                    'start_time': start_time,
                    'end_time': end_time,
                    'shift': 'FULL_DAY',
                }
            )
            periods.append(period)
        self.stdout.write(self.style.SUCCESS(f"Configured {len(periods)} daily periods."))

        # 3. Streams
        stream_gen, _ = Stream.objects.get_or_create(school=school, code='GEN', defaults={'name': 'General'})
        stream_nat, _ = Stream.objects.get_or_create(school=school, code='NAT', defaults={'name': 'Natural Science'})
        stream_soc, _ = Stream.objects.get_or_create(school=school, code='SOC', defaults={'name': 'Social Science'})
        stream_map = {'GEN': stream_gen, 'NAT': stream_nat, 'SOC': stream_soc}

        # 4. Grades
        grade_map = {}
        for lvl in [9, 10, 11, 12]:
            st = 'GEN' if lvl in [9, 10] else 'NAT'
            g, _ = Grade.objects.get_or_create(
                school=school,
                level=lvl,
                defaults={'name': f"Grade {lvl}", 'stream_type': st}
            )
            grade_map[lvl] = g

        # 5. Sections (16 sections: 9A-9E, 10A-10D, 11A-11C, 12A-12D)
        section_objs = []
        for sec_def in SECTIONS_DEF:
            lvl = sec_def['level']
            st_code = sec_def['stream']
            sec_name = sec_def['name']
            sec, _ = Section.objects.update_or_create(
                school=school,
                name=sec_name,
                grade=grade_map[lvl],
                stream=stream_map[st_code],
                defaults={'is_active': True, 'capacity': 45, 'shift': 'FULL_DAY'}
            )
            section_objs.append(sec)
        self.stdout.write(self.style.SUCCESS(f"Configured {len(section_objs)} academic sections (9A-12D)."))

        # 6. Ensure Subjects exist for each grade
        subject_cache = {}  # (lvl, code) -> Subject
        for lvl in [9, 10, 11, 12]:
            st = 'GEN' if lvl in [9, 10] else 'NAT'
            for code, name in SUBJECT_NAMES.items():
                subj, _ = Subject.objects.get_or_create(
                    school=school,
                    code=code,
                    grade=grade_map[lvl],
                    stream=stream_map[st],
                    defaults={
                        'name': name,
                        'is_core': code in ['MATH', 'ENGL', 'PHYS', 'CHEM', 'BIOL'],
                        'weekly_periods': 4,
                    }
                )
                subject_cache[(lvl, code)] = subj

        # 7. Ensure at least 20 teachers exist for Seattle Academy to prevent simultaneous period conflicts
        TEACHERS_LIST = [
            ("Dawit", "Tadesse"), ("Aster", "Bekele"), ("Solomon", "Hailemariam"),
            ("Bethlehem", "Girma"), ("Yohannes", "Worku"), ("Tigist", "Assefa"),
            ("Ermias", "Kebede"), ("Selamawit", "Alemu"), ("Kassahun", "Desta"),
            ("Meron", "Tekle"), ("Biniam", "Fikru"), ("Helen", "Zenebe"),
            ("Tamrat", "Berhanu"), ("Rahel", "Mekonnen"), ("Nebiyu", "Ayalew"),
            ("Hanna", "Gebre"), ("Marta", "Kassa"), ("Getachew", "Chernet"),
            ("Almaz", "Derese"), ("Fikadu", "Tesfaye"),
        ]
        from apps.accounts.models import User, UserRole
        teacher_pool = list(TeacherProfile.objects.filter(school=school))
        while len(teacher_pool) < 20:
            emp_num = len(teacher_pool) + 1
            emp_id = f"SEA-TCH-{emp_num:04d}"
            uname = f"sea_faculty_{emp_num:02d}"
            u, _ = User.objects.get_or_create(
                school=school,
                username=uname,
                defaults={
                    'first_name': TEACHERS_LIST[emp_num % len(TEACHERS_LIST)][0],
                    'last_name': TEACHERS_LIST[emp_num % len(TEACHERS_LIST)][1],
                    'role': UserRole.TEACHER,
                    'email': f"{uname}@seattleacademy.edu.et"
                }
            )
            tp, _ = TeacherProfile.objects.get_or_create(
                school=school,
                employee_id=emp_id,
                defaults={'user': u, 'employment_status': 'FULL_TIME'}
            )
            teacher_pool.append(tp)

        # 8. Populate all 560 TimetableSlots
        TimetableSlot.objects.filter(school=school).delete()
        slots_created = 0

        for day_val, period_rows in SCHEDULE_DATA.items():
            for p_idx, row_subjects in enumerate(period_rows):
                period = periods[p_idx]
                # In this period, track assigned teachers to ensure 100% zero conflict
                used_teachers_this_period = set()

                for s_idx, subj_code in enumerate(row_subjects):
                    sec = section_objs[s_idx]
                    lvl = sec.grade.level
                    subj = subject_cache.get((lvl, subj_code))
                    if not subj:
                        subj, _ = Subject.objects.get_or_create(
                            school=school,
                            code=subj_code,
                            grade=grade_map[lvl],
                            stream=sec.stream,
                            defaults={'name': SUBJECT_NAMES.get(subj_code, subj_code)}
                        )
                        subject_cache[(lvl, subj_code)] = subj

                    # Assign teacher unique to this period slot
                    assigned_teacher = None
                    if s_idx < len(teacher_pool):
                        candidate = teacher_pool[s_idx]
                        if candidate not in used_teachers_this_period:
                            assigned_teacher = candidate
                            used_teachers_this_period.add(candidate)

                    # Room assignment (unique per section)
                    room = f"Rm-{sec.name}"

                    TimetableSlot.objects.create(
                        school=school,
                        academic_year=ay,
                        section=sec,
                        subject=subj,
                        teacher=assigned_teacher,
                        day_of_week=day_val,
                        period_slot=period,
                        room=room,
                        is_locked=True
                    )
                    slots_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {slots_created} weekly timetable slots matching Seattle Academy 2026/27 (2019 E.C)!"
        ))
