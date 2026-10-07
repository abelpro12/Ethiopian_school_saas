import os
import sys
import random
from decimal import Decimal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.tenants.models import School
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Section, Grade
from apps.enrollment.models import StudentEnrollment, SubjectEnrollment
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus
from apps.teachers.models import TeacherAssignment

def seed_draft_marks():
    random.seed(42)  # Deterministic, authentic, reproducible results

    school = School.objects.get(code='SEA')
    ay = AcademicYear.objects.filter(school=school, is_active=True).first()
    if not ay:
        ay = AcademicYear.objects.filter(school=school).first()

    sem = AcademicPeriod.objects.filter(school=school, academic_year=ay, is_current=True).first()
    if not sem:
        sem = AcademicPeriod.objects.filter(school=school, academic_year=ay).first()

    admin_user = User.objects.filter(school=school, role='SCHOOL_ADMIN').first() or User.objects.filter(is_superuser=True).first()

    print(f"=== Seeding Real-World Draft Marks for {school.name} ({school.code}) ===")
    print(f"Academic Year: {ay.name}")
    print(f"Period: {sem.name}")
    print(f"Admin User fallback: {admin_user.username if admin_user else 'None'}\n")

    # 1. Ensure Assessment Components exist for all subjects in Seattle Academy
    subjects = Subject.objects.filter(school=school).order_by('grade__level', 'name')
    print(f"1. Checking assessment components for {subjects.count()} subjects...")

    standard_components = [
        {'name': 'Continuous Assessment', 'weight': Decimal('30.00'), 'max_marks': Decimal('30.00')},
        {'name': 'Midterm Exam', 'weight': Decimal('30.00'), 'max_marks': Decimal('30.00')},
        {'name': 'Final Exam', 'weight': Decimal('40.00'), 'max_marks': Decimal('40.00')},
    ]

    components_created = 0
    components_total = 0
    for subj in subjects:
        for c_def in standard_components:
            comp, created = AssessmentComponent.objects.get_or_create(
                school=school,
                academic_year=ay,
                period=sem,
                subject=subj,
                name=c_def['name'],
                defaults={
                    'weight': c_def['weight'],
                    'max_marks': c_def['max_marks'],
                }
            )
            if created:
                components_created += 1
            components_total += 1

    print(f"   Assessment components ready: {components_total} total ({components_created} newly created).\n")

    # 2. Map teacher assignments for quick lookup of who enters marks
    # (subject_id, section_id) -> Teacher User
    teacher_map = {}
    for ta in TeacherAssignment.objects.filter(school=school, academic_year=ay).select_related('teacher__user', 'subject', 'section'):
        teacher_map[(ta.subject_id, ta.section_id)] = ta.teacher.user

    # 3. Fetch all active student enrollments
    enrollments = StudentEnrollment.objects.filter(
        school=school, academic_year=ay, status='ACTIVE'
    ).select_related('student', 'section', 'section__grade', 'section__class_teacher')

    print(f"2. Generating marks for {enrollments.count()} active students across 8 sections...")

    # Assign each student an authentic base aptitude archetype to reflect a real-world classroom
    # Archetypes:
    # 'top': 88 - 97% overall
    # 'strong': 78 - 87% overall
    # 'average': 68 - 77% overall
    # 'developing': 54 - 67% overall
    archetype_pools = ['top', 'strong', 'strong', 'average', 'average', 'average', 'developing']

    # Pre-assign baseline ability to each student
    student_abilities = {}
    for idx, enr in enumerate(enrollments):
        st_id = enr.student.id
        # Special top students like Abel Derege Ababu or Marta Getachew
        if 'Abel' in enr.student.first_name or 'Marta' in enr.student.first_name:
            tier = 'top'
            base_score = random.uniform(0.91, 0.96)
        elif 'Blen' in enr.student.first_name or 'Kaleb' in enr.student.first_name:
            tier = 'top'
            base_score = random.uniform(0.88, 0.93)
        else:
            tier = archetype_pools[idx % len(archetype_pools)]
            if tier == 'top':
                base_score = random.uniform(0.88, 0.94)
            elif tier == 'strong':
                base_score = random.uniform(0.78, 0.86)
            elif tier == 'average':
                base_score = random.uniform(0.68, 0.77)
            else:
                base_score = random.uniform(0.55, 0.66)
        
        # Student-level subject preferences / affinities (e.g., sciences vs humanities)
        stem_affinity = random.uniform(-0.04, 0.05)
        humanities_affinity = random.uniform(-0.04, 0.05)
        student_abilities[st_id] = {
            'tier': tier,
            'base_score': base_score,
            'stem_affinity': stem_affinity,
            'humanities_affinity': humanities_affinity,
        }

    total_marks_saved = 0
    section_stats = {}

    for enr in enrollments:
        sec = enr.section
        if sec.name not in section_stats:
            section_stats[sec.name] = {'count': 0, 'total_sum': 0.0, 'marks_count': 0}

        st_profile = student_abilities[enr.student.id]
        
        # Get all enrolled subjects for this student
        sub_enrollments = SubjectEnrollment.objects.filter(
            school=school, enrollment=enr
        ).select_related('subject')

        for se in sub_enrollments:
            subj = se.subject
            
            # Determine teacher who entered the marks
            entered_by = teacher_map.get((subj.id, sec.id))
            if not entered_by and sec.class_teacher:
                entered_by = sec.class_teacher
            if not entered_by:
                entered_by = admin_user

            # Subject-specific aptitude adjustment
            subj_code = subj.code.upper()
            if any(k in subj_code for k in ['MTH', 'PHY', 'CHM', 'BIO', 'ICT', 'WEB']):
                subj_score_pct = st_profile['base_score'] + st_profile['stem_affinity']
            elif any(k in subj_code for k in ['ENG', 'AMH', 'HIS', 'GEO', 'CIT', 'ECN']):
                subj_score_pct = st_profile['base_score'] + st_profile['humanities_affinity']
            else:
                subj_score_pct = st_profile['base_score']

            # Add minor subject noise (+/- 2.5%)
            subj_score_pct += random.uniform(-0.025, 0.025)
            subj_score_pct = max(0.48, min(0.985, subj_score_pct))

            # Fetch assessment components for this subject
            components = AssessmentComponent.objects.filter(
                school=school, academic_year=ay, period=sem, subject=subj
            ).order_by('id')

            subj_total = 0.0

            for comp in components:
                max_m = float(comp.max_marks)

                # Realistic teacher scoring:
                # Add slight component variation (e.g., student might do slightly better on Continuous Assessment than Final Exam)
                if 'Continuous' in comp.name:
                    comp_pct = subj_score_pct + random.uniform(0.01, 0.05)
                elif 'Midterm' in comp.name:
                    comp_pct = subj_score_pct + random.uniform(-0.03, 0.03)
                else: # Final Exam
                    comp_pct = subj_score_pct + random.uniform(-0.04, 0.02)

                comp_pct = max(0.45, min(0.99, comp_pct))
                raw_mark = comp_pct * max_m

                # Round to realistic 0.5 step (half marks) or integer: e.g. 24.5, 27.0
                rounded_mark = round(raw_mark * 2) / 2.0
                
                # Clip within [0, max_m]
                rounded_mark = max(0.0, min(max_m, rounded_mark))
                subj_total += rounded_mark

                # Save mark with status strictly = MarkStatus.DRAFT ("don't submit for review just do save change")
                mark_obj, _ = StudentMark.objects.update_or_create(
                    school=school,
                    enrollment=enr,
                    assessment_component=comp,
                    defaults={
                        'mark_value': Decimal(f"{rounded_mark:.2f}"),
                        'status': MarkStatus.DRAFT,
                        'entered_by': entered_by,
                    }
                )
                total_marks_saved += 1
                section_stats[sec.name]['marks_count'] += 1

            section_stats[sec.name]['total_sum'] += subj_total
            section_stats[sec.name]['count'] += 1

    print(f"\n3. Generation Summary:")
    print(f"   Total StudentMarks saved: {total_marks_saved}")
    print(f"   All marks saved with status: {MarkStatus.DRAFT} (Draft Mode - not submitted for review)\n")

    print("--- Section Statistics (Subject Average Scores) ---")
    for sec_name, data in section_stats.items():
        avg = data['total_sum'] / max(1, data['count'])
        print(f"   Section {sec_name:8s}: {data['count']} subject enrollments, {data['marks_count']} marks, Avg Total: {avg:.2f}/100")

    # Verification checks
    draft_count = StudentMark.objects.filter(school=school, status=MarkStatus.DRAFT).count()
    submitted_count = StudentMark.objects.filter(school=school, status=MarkStatus.SUBMITTED).count()
    approved_count = StudentMark.objects.filter(school=school, status=MarkStatus.APPROVED).count()
    published_count = StudentMark.objects.filter(school=school, status=MarkStatus.PUBLISHED).count()

    print("\n--- Integrity Verification ---")
    print(f"   Draft Marks:     {draft_count}")
    print(f"   Submitted Marks: {submitted_count} (Must be 0)")
    print(f"   Approved Marks:  {approved_count}")
    print(f"   Published Marks: {published_count}")
    assert submitted_count == 0, "Error: Submitted marks detected when only Draft was requested!"
    print("   Verification PASSED: All marks are in DRAFT status as requested.\n")

if __name__ == '__main__':
    seed_draft_marks()
