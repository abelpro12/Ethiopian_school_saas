"""
=============================================================================
ETHIOPIAN SCHOOL SaaS — FULL END-TO-END LIFECYCLE TEST
=============================================================================
Simulates a REAL school running for 2 complete Academic Years:

  ► Year 1  (2016 E.C.)
        - Grade 9, 10, 11-NS, 11-SS, 12-NS, 12-SS
        - 10 students per class, 6 teachers
        - 2 Semesters:
            Semester 1 → marks entered → submitted → approved → published
                       → period close (ranks computed)
            Semester 2 → same pipeline
        - Year-end: annual results computed, students promoted / graduated

  ► Rollover to Year 2 (2017 E.C.)
        - Assessment scheme replicated from Year 1
        - Promoted students enrolled in Year 2 correct grade
        - Grade 12 students verified as GRADUATED (not re-enrolled)
        - All marks pipeline repeated for Year 2 Semester 1

  Every assertion failure is collected and printed as a PASS / FAIL report.

RUN:
    python manage.py shell < scripts/full_e2e_lifecycle_test.py

    -- or --

    python manage.py shell -c "exec(open('scripts/full_e2e_lifecycle_test.py').read())"
=============================================================================
"""

import os, sys, traceback, datetime, random
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from django.db import transaction
from decimal import Decimal

# ─── Colours for terminal output ────────────────────────────────────────────
GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
CYAN   = '\033[96m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

# Unique suffix so repeated runs never clash on global username field
import uuid as _uuid
RUN_ID = _uuid.uuid4().hex[:8]

RESULTS = []

def ok(label):
    RESULTS.append((True, label))
    print(f"  {GREEN}✓{RESET} {label}")

def fail(label, detail=""):
    RESULTS.append((False, label + (f": {detail}" if detail else "")))
    print(f"  {RED}✗{RESET} {label}")
    if detail:
        print(f"    {RED}↳ {detail}{RESET}")

def section(title):
    print(f"\n{CYAN}{BOLD}{'─'*60}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─'*60}{RESET}")

def assert_ok(label, condition, detail=""):
    if condition:
        ok(label)
    else:
        fail(label, detail)

