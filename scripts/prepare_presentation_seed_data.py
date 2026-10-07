import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.tenants.models import School
from apps.academics.models import AcademicYear, AcademicPeriod
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import (
    AssessmentComponent,
    StudentMark,
    MarkStatus,
    AcademicPeriodResult,
    AnnualResult,
    AcademicPeriodPublishLog,
    SupplementaryExam,
)
from apps.examinations.models import OnlineExam
from apps.teachers.models import TeacherAssignment

def prepare_2018_presentation_data():
    school = School.objects.get(code='SEA')
    print(f"=== Preparing Presentation Seed Data for {school.name} ({school.code}) ===")

    ay2018 = AcademicYear.objects.get(id=27)
    sem1_2018 = AcademicPeriod.objects.get(id=26, academic_year=ay2018)

    # 1. Update OnlineExam to 2018 Semester 1 so CBT demo remains fully functional
    exam_count = 0
    for ex in OnlineExam.objects.filter(school=school):
        ex.academic_year = ay2018
        ex.period = sem1_2018
        ex.save()
        exam_count += 1
    print(f"1. Preserved and updated {exam_count} OnlineExam(s) to 2018 E.C. (Semester 1).")

    # 2. Delete 2019 Academic Year and all associated 2019 records
    ay2019 = AcademicYear.objects.filter(id=26).first()
    if ay2019:
        print("2. Removing 2019 Academic Year and testing rollover records...")
        StudentEnrollment.objects.filter(academic_year=ay2019).delete()
        TeacherAssignment.objects.filter(academic_year=ay2019).delete()
        AssessmentComponent.objects.filter(academic_year=ay2019).delete()
        AcademicPeriod.objects.filter(academic_year=ay2019).delete()
        ay2019.delete()
        print("   2019 Academic Year completely removed.")
    else:
        print("2. No 2019 Academic Year found to remove.")

    # 3. Activate 2018 Academic Year and Semester 1
    print("3. Activating 2018 E.C. as active Academic Year...")
    AcademicYear.objects.filter(school=school).exclude(id=ay2018.id).update(is_active=False)
    ay2018.is_active = True
    ay2018.status = 'ACTIVE'
    ay2018.name = '2018 E.C.'
    ay2018.save()

    AcademicPeriod.objects.filter(academic_year=ay2018).update(is_current=False)
    sem1_2018.is_current = True
    sem1_2018.status = 'ACTIVE'
    sem1_2018.save()

    # 4. Restore all 33 student enrollments in 2018 to ACTIVE
    print("4. Restoring all 33 Seattle Academy student enrollments to ACTIVE status...")
    updated_enr = StudentEnrollment.objects.filter(academic_year=ay2018).update(status=EnrollmentStatus.ACTIVE)
    print(f"   {updated_enr} student enrollments restored to ACTIVE.")

    # 5. Clear computed promotion and period close results for 2018
    print("5. Resetting annual promotion and period close calculations...")
    AnnualResult.objects.filter(academic_year=ay2018).delete()
    AcademicPeriodResult.objects.filter(period=sem1_2018).delete()
    AcademicPeriodPublishLog.objects.filter(period=sem1_2018).delete()
    SupplementaryExam.objects.filter(academic_year=ay2018).delete()
    print("   Annual and period results cleared.")

    # 6. Set all marks in 2018 to DRAFT (Saved changes by teachers, not submitted for review)
    print("6. Setting all marks to DRAFT (Teacher 'Save Changes' status)...")
    marks_count = StudentMark.objects.filter(assessment_component__academic_year=ay2018).update(status=MarkStatus.DRAFT)
    print(f"   {marks_count} student marks set to DRAFT (Save Changes state).")

    # 7. Verification
    active_ay = AcademicYear.objects.filter(school=school, is_active=True).first()
    active_period = AcademicPeriod.objects.filter(school=school, is_current=True).first()
    active_students = StudentEnrollment.objects.filter(school=school, academic_year=ay2018, status='ACTIVE').count()
    draft_marks = StudentMark.objects.filter(school=school, status=MarkStatus.DRAFT).count()
    submitted_marks = StudentMark.objects.filter(school=school, status=MarkStatus.SUBMITTED).count()
    approved_marks = StudentMark.objects.filter(school=school, status=MarkStatus.APPROVED).count()
    published_marks = StudentMark.objects.filter(school=school, status=MarkStatus.PUBLISHED).count()
    annual_results = AnnualResult.objects.filter(academic_year=ay2018).count()
    period_results = AcademicPeriodResult.objects.filter(period=sem1_2018).count()
    all_ays = [ay.name for ay in AcademicYear.objects.filter(school=school)]

    print("\n=== VERIFICATION SUMMARY ===")
    print(f"Active Academic Year: {active_ay.name if active_ay else 'None'}")
    print(f"Active Period:        {active_period.name if active_period else 'None'}")
    print(f"Active Students:      {active_students}")
    print(f"Draft Marks:          {draft_marks}")
    print(f"Submitted Marks:      {submitted_marks} (Expected: 0)")
    print(f"Approved Marks:       {approved_marks} (Expected: 0)")
    print(f"Published Marks:      {published_marks} (Expected: 0)")
    print(f"Annual Results:       {annual_results} (Expected: 0)")
    print(f"Period Results:       {period_results} (Expected: 0)")
    print(f"Existing AYs:         {all_ays}")

    assert active_ay and active_ay.id == ay2018.id, "Active AY is not 2018!"
    assert submitted_marks == 0, "Submitted marks exist!"
    assert published_marks == 0, "Published marks exist!"
    assert active_students == 33, f"Expected 33 active students, found {active_students}!"
    assert draft_marks == 837, f"Expected 837 draft marks, found {draft_marks}!"
    print("\nSUCCESS: All presentation seed data prepared perfectly!")

if __name__ == '__main__':
    prepare_2018_presentation_data()