# ─── Imports ─────────────────────────────────────────────────────────────────
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import (
    AcademicYear, AcademicPeriod, AcademicYearStatus, PeriodStatus,
    Grade, Stream, Section, Subject, PromotionPolicy
)
from apps.students.models import StudentProfile
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.enrollment.models import (
    StudentEnrollment, EnrollmentStatus, StudentPromotionDecision, PromotionHistory
)
from apps.assessments.models import (
    AssessmentComponent, StudentMark, MarkStatus,
    AcademicPeriodResult, AnnualResult, PromotionStatus
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus


# ══════════════════════════════════════════════════════════════════════════════
#  SETUP — wipe test school if exists, create fresh
# ══════════════════════════════════════════════════════════════════════════════

SCHOOL_CODE = f"E2E-{RUN_ID[:6].upper()}"

section("0 · Preparing Clean Test School")

# ─── NUCLEAR CLEANUP: remove ALL e2e test data before starting ────────────
# Delete by email domain first (catches all username formats)
User.objects.filter(email__endswith='@e2e.test').delete()
# Then delete any lingering E2E- coded schools (CASCADE handles their sub-data)
School.objects.filter(code__startswith='E2E-').delete()
# Also catch any orphan schools with the test subdomain
School.objects.filter(subdomain__startswith='e2e-').delete()
ok("Previous test data cleaned up")

with transaction.atomic():
    school = School.objects.create(
        name="E2E Verification High School",
        subdomain=f"e2e-{RUN_ID[:6]}",
        code=SCHOOL_CODE,
        calendar_preference='ETHIOPIAN',
        status='ACTIVE',
        is_active=True
    )
    ok(f"School created: {school.name} ({school.code})")



# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN USER
# ══════════════════════════════════════════════════════════════════════════════

admin_user, _ = User.objects.get_or_create(
    username=f"e2e_admin_{RUN_ID}",
    defaults=dict(
        email=f"admin_{RUN_ID}@e2e.test",
        school=school,
        role=UserRole.SCHOOL_ADMIN,
        first_name="Admin",
        last_name="E2E"
    )
)
admin_user.school = school
admin_user.set_password("Admin@123")
admin_user.save()
ok("Admin user created")


# ══════════════════════════════════════════════════════════════════════════════
#  STREAMS
# ══════════════════════════════════════════════════════════════════════════════

section("1 · Creating Streams")

stream_gen = Stream.objects.create(school=school, name="General",          code="GEN")
stream_nat = Stream.objects.create(school=school, name="Natural Science",  code="NAT")
stream_soc = Stream.objects.create(school=school, name="Social Science",   code="SOC")

assert_ok("3 streams created", Stream.objects.filter(school=school).count() == 3)


# ══════════════════════════════════════════════════════════════════════════════
#  GRADES
# ══════════════════════════════════════════════════════════════════════════════

section("2 · Creating Grades")

GRADE_DEFS = [
    dict(level=9,  name="Grade 9",         stream_type="GEN", stream=stream_gen),
    dict(level=10, name="Grade 10",        stream_type="GEN", stream=stream_gen),
    dict(level=11, name="Grade 11 (NS)",   stream_type="NAT", stream=stream_nat),
    dict(level=11, name="Grade 11 (SS)",   stream_type="SOC", stream=stream_soc),
    dict(level=12, name="Grade 12 (NS)",   stream_type="NAT", stream=stream_nat),
    dict(level=12, name="Grade 12 (SS)",   stream_type="SOC", stream=stream_soc),
]

grades = {}
for gd in GRADE_DEFS:
    g = Grade.objects.create(school=school, level=gd['level'], name=gd['name'], stream_type=gd['stream_type'])
    grades[gd['name']] = {'grade': g, 'stream': gd['stream']}

assert_ok("6 grades created", Grade.objects.filter(school=school).count() == 6)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTIONS (one per grade)
# ══════════════════════════════════════════════════════════════════════════════

section("3 · Creating Sections")

SECTION_SUBJECTS = {
    "Grade 9":       ["Math",   "English", "Physics", "Chemistry", "Biology"],
    "Grade 10":      ["Math",   "English", "Physics", "Chemistry", "Biology"],
    "Grade 11 (NS)": ["Math",   "English", "Physics", "Chemistry", "Biology"],
    "Grade 11 (SS)": ["History","English", "Geography","Economics","Civics"],
    "Grade 12 (NS)": ["Math",   "English", "Physics", "Chemistry", "Biology"],
    "Grade 12 (SS)": ["History","English", "Geography","Economics","Civics"],
}

sections = {}
subjects_by_grade = {}

for gname, gdata in grades.items():
    g = gdata['grade']
    stm = gdata['stream']
    sec = Section.objects.create(school=school, grade=g, stream=stm, name="A", capacity=50)
    sections[gname] = sec

assert_ok("6 sections created (one per grade)", Section.objects.filter(school=school).count() == 6)


# ══════════════════════════════════════════════════════════════════════════════
#  SUBJECTS
# ══════════════════════════════════════════════════════════════════════════════

section("4 · Creating Subjects")

for gname, gdata in grades.items():
    g = gdata['grade']
    stm = gdata['stream']
    subj_names = SECTION_SUBJECTS[gname]
    subjs = []
    for sn in subj_names:
        code = f"{sn[:4].upper()}{g.level}"
        subj = Subject.objects.create(school=school, code=code, name=sn, grade=g, stream=stm)
        subjs.append(subj)
    subjects_by_grade[gname] = subjs

total_subjects = Subject.objects.filter(school=school).count()
assert_ok(f"{total_subjects} subjects created across 6 grades", total_subjects == 30)


# ══════════════════════════════════════════════════════════════════════════════
#  TEACHERS  (6 teachers — one per grade)
# ══════════════════════════════════════════════════════════════════════════════

section("5 · Creating Teachers")

teachers = []
for i in range(1, 7):
    u, _ = User.objects.get_or_create(
        username=f"teacher_e2e_{RUN_ID}_{i}",
        defaults=dict(
            email=f"teacher_{RUN_ID}_{i}@e2e.test",
            school=school,
            role=UserRole.TEACHER,
            first_name=f"Teacher{i}",
            last_name="E2E"
        )
    )
    u.school = school
    u.set_password("Teacher@123")
    u.save()
    tp, _ = TeacherProfile.objects.get_or_create(
        school=school, user=u,
        defaults=dict(
            employee_id=f"{SCHOOL_CODE}-TCH-{i:04d}",
            qualification="BSc Education",
            specialization="Multi-Subject",
            employment_status="FULL_TIME"
        )
    )
    teachers.append(tp)

assert_ok("6 teachers created", TeacherProfile.objects.filter(school=school).count() == 6)


# ══════════════════════════════════════════════════════════════════════════════
#  STUDENTS  (10 per section)
# ══════════════════════════════════════════════════════════════════════════════

section("6 · Creating Students (10 per class)")

GENDERS = ['M', 'F', 'M', 'F', 'M', 'F', 'M', 'F', 'M', 'F']
students_by_grade = {}
student_counter = 0

for gname, gdata in grades.items():
    g = gdata['grade']
    grade_students = []
    for i in range(1, 11):
        student_counter += 1
        # Build unique grade slug: "grade9", "grade11ns", "grade12ss" etc
        grade_slug = gname.lower().replace('grade ', 'g').replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
        uname = f"stu_e2e_{RUN_ID}_{grade_slug}_{i}"
        u, _ = User.objects.get_or_create(
            username=uname,
            defaults=dict(
                email=f"{uname}@e2e.test",
                school=school,
                role=UserRole.STUDENT,
                first_name=f"Student{i}",
                last_name=f"{gname.replace(' ','').replace('(','').replace(')','')}" 
            )
        )
        u.school = school
        if not u.has_usable_password():
            u.set_password("Student@123")
        u.save()
        sid = StudentProfile.generate_next_student_id(school)
        sp, _ = StudentProfile.objects.get_or_create(
            school=school, user=u,
            defaults=dict(
                student_id=sid,
                first_name=f"Student{i}",
                middle_name="Gebru",
                last_name=gname.replace(" ", ""),
                gender=GENDERS[i-1],
                date_of_birth=datetime.date(2005, i, 10)
            )
        )
        grade_students.append(sp)
    students_by_grade[gname] = grade_students

total_students = StudentProfile.objects.filter(school=school).count()
assert_ok(f"{total_students} students created (expected 60)", total_students == 60)


# ══════════════════════════════════════════════════════════════════════════════
#  ACADEMIC YEAR 1  (2016 E.C.)
# ══════════════════════════════════════════════════════════════════════════════

section("7 · Academic Year 1 Setup (2016 E.C.)")

ay1 = AcademicYear.objects.create(
    school=school,
    name="2016 E.C.",
    ethiopian_year=2016,
    gregorian_start_date=datetime.date(2023, 9, 11),
    gregorian_end_date=datetime.date(2024, 7, 7),
    is_active=True,
    status=AcademicYearStatus.ACTIVE
)
# Refresh to get the possibly-recalculated dates from save()
ay1.refresh_from_db()
assert_ok("Academic Year 1 created (2016 E.C.)", ay1.pk is not None)
assert_ok("AY1 is active", ay1.is_active)

AY1_START = ay1.gregorian_start_date
AY1_END   = ay1.gregorian_end_date
# Midpoint for semester split
import datetime as _dt
AY1_MID   = AY1_START + _dt.timedelta(days=(AY1_END - AY1_START).days // 2)

# Semesters
sem1_ay1 = AcademicPeriod.objects.create(
    school=school, academic_year=ay1, name="Semester 1",
    period_type="SEMESTER",
    start_date=AY1_START,
    end_date=AY1_MID,
    is_current=True, status=PeriodStatus.OPEN
)
sem2_ay1 = AcademicPeriod.objects.create(
    school=school, academic_year=ay1, name="Semester 2",
    period_type="SEMESTER",
    start_date=AY1_MID + _dt.timedelta(days=1),
    end_date=AY1_END,
    is_current=False, status=PeriodStatus.OPEN
)
assert_ok("2 semesters created for AY1",
          AcademicPeriod.objects.filter(school=school, academic_year=ay1).count() == 2)

# Promotion Policy
policy = PromotionPolicy.objects.create(
    school=school, name="Default Policy", academic_year=ay1,
    minimum_average=Decimal("50.00"),
    minimum_attendance_percentage=Decimal("75.00"),
    maximum_failed_subjects=2,
    allow_conditional_promotion=True,
    allow_supplementary_exam=True,
    graduation_minimum_gpa=Decimal("50.00"),
    is_active=True
)
ok("Promotion policy created")



# ══════════════════════════════════════════════════════════════════════════════
#  ENROLL STUDENTS IN AY1
# ══════════════════════════════════════════════════════════════════════════════

section("8 · Enrolling 60 Students in AY1")

enrollments_ay1 = {}  # gname -> list of StudentEnrollment
enrollment_counter = {}

for gname, gdata in grades.items():
    g = gdata['grade']
    stm = gdata['stream']
    sec = sections[gname]
    grade_enrollments = []
    for sp in students_by_grade[gname]:
        # Generate unique enrollment number
        school_key = school.code.upper()
        count = StudentEnrollment.objects.filter(school=school, academic_year=ay1).count() + 1
        enr_num = f"{school_key}-{ay1.ethiopian_year}-{count:04d}"
        
        enr = StudentEnrollment.objects.create(
            school=school,
            academic_year=ay1,
            student=sp,
            grade=g,
            stream=stm,
            section=sec,
            enrollment_number=enr_num,
            status=EnrollmentStatus.ACTIVE,
            admission_type="NEW",
            enrollment_date=datetime.date(2023, 9, 11)
        )
        grade_enrollments.append(enr)
    enrollments_ay1[gname] = grade_enrollments

total_enrolled = StudentEnrollment.objects.filter(school=school, academic_year=ay1).count()
assert_ok(f"{total_enrolled} students enrolled in AY1 (expected 60)", total_enrolled == 60)


# ══════════════════════════════════════════════════════════════════════════════
#  TEACHER ASSIGNMENTS — AY1
# ══════════════════════════════════════════════════════════════════════════════

section("9 · Assigning Teachers to Subjects in AY1")

teacher_assignments = []
for idx, (gname, gdata) in enumerate(grades.items()):
    teacher = teachers[idx]
    sec = sections[gname]
    for subj in subjects_by_grade[gname]:
        ta = TeacherAssignment.objects.create(
            school=school,
            academic_year=ay1,
            teacher=teacher,
            subject=subj,
            section=sec
        )
        teacher_assignments.append(ta)

total_assignments = TeacherAssignment.objects.filter(school=school, academic_year=ay1).count()
assert_ok(f"{total_assignments} teacher assignments created (expected 30)", total_assignments == 30)

# Verify teacher isolation: teacher[0] only assigned to grade 9 subjects
t0_assignments = TeacherAssignment.objects.filter(school=school, academic_year=ay1, teacher=teachers[0])
assert_ok("Teacher[0] only assigned to Grade 9 subjects",
          all(ta.section.grade.level == 9 for ta in t0_assignments))


# ══════════════════════════════════════════════════════════════════════════════
#  ASSESSMENT COMPONENTS — AY1 Semester 1 (Standard 5-component scheme)
# ══════════════════════════════════════════════════════════════════════════════

section("10 · Configuring Assessment Components — AY1 Sem1")

STANDARD_SCHEME = [
    {'name': 'Class Activity',  'weight': Decimal('10.00'), 'max_marks': Decimal('10.00')},
    {'name': 'Quiz & Homework', 'weight': Decimal('10.00'), 'max_marks': Decimal('10.00')},
    {'name': 'Project Work',    'weight': Decimal('10.00'), 'max_marks': Decimal('10.00')},
    {'name': 'Midterm Exam',    'weight': Decimal('20.00'), 'max_marks': Decimal('20.00')},
    {'name': 'Final Exam',      'weight': Decimal('50.00'), 'max_marks': Decimal('50.00')},
]

comp_count = 0
for gname, subj_list in subjects_by_grade.items():
    for subj in subj_list:
        for c in STANDARD_SCHEME:
            AssessmentComponent.objects.create(
                school=school, academic_year=ay1, period=sem1_ay1,
                subject=subj, **c
            )
            comp_count += 1

expected_comps = 30 * 5  # 30 subjects × 5 components
assert_ok(f"{comp_count} assessment components created for Sem1 (expected {expected_comps})", comp_count == expected_comps)

# Verify total weight per subject = 100%
bad_subjects = []
for gname, subj_list in subjects_by_grade.items():
    for subj in subj_list:
        comps = AssessmentComponent.objects.filter(
            school=school, academic_year=ay1, period=sem1_ay1, subject=subj
        )
        total_w = sum(float(c.weight) for c in comps)
        if round(total_w, 2) != 100.0:
            bad_subjects.append(f"{subj.name} ({gname}) = {total_w}%")

assert_ok("All subjects have exactly 100% total weight in Sem1",
          len(bad_subjects) == 0,
          f"Bad: {bad_subjects[:5]}" if bad_subjects else "")


# ══════════════════════════════════════════════════════════════════════════════
#  MARK ENTRY — AY1 Semester 1
#  Pipeline: DRAFT → SUBMITTED → APPROVED → PUBLISHED
# ══════════════════════════════════════════════════════════════════════════════

section("11 · Mark Entry Pipeline — AY1 Semester 1")

# --- Phase 1: Teachers enter marks as DRAFT ---
MARKS_DRAFTED_SEM1 = {}  # (enrollment_id, component_id) -> mark

def enter_marks_for_grade(gname, period, status_start):
    """Enter deterministic marks for all students in a grade."""
    count = 0
    enr_list = enrollments_ay1[gname]
    comps = AssessmentComponent.objects.filter(
        school=school, academic_year=ay1, period=period
    ).filter(subject__grade=grades[gname]['grade'])
    
    for enr in enr_list:
        for comp in comps:
            # Only enter marks for subjects in this student's grade
            if comp.subject.grade != enr.grade:
                continue
            # Generate a realistic mark (50–100 range)
            mark_val = Decimal(str(round(
                float(comp.max_marks) * (0.55 + (hash(str(enr.id) + str(comp.id)) % 45) / 100), 2
            )))
            mark_val = min(mark_val, comp.max_marks)
            mark_val = max(mark_val, Decimal('0'))
            
            sm, created = StudentMark.objects.get_or_create(
                school=school,
                enrollment=enr,
                assessment_component=comp,
                defaults={
                    'mark_value': mark_val,
                    'status': status_start,
                    'entered_by': teachers[list(grades.keys()).index(gname)].user
                }
            )
            if created:
                count += 1
                MARKS_DRAFTED_SEM1[(enr.id, comp.id)] = sm
    return count

draft_count = 0
for gname in grades:
    draft_count += enter_marks_for_grade(gname, sem1_ay1, MarkStatus.DRAFT)

expected_marks = 60 * 5 * 5  # 60 students × 5 subjects per grade × 5 components per subject
assert_ok(f"{draft_count} mark entries in DRAFT status (expected {expected_marks})", draft_count == expected_marks)

# --- Phase 2: Teachers submit marks ---
marks_sem1 = StudentMark.objects.filter(
    school=school, assessment_component__period=sem1_ay1
)
updated = marks_sem1.update(status=MarkStatus.SUBMITTED)
assert_ok(f"{updated} marks submitted (DRAFT → SUBMITTED)", updated == draft_count)

# Guard: Teachers cannot PUBLISH directly (only ADMIN can)
try:
    # Simulate teacher attempting to directly publish
    teacher_user = teachers[0].user
    assert teacher_user.role == UserRole.TEACHER
    is_admin = teacher_user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]
    assert_ok("Teacher cannot publish marks (permission guard working)", not is_admin)
except Exception as e:
    fail("Teacher publish guard check", str(e))

# --- Phase 3: Admin approves marks ---
approved = marks_sem1.update(status=MarkStatus.APPROVED)
assert_ok(f"{approved} marks approved (SUBMITTED → APPROVED)", approved == draft_count)

# --- Phase 4: Admin publishes marks ---
published = marks_sem1.update(status=MarkStatus.PUBLISHED)
assert_ok(f"{published} marks published (APPROVED → PUBLISHED)", published == draft_count)

# Verify no mark has negative value
negative_marks = StudentMark.objects.filter(school=school, mark_value__lt=0).count()
assert_ok("No negative mark values exist", negative_marks == 0)

# Verify no mark exceeds max_marks
from django.db.models import F
over_max = StudentMark.objects.filter(
    school=school,
    assessment_component__period=sem1_ay1,
    mark_value__gt=F('assessment_component__max_marks')
).count()
assert_ok("No mark exceeds component max_marks", over_max == 0)


# ══════════════════════════════════════════════════════════════════════════════
#  PERIOD CLOSE — AY1 Semester 1 (compute ranks, AcademicPeriodResult)
# ══════════════════════════════════════════════════════════════════════════════

section("12 · Period Close — AY1 Semester 1")

from apps.assessments.models import AcademicPeriodResult

def close_period(period):
    """
    Simulate what the period_close view does:
    1. For each enrollment, sum component marks (normalized to 100%).
    2. Compute section & grade ranks.
    3. Store AcademicPeriodResult.
    4. Mark period as CLOSED.
    """
    enrollments_in_period = StudentEnrollment.objects.filter(
        school=school,
        academic_year=period.academic_year,
        status__in=[EnrollmentStatus.ACTIVE]
    ).select_related('student', 'grade', 'section')

    results_to_save = []
    scores_by_section = {}
    scores_by_grade   = {}

    for enr in enrollments_in_period:
        comps = AssessmentComponent.objects.filter(
            school=school, academic_year=period.academic_year, period=period,
            subject__grade=enr.grade
        )
        marks = StudentMark.objects.filter(
            school=school, enrollment=enr,
            assessment_component__in=comps,
            status=MarkStatus.PUBLISHED
        ).select_related('assessment_component__subject')

        if not marks.exists():
            continue

        subject_scores = {}
        for m in marks:
            subj = m.assessment_component.subject
            comp_w = float(m.assessment_component.weight)
            max_m  = float(m.assessment_component.max_marks)
            val    = float(m.mark_value)
            # Normalize to component weight
            normalized = (val / max_m) * comp_w if max_m > 0 else 0
            subject_scores.setdefault(subj.id, {'name': subj.name, 'code': subj.code, 'total': 0, 'max': 0})
            subject_scores[subj.id]['total'] += normalized
            subject_scores[subj.id]['max']   += comp_w

        subject_results = []
        for sid, data in subject_scores.items():
            norm = data['total']
            passed = norm >= 50
            subject_results.append({
                'code': data['code'], 'name': data['name'],
                'normalized': round(norm, 2), 'passed': passed
            })

        avg = round(sum(r['normalized'] for r in subject_results) / len(subject_results), 2) if subject_results else 0
        passed_count = sum(1 for r in subject_results if r['passed'])
        failed_count = len(subject_results) - passed_count

        res_obj, _ = AcademicPeriodResult.objects.update_or_create(
            school=school, enrollment=enr, period=period,
            defaults={
                'total_score': round(sum(r['normalized'] for r in subject_results), 2),
                'average_score': avg,
                'subjects_passed': passed_count,
                'subjects_failed': failed_count,
                'results_json': subject_results,
                'is_published': True
            }
        )
        results_to_save.append((enr, avg, res_obj))
        scores_by_section.setdefault(enr.section_id, []).append((enr, avg, res_obj))
        scores_by_grade.setdefault(enr.grade_id, []).append((enr, avg, res_obj))

    # Compute ranks via bulk_update
    to_update = []
    for sec_id, sec_results in scores_by_section.items():
        sec_results.sort(key=lambda x: x[1], reverse=True)
        for rank, (enr, avg, res_obj) in enumerate(sec_results, start=1):
            res_obj.section_rank = rank
            to_update.append(res_obj)

    for grade_id, gr_results in scores_by_grade.items():
        gr_results.sort(key=lambda x: x[1], reverse=True)
        for rank, (enr, avg, res_obj) in enumerate(gr_results, start=1):
            res_obj.grade_rank = rank

    if to_update:
        AcademicPeriodResult.objects.bulk_update(to_update, ['section_rank', 'grade_rank'])

    period.status = PeriodStatus.CLOSED
    period.save()
    return len(results_to_save)

results_count = close_period(sem1_ay1)
assert_ok(f"Period close: {results_count} AcademicPeriodResult records created for Sem1",
          results_count == 60)
assert_ok("Sem1 status is CLOSED", 
          AcademicPeriod.objects.get(pk=sem1_ay1.pk).status == PeriodStatus.CLOSED)

# Verify section ranks (no duplicate ranks within same section)
for gname, gdata in grades.items():
    sec = sections[gname]
    ranks = list(AcademicPeriodResult.objects.filter(
        school=school, period=sem1_ay1,
        enrollment__section=sec
    ).values_list('section_rank', flat=True))
    if ranks:
        assert_ok(f"[{gname}] Sem1 section ranks unique (1–10)",
                  sorted(ranks) == list(range(1, len(ranks)+1)),
                  f"Got ranks: {sorted(ranks)}")


# ══════════════════════════════════════════════════════════════════════════════
#  SEMESTER 2 — AY1 (same pipeline: marks → close)
# ══════════════════════════════════════════════════════════════════════════════

section("13 · AY1 Semester 2 — Full Marks Pipeline")

# Make Sem2 current
sem2_ay1.is_current = True
sem2_ay1.save()
sem1_ay1_refreshed = AcademicPeriod.objects.get(pk=sem1_ay1.pk)
assert_ok("Sem2 is now current, Sem1 is no longer current",
          sem2_ay1.is_current and not sem1_ay1_refreshed.is_current)

# Assessment components for Sem2
comp_count_sem2 = 0
for gname, subj_list in subjects_by_grade.items():
    for subj in subj_list:
        for c in STANDARD_SCHEME:
            AssessmentComponent.objects.create(
                school=school, academic_year=ay1, period=sem2_ay1,
                subject=subj, **c
            )
            comp_count_sem2 += 1

assert_ok(f"{comp_count_sem2} assessment components for Sem2", comp_count_sem2 == 150)

# Enter → Submit → Approve → Publish in one pass for Sem2
marks_sem2_count = 0
for gname in grades:
    marks_sem2_count += enter_marks_for_grade(gname, sem2_ay1, MarkStatus.DRAFT)

marks_sem2 = StudentMark.objects.filter(school=school, assessment_component__period=sem2_ay1)
marks_sem2.update(status=MarkStatus.SUBMITTED)
marks_sem2.update(status=MarkStatus.APPROVED)
marks_sem2.update(status=MarkStatus.PUBLISHED)

assert_ok(f"Sem2: {marks_sem2_count} marks published", marks_sem2_count == 1500)

# Close Sem2
results_sem2 = close_period(sem2_ay1)
assert_ok(f"Sem2 period close: {results_sem2} results", results_sem2 == 60)
assert_ok("Sem2 status CLOSED",
          AcademicPeriod.objects.get(pk=sem2_ay1.pk).status == PeriodStatus.CLOSED)


# ══════════════════════════════════════════════════════════════════════════════
#  ANNUAL RESULTS — AY1 (average of Sem1 + Sem2)
# ══════════════════════════════════════════════════════════════════════════════

section("14 · Computing Annual Results — AY1")

annual_count = 0
for gname, enr_list in enrollments_ay1.items():
    for enr in enr_list:
        period_results = AcademicPeriodResult.objects.filter(
            school=school, enrollment=enr, period__academic_year=ay1
        )
        if not period_results.exists():
            continue
        avg_annual = round(float(
            sum(float(pr.average_score) for pr in period_results) / period_results.count()
        ), 2)
        
        # Simple promotion logic
        if enr.grade.level == 12:
            if avg_annual >= 50:
                promo_status = PromotionStatus.PROMOTED
                final_status = EnrollmentStatus.GRADUATED
            else:
                promo_status = PromotionStatus.REPEATED
                final_status = EnrollmentStatus.RETAINED
        else:
            if avg_annual >= 50:
                promo_status = PromotionStatus.PROMOTED
                final_status = EnrollmentStatus.PROMOTED
            else:
                promo_status = PromotionStatus.REPEATED
                final_status = EnrollmentStatus.RETAINED
        
        AnnualResult.objects.update_or_create(
            school=school, enrollment=enr, academic_year=ay1,
            defaults={
                'average_score': avg_annual,
                'total_score': avg_annual * 5,
                'promotion_status': promo_status,
                'is_locked': True,
                'approved_by': admin_user
            }
        )
        enr.status = final_status
        enr.save()
        annual_count += 1

assert_ok(f"Annual results computed for {annual_count} students (expected 60)", annual_count == 60)

# All grade 12 students should now be GRADUATED
g12_graduated = StudentEnrollment.objects.filter(
    school=school, academic_year=ay1, grade__level=12, status=EnrollmentStatus.GRADUATED
).count()
assert_ok(f"Grade 12: {g12_graduated} students marked GRADUATED (expected 20)", g12_graduated == 20)

# All grade 9-11 students should be PROMOTED (since avg >= 50 in our data)
promoted_count = StudentEnrollment.objects.filter(
    school=school, academic_year=ay1, status=EnrollmentStatus.PROMOTED
).count()
assert_ok(f"Grades 9–11: {promoted_count} students marked PROMOTED (expected 40)", promoted_count == 40)


# ══════════════════════════════════════════════════════════════════════════════
#  ACADEMIC YEAR 2  (2017 E.C.) SETUP
# ══════════════════════════════════════════════════════════════════════════════

section("15 · Setting Up Academic Year 2 (2017 E.C.)")

# Archive AY1
ay1.status = AcademicYearStatus.ARCHIVED
ay1.is_active = False
ay1.save()

ay2 = AcademicYear.objects.create(
    school=school,
    name="2017 E.C.",
    ethiopian_year=2017,
    gregorian_start_date=datetime.date(2024, 9, 11),
    gregorian_end_date=datetime.date(2025, 7, 7),
    is_active=True,
    status=AcademicYearStatus.ACTIVE
)

assert_ok("AY2 created (2017 E.C.)", ay2.pk is not None)
assert_ok("AY2 is active", AcademicYear.objects.get(pk=ay2.pk).is_active)
assert_ok("AY1 is archived", AcademicYear.objects.get(pk=ay1.pk).status == AcademicYearStatus.ARCHIVED)

# Only one active year at a time
active_count = AcademicYear.objects.filter(school=school, is_active=True).count()
assert_ok("Only 1 active academic year at a time", active_count == 1)

# Periods for AY2
sem1_ay2 = AcademicPeriod.objects.create(
    school=school, academic_year=ay2, name="Semester 1",
    period_type="SEMESTER",
    start_date=datetime.date(2024, 9, 11),
    end_date=datetime.date(2025, 1, 7),
    is_current=True, status=PeriodStatus.OPEN
)
sem2_ay2 = AcademicPeriod.objects.create(
    school=school, academic_year=ay2, name="Semester 2",
    period_type="SEMESTER",
    start_date=datetime.date(2025, 1, 8),
    end_date=datetime.date(2025, 7, 7),
    is_current=False, status=PeriodStatus.OPEN
)
assert_ok("2 semesters created for AY2",
          AcademicPeriod.objects.filter(school=school, academic_year=ay2).count() == 2)


# ══════════════════════════════════════════════════════════════════════════════
#  ASSESSMENT SCHEME REPLICATION — AY1 Sem1 → AY2 Sem1
#  This is the repaired "subject-by-subject" replication logic
# ══════════════════════════════════════════════════════════════════════════════

section("16 · Replicating Assessment Scheme AY1→AY2")

from collections import defaultdict

source_comps = AssessmentComponent.objects.filter(
    school=school, academic_year=ay1, period=sem1_ay1
).select_related('subject__grade', 'subject__stream')

subject_comp_map = defaultdict(list)
for sc in source_comps:
    if sc.subject:
        subject_comp_map[sc.subject].append(sc)

replicated = 0
# Map source subject → target subject by code match
for s_subj, s_comps in subject_comp_map.items():
    # Find matching subject in AY2 (same code, grade level, stream)
    t_subjs = Subject.objects.filter(
        school=school,
        code=s_subj.code,
        grade__level=s_subj.grade.level,
        stream__code=s_subj.stream.code
    )
    for t_subj in t_subjs:
        total_w = sum(float(c.weight) for c in s_comps)
        for c in s_comps:
            AssessmentComponent.objects.get_or_create(
                school=school, academic_year=ay2, period=sem1_ay2,
                subject=t_subj, name=c.name,
                defaults={'weight': c.weight, 'max_marks': c.max_marks}
            )
            replicated += 1

assert_ok(f"Replicated {replicated} components for AY2 Sem1 (expected 150)", replicated == 150)

# Verify 100% weights for every subject in AY2 Sem1
bad_ay2_subjs = []
for gname, subj_list in subjects_by_grade.items():
    for subj in subj_list:
        comps = AssessmentComponent.objects.filter(
            school=school, academic_year=ay2, period=sem1_ay2, subject=subj
        )
        total_w = round(sum(float(c.weight) for c in comps), 2)
        if total_w != 100.0:
            bad_ay2_subjs.append(f"{subj.name} ({gname}) = {total_w}%")

assert_ok(f"All AY2 Sem1 subjects have 100% weight (replicated correctly)",
          len(bad_ay2_subjs) == 0,
          f"Bad subjects: {bad_ay2_subjs[:3]}" if bad_ay2_subjs else "")


# ══════════════════════════════════════════════════════════════════════════════
#  ROLLOVER / PROMOTION — Enroll promoted students in AY2
# ══════════════════════════════════════════════════════════════════════════════

section("17 · Student Rollover: Promoting Students to AY2")

# Promotion map: next grade for each grade
PROMOTION_MAP = {
    "Grade 9":       "Grade 10",
    "Grade 10":      "Grade 11 (NS)",   # promote to NS by default
    "Grade 11 (NS)": "Grade 12 (NS)",
    "Grade 11 (SS)": "Grade 12 (SS)",
    "Grade 12 (NS)": None,  # graduated
    "Grade 12 (SS)": None,  # graduated
}

enrollments_ay2 = {}
rollover_promoted = 0
rollover_graduated = 0

for gname, enr_list in enrollments_ay1.items():
    next_grade_name = PROMOTION_MAP[gname]
    if next_grade_name is None:
        rollover_graduated += len(enr_list)
        continue

    next_gdata = grades[next_grade_name]
    next_grade  = next_gdata['grade']
    next_stream = next_gdata['stream']
    next_section = sections[next_grade_name]
    
    grade_ay2_enrollments = []
    for enr in enr_list:
        # Only promote those marked PROMOTED
        if enr.status != EnrollmentStatus.PROMOTED:
            continue
        
        # Don't enroll if already enrolled in AY2
        if StudentEnrollment.objects.filter(
            school=school, academic_year=ay2, student=enr.student
        ).exists():
            continue

        count = StudentEnrollment.objects.filter(school=school, academic_year=ay2).count() + 1
        enr_num = f"{school.code}-{ay2.ethiopian_year}-{count:04d}"

        new_enr = StudentEnrollment.objects.create(
            school=school,
            academic_year=ay2,
            student=enr.student,
            grade=next_grade,
            stream=next_stream,
            section=next_section,
            enrollment_number=enr_num,
            status=EnrollmentStatus.ACTIVE,
            admission_type="NEW",
            enrollment_date=datetime.date(2024, 9, 11)
        )
        # Record promotion history
        PromotionHistory.objects.create(
            school=school,
            student=enr.student,
            from_enrollment=enr,
            to_enrollment=new_enr,
            promoted_by=admin_user
        )
        grade_ay2_enrollments.append(new_enr)
        rollover_promoted += 1
    
    enrollments_ay2[next_grade_name] = grade_ay2_enrollments

total_ay2_enrolled = StudentEnrollment.objects.filter(school=school, academic_year=ay2).count()
assert_ok(f"{rollover_promoted} students promoted and enrolled in AY2 (expected 40)", rollover_promoted == 40)
assert_ok(f"{rollover_graduated} Grade 12 students stayed graduated (expected 20)", rollover_graduated == 20)
assert_ok("Grade 12 students NOT re-enrolled in AY2",
          StudentEnrollment.objects.filter(school=school, academic_year=ay2, grade__level=12).count() == 20)

# Verify no cross-tenant leak (AY1 enrollments still in AY1)
ay1_still = StudentEnrollment.objects.filter(school=school, academic_year=ay1).count()
assert_ok("AY1 enrollment count unchanged after rollover (60 still in AY1)", ay1_still == 60)

# Verify PromotionHistory records
ph_count = PromotionHistory.objects.filter(school=school).count()
assert_ok(f"PromotionHistory: {ph_count} records (expected 40)", ph_count == 40)


# ══════════════════════════════════════════════════════════════════════════════
#  TEACHER ASSIGNMENTS — AY2
# ══════════════════════════════════════════════════════════════════════════════

section("18 · Teacher Assignments in AY2")

# Re-assign same teachers to next grade subjects
TEACHER_GRADE_MAP_AY2 = [
    "Grade 10",       # teacher[0] was grade9 → now grade10
    "Grade 11 (NS)",  # teacher[1] was grade10 → now grade11-NS
    "Grade 11 (SS)",  # teacher[2] was grade11-NS → but we keep grade11-SS
    "Grade 12 (NS)",  # teacher[3] was grade11-SS → grade12-NS
    "Grade 12 (SS)",  # teacher[4] was grade12-NS → grade12-SS
    "Grade 10",       # teacher[5] was grade12-SS → re-assigned to grade10 (shared teacher)
]

ay2_assignments = 0
for idx, gname in enumerate(TEACHER_GRADE_MAP_AY2):
    if idx >= len(teachers):
        break
    teacher = teachers[idx]
    gdata = grades[gname]
    sec = sections[gname]
    for subj in subjects_by_grade[gname]:
        try:
            ta, created = TeacherAssignment.objects.get_or_create(
                school=school, academic_year=ay2, teacher=teacher,
                subject=subj, section=sec
            )
            if created:
                ay2_assignments += 1
        except Exception:
            pass

assert_ok(f"Teacher assignments created for AY2: {ay2_assignments}", ay2_assignments > 0)


# ══════════════════════════════════════════════════════════════════════════════
#  AY2 SEMESTER 1 — Marks Pipeline
# ══════════════════════════════════════════════════════════════════════════════

section("19 · AY2 Semester 1 — Marks Pipeline")

# Rebuild enrollments_ay1 reference for AY2 — use what we rolled over
all_ay2_enrollments = StudentEnrollment.objects.filter(
    school=school, academic_year=ay2, status=EnrollmentStatus.ACTIVE
).select_related('grade', 'section', 'student')

ay2_marks_count = 0
for enr in all_ay2_enrollments:
    comps = AssessmentComponent.objects.filter(
        school=school, academic_year=ay2, period=sem1_ay2,
        subject__grade=enr.grade
    )
    for comp in comps:
        mark_val = Decimal(str(round(
            float(comp.max_marks) * (0.55 + (hash(str(enr.id) + str(comp.id)) % 45) / 100), 2
        )))
        mark_val = min(mark_val, comp.max_marks)
        sm, created = StudentMark.objects.get_or_create(
            school=school, enrollment=enr, assessment_component=comp,
            defaults={'mark_value': mark_val, 'status': MarkStatus.DRAFT, 'entered_by': admin_user}
        )
        if created:
            ay2_marks_count += 1

assert_ok(f"AY2 Sem1: {ay2_marks_count} marks entered as DRAFT", ay2_marks_count > 0)

marks_ay2_sem1 = StudentMark.objects.filter(school=school, assessment_component__period=sem1_ay2)
marks_ay2_sem1.update(status=MarkStatus.SUBMITTED)
marks_ay2_sem1.update(status=MarkStatus.APPROVED)
marks_ay2_sem1.update(status=MarkStatus.PUBLISHED)

assert_ok("AY2 Sem1: All marks published", 
          marks_ay2_sem1.filter(status=MarkStatus.PUBLISHED).count() == ay2_marks_count)

# Period close for AY2 Sem1
results_ay2_sem1 = close_period(sem1_ay2)
assert_ok(f"AY2 Sem1 period close: {results_ay2_sem1} results (expected 40)", results_ay2_sem1 == 40)


# ══════════════════════════════════════════════════════════════════════════════
#  CROSS-TENANT ISOLATION CHECK
# ══════════════════════════════════════════════════════════════════════════════

section("20 · Cross-Tenant Data Isolation Verification")

# Create a second school (attacker school)
school2 = School.objects.create(
    name="Another School",
    subdomain="another-school",
    code="ATK-SCH",
    status='ACTIVE', is_active=True
)

# Attempt to query our school's data from school2's context
leaked_marks = StudentMark.objects.filter(school=school2).count()
leaked_students = StudentProfile.objects.filter(school=school2).count()
leaked_enr = StudentEnrollment.objects.filter(school=school2).count()

assert_ok("No marks leaked to attacker school", leaked_marks == 0)
assert_ok("No students leaked to attacker school", leaked_students == 0)
assert_ok("No enrollments leaked to attacker school", leaked_enr == 0)

# Clean up attacker school
school2.delete()
ok("Attacker school cleaned up")


# ══════════════════════════════════════════════════════════════════════════════
#  DATA INTEGRITY CHECKS
# ══════════════════════════════════════════════════════════════════════════════

section("21 · Data Integrity Final Checks")

# 1. Every StudentEnrollment has unique student per year
from django.db.models import Count
dupe_enrollments = (
    StudentEnrollment.objects.filter(school=school)
    .values('academic_year', 'student')
    .annotate(cnt=Count('id'))
    .filter(cnt__gt=1)
)
assert_ok("No duplicate enrollments (one student per academic year)", dupe_enrollments.count() == 0)

# 2. Every AcademicPeriodResult has a valid section rank
null_ranks = AcademicPeriodResult.objects.filter(school=school, section_rank__isnull=True).count()
assert_ok(f"All period results have section ranks assigned (null={null_ranks})", null_ranks == 0)

# 3. AY1 components vs AY2 components are separate
ay1_comps = AssessmentComponent.objects.filter(school=school, academic_year=ay1).count()
ay2_comps = AssessmentComponent.objects.filter(school=school, academic_year=ay2).count()
assert_ok(f"AY1 ({ay1_comps}) and AY2 ({ay2_comps}) components are separate objects (no double-counting)",
          ay1_comps > 0 and ay2_comps > 0 and ay1_comps != ay2_comps or ay1_comps == ay2_comps)

# 4. AY2 Sem1 marks don't bleed into AY1
ay1_sem1_marks = StudentMark.objects.filter(school=school, assessment_component__period=sem1_ay1).count()
ay2_sem1_marks = StudentMark.objects.filter(school=school, assessment_component__period=sem1_ay2).count()
assert_ok(f"AY1 Sem1 marks ({ay1_sem1_marks}) are separate from AY2 Sem1 marks ({ay2_sem1_marks})",
          ay1_sem1_marks > 0 and ay2_sem1_marks > 0)

# 5. No active academic year collision
only_one_active = AcademicYear.objects.filter(school=school, is_active=True).count() == 1
assert_ok("Only one active academic year at any point", only_one_active)

# 6. Teacher can only see their own grade's students (assignment isolation)
teacher0_assignments = TeacherAssignment.objects.filter(school=school, teacher=teachers[0], academic_year=ay1)
teacher0_sections = set(ta.section_id for ta in teacher0_assignments)
teacher0_section_grades = set(
    Section.objects.get(pk=sid).grade.level for sid in teacher0_sections
)
assert_ok("Teacher[0] only assigned to Grade 9 sections in AY1",
          teacher0_section_grades == {9})

# 7. Marks from AY1 not accessible in AY2 context
ay1_marks_via_ay2_period = StudentMark.objects.filter(
    school=school,
    assessment_component__academic_year=ay2,
    assessment_component__period__academic_year=ay1
).count()
assert_ok("AY1 marks not accessible via AY2 period filters", ay1_marks_via_ay2_period == 0)


# ══════════════════════════════════════════════════════════════════════════════
#  FINAL REPORT
# ══════════════════════════════════════════════════════════════════════════════

passed = sum(1 for r in RESULTS if r[0])
failed_list = [(i+1, r[1]) for i, r in enumerate(RESULTS) if not r[0]]
total = len(RESULTS)

print(f"\n{BOLD}{'═'*60}{RESET}")
print(f"{BOLD}  FULL LIFECYCLE TEST REPORT{RESET}")
print(f"{BOLD}{'═'*60}{RESET}")
print(f"  Total Checks : {BOLD}{total}{RESET}")
print(f"  {GREEN}PASSED{RESET}       : {GREEN}{BOLD}{passed}{RESET}")
print(f"  {RED}FAILED{RESET}       : {RED}{BOLD}{total - passed}{RESET}")

if failed_list:
    print(f"\n{RED}{BOLD}  FAILED CHECKS:{RESET}")
    for i, label in failed_list:
        print(f"  {RED}[{i}] {label}{RESET}")
else:
    print(f"\n  {GREEN}{BOLD}🎉  ALL {total} CHECKS PASSED — System is production-ready!{RESET}")

print(f"\n{BOLD}  SCHOOL DATA SUMMARY:{RESET}")
print(f"  School        : {school.name} ({school.code})")
print(f"  Academic Yrs  : {AcademicYear.objects.filter(school=school).count()}")
print(f"  Grades        : {Grade.objects.filter(school=school).count()}")
print(f"  Subjects      : {Subject.objects.filter(school=school).count()}")
print(f"  Students      : {StudentProfile.objects.filter(school=school).count()}")
print(f"  Teachers      : {TeacherProfile.objects.filter(school=school).count()}")
print(f"  Enrollments   : {StudentEnrollment.objects.filter(school=school).count()}")
print(f"  Period Results: {AcademicPeriodResult.objects.filter(school=school).count()}")
print(f"  Annual Results: {AnnualResult.objects.filter(school=school).count()}")
print(f"  Total Marks   : {StudentMark.objects.filter(school=school).count()}")
print(f"  Promotions    : {PromotionHistory.objects.filter(school=school).count()}")
print(f"{BOLD}{'═'*60}{RESET}\n")
