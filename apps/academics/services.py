import datetime
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    AcademicYearStatus,
    AcademicPeriod,
    PeriodStatus,
    PeriodType,
    Grade,
    Section,
    Stream,
    Subject,
)
from apps.enrollment.models import (
    StudentEnrollment,
    EnrollmentStatus,
    StudentPromotionDecision,
    PromotionDecisionType,
    PromotionHistory,
    SubjectEnrollment,
)
from apps.assessments.models import (
    AssessmentComponent,
    StudentMark,
    MarkStatus,
    AcademicPeriodResult,
)
from apps.teachers.models import TeacherAssignment


class RolloverValidationError(Exception):
    pass


class AcademicConfigCloningService:
    """
    Automates the cloning and replication of academic configurations across academic years:
    - Automatically calculates and provisions the next Ethiopian/Gregorian Academic Year.
    - Clones Academic Periods (Semesters) with forward-shifted dates.
    - Clones 100% Assessment Schemes (Components and Weights) across all curriculum subjects.
    - Ensures section structures exist for upcoming grades.
    - Auto-enrolls promoted/retained students into their appropriate curriculum subjects.
    - Replicates recurring Teacher Subject Assignments.
    """

    @classmethod
    @transaction.atomic
    def auto_provision_next_academic_year(
        cls,
        school,
        source_year=None,
        clone_periods=True,
        clone_assessment_schemes=True,
        clone_teacher_assignments=True,
        activate_new_year=False,
    ):
        from apps.academics.ethiopian_date import ethiopian_to_gregorian

        if not source_year:
            source_year = AcademicYear.objects.filter(school=school, is_active=True).first()
        if not source_year:
            source_year = AcademicYear.objects.filter(school=school).order_by('-ethiopian_year').first()

        if not source_year:
            raise RolloverValidationError("No source academic year found to clone configuration from.")

        next_eth_year = (source_year.ethiopian_year or 2018) + 1

        # Calculate standard Ethiopian academic calendar dates (Meskerem 1 to Sene 30)
        calc_start = ethiopian_to_gregorian(next_eth_year, 1, 1)
        calc_end = ethiopian_to_gregorian(next_eth_year, 10, 30)
        start_y = calc_start.year
        end_y = calc_end.year
        next_name = f"{next_eth_year} E.C. ({start_y}/{end_y} G.C)"

        target_year, created = AcademicYear.objects.get_or_create(
            school=school,
            ethiopian_year=next_eth_year,
            defaults={
                'name': next_name,
                'gregorian_start_date': calc_start,
                'gregorian_end_date': calc_end,
                'is_active': activate_new_year,
                'status': AcademicYearStatus.ACTIVE if activate_new_year else AcademicYearStatus.PLANNING,
            }
        )

        summary = {
            'target_year': target_year,
            'year_created': created,
            'periods_created': 0,
            'components_created': 0,
            'teacher_assignments_created': 0,
        }

        # 1. Clone Periods (Semesters)
        target_sem1 = None
        if clone_periods:
            source_periods = AcademicPeriod.objects.filter(
                school=school, academic_year=source_year
            ).order_by('start_date')

            if source_periods.exists():
                for sp in source_periods:
                    # Calculate shifted dates (+1 year)
                    try:
                        shifted_start = sp.start_date.replace(year=sp.start_date.year + 1)
                    except ValueError:
                        shifted_start = sp.start_date + datetime.timedelta(days=365)
                    try:
                        shifted_end = sp.end_date.replace(year=sp.end_date.year + 1)
                    except ValueError:
                        shifted_end = sp.end_date + datetime.timedelta(days=365)

                    is_sem1 = ('1' in sp.name or 'I' in sp.name or sp.is_current)
                    new_period, p_created = AcademicPeriod.objects.get_or_create(
                        school=school,
                        academic_year=target_year,
                        name=sp.name,
                        defaults={
                            'period_type': sp.period_type,
                            'start_date': shifted_start,
                            'end_date': shifted_end,
                            'is_current': is_sem1,
                            'status': PeriodStatus.OPEN,
                        }
                    )
                    if p_created:
                        summary['periods_created'] += 1
                    if is_sem1 and not target_sem1:
                        target_sem1 = new_period
            else:
                # Fallback: create standard Ethiopian semesters
                sem1_end = ethiopian_to_gregorian(next_eth_year, 5, 30)
                sem2_start = ethiopian_to_gregorian(next_eth_year, 6, 1)
                s1, _ = AcademicPeriod.objects.get_or_create(
                    school=school,
                    academic_year=target_year,
                    name="Semester 1",
                    defaults={
                        'period_type': PeriodType.SEMESTER,
                        'start_date': calc_start,
                        'end_date': sem1_end,
                        'is_current': True,
                        'status': PeriodStatus.OPEN,
                    }
                )
                AcademicPeriod.objects.get_or_create(
                    school=school,
                    academic_year=target_year,
                    name="Semester 2",
                    defaults={
                        'period_type': PeriodType.SEMESTER,
                        'start_date': sem2_start,
                        'end_date': calc_end,
                        'is_current': False,
                        'status': PeriodStatus.OPEN,
                    }
                )
                target_sem1 = s1
                summary['periods_created'] += 2

        if not target_sem1:
            target_sem1 = AcademicPeriod.objects.filter(school=school, academic_year=target_year).first()

        # 2. Clone Assessment Schemes & Components across all curriculum subjects
        if clone_assessment_schemes and target_sem1:
            subjects = Subject.objects.filter(school=school)
            for subj in subjects:
                # Find components for this subject in source year
                source_comps = AssessmentComponent.objects.filter(
                    school=school, academic_year=source_year, subject=subj
                )

                comp_defs = []
                if source_comps.exists():
                    seen = set()
                    for sc in source_comps:
                        if sc.name not in seen:
                            seen.add(sc.name)
                            comp_defs.append({
                                'name': sc.name,
                                'weight': sc.weight,
                                'max_marks': sc.max_marks
                            })
                else:
                    # Standard 100% Ethiopian Scheme (30% CA, 30% Mid, 40% Final)
                    comp_defs = [
                        {'name': 'Continuous Assessment', 'weight': 30.0, 'max_marks': 30.0},
                        {'name': 'Midterm Exam', 'weight': 30.0, 'max_marks': 30.0},
                        {'name': 'Final Exam', 'weight': 40.0, 'max_marks': 40.0},
                    ]

                for cd in comp_defs:
                    _, comp_created = AssessmentComponent.objects.get_or_create(
                        school=school,
                        academic_year=target_year,
                        period=target_sem1,
                        subject=subj,
                        name=cd['name'],
                        defaults={
                            'weight': cd['weight'],
                            'max_marks': cd['max_marks'],
                        }
                    )
                    if comp_created:
                        summary['components_created'] += 1

        # 3. Clone Teacher Assignments
        if clone_teacher_assignments:
            source_assignments = TeacherAssignment.objects.filter(
                school=school, academic_year=source_year
            ).select_related('teacher', 'subject', 'section')

            for ta in source_assignments:
                _, ta_created = TeacherAssignment.objects.get_or_create(
                    school=school,
                    academic_year=target_year,
                    teacher=ta.teacher,
                    subject=ta.subject,
                    section=ta.section,
                )
                if ta_created:
                    summary['teacher_assignments_created'] += 1

        return target_year, created, summary

    @classmethod
    def auto_enroll_student_in_subjects(cls, school, enrollment, academic_year=None):
        """
        Automatically enrolls a student into all active curriculum subjects for their
        allocated grade and stream.
        """
        subjects = Subject.objects.filter(school=school, grade=enrollment.grade)
        if enrollment.stream:
            subjects = subjects.filter(
                Q(stream=enrollment.stream) | Q(stream__code='GEN') | Q(stream__isnull=True)
            )

        enrolled_count = 0
        for subj in subjects:
            _, created = SubjectEnrollment.objects.get_or_create(
                school=school,
                enrollment=enrollment,
                subject=subj,
            )
            if created:
                enrolled_count += 1
        return enrolled_count


class AcademicYearRolloverService:
    @staticmethod
    def auto_provision_next_academic_year(school, source_year=None, **kwargs):
        return AcademicConfigCloningService.auto_provision_next_academic_year(
            school=school, source_year=source_year, **kwargs
        )

    @staticmethod
    def auto_enroll_student_in_subjects(school, enrollment, academic_year=None):
        return AcademicConfigCloningService.auto_enroll_student_in_subjects(
            school=school, enrollment=enrollment, academic_year=academic_year
        )

    @staticmethod
    def run_preflight_checks(school, academic_year):
        draft_marks_count = StudentMark.objects.filter(
            school=school,
            enrollment__academic_year=academic_year,
            status=MarkStatus.DRAFT
        ).count()

        active_enrollments_count = StudentEnrollment.objects.filter(
            school=school,
            academic_year=academic_year,
            status=EnrollmentStatus.ACTIVE
        ).count()

        results_count = AcademicPeriodResult.objects.filter(
            school=school,
            enrollment__academic_year=academic_year
        ).values('enrollment').distinct().count()

        missing_results = active_enrollments_count - results_count

        return {
            'draft_marks_count': draft_marks_count,
            'active_enrollments_count': active_enrollments_count,
            'missing_results_count': max(0, missing_results),
            'is_ready': (draft_marks_count == 0 and missing_results == 0)
        }

    @staticmethod
    def preview_rollover(school, source_academic_year, target_academic_year):
        from apps.enrollment.services import PromotionEvaluationEngine
        preflight = AcademicYearRolloverService.run_preflight_checks(school, source_academic_year)
        active_enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=source_academic_year,
            status=EnrollmentStatus.ACTIVE
        )
        decisions_summary = {
            'total_students': active_enrollments.count(),
            'promoted': 0,
            'retained': 0,
            'graduated': 0,
            'special_review': 0,
        }
        for enrollment in active_enrollments:
            dec = PromotionEvaluationEngine.evaluate_student(enrollment)
            rec = dec.system_recommendation
            if rec in [PromotionDecisionType.PROMOTED, PromotionDecisionType.PROMOTED_WITH_CONDITIONS]:
                decisions_summary['promoted'] += 1
            elif rec == PromotionDecisionType.RETAINED:
                decisions_summary['retained'] += 1
            elif rec == PromotionDecisionType.GRADUATED:
                decisions_summary['graduated'] += 1
            else:
                decisions_summary['special_review'] += 1
        return {
            'preflight': preflight,
            'summary': decisions_summary
        }

    @staticmethod
    @transaction.atomic
    def execute_rollover(school, current_academic_year, target_academic_year=None, admin_user=None, default_allocation_strategy='BALANCED_CAPACITY', auto_enroll_subjects=True):
        from apps.enrollment.services import PromotionEvaluationEngine, StreamAllocationEngine, SectionAllocationEngine

        if not target_academic_year:
            target_academic_year, _, _ = AcademicConfigCloningService.auto_provision_next_academic_year(
                school=school, source_year=current_academic_year
            )

        preflight = AcademicYearRolloverService.run_preflight_checks(school, current_academic_year)
        if not preflight['is_ready'] and preflight['draft_marks_count'] > 0:
            raise RolloverValidationError(f"Cannot execute rollover: {preflight['draft_marks_count']} draft marks remain unapproved.")

        active_enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=current_academic_year,
            status=EnrollmentStatus.ACTIVE
        )

        decisions = []
        for enrollment in active_enrollments:
            decision = PromotionEvaluationEngine.evaluate_student(enrollment)
            if not decision.admin_decision:
                decision.admin_decision = decision.system_recommendation
                decision.approved_by = admin_user
                decision.approved_at = timezone.now()
                decision.save()
            decisions.append(decision)

        StreamAllocationEngine.allocate_grade10_streams(school, current_academic_year)
        SectionAllocationEngine.allocate_sections(school, target_academic_year, strategy=default_allocation_strategy)

        promoted_count = 0
        retained_count = 0
        graduated_count = 0
        subject_enrollments_count = 0

        for decision in StudentPromotionDecision.objects.filter(school=school, academic_year=current_academic_year):
            enrollment = decision.enrollment
            student = enrollment.student
            decision_type = decision.admin_decision or decision.system_recommendation

            if decision_type in [PromotionDecisionType.PROMOTED, PromotionDecisionType.PROMOTED_WITH_CONDITIONS]:
                enrollment.status = EnrollmentStatus.PROMOTED
                enrollment.save()

                target_grade = decision.allocated_grade or enrollment.grade
                target_stream = decision.allocated_stream or enrollment.stream
                target_section = decision.allocated_section or Section.objects.filter(school=school, grade=target_grade, is_active=True).first()

                if target_section:
                    new_enrollment = StudentEnrollment.objects.create(
                        school=school,
                        academic_year=target_academic_year,
                        student=student,
                        grade=target_grade,
                        stream=target_stream,
                        section=target_section,
                        status=EnrollmentStatus.ACTIVE,
                        admission_type=enrollment.admission_type
                    )
                    PromotionHistory.objects.create(
                        school=school,
                        student=student,
                        from_enrollment=enrollment,
                        to_enrollment=new_enrollment,
                        promoted_by=admin_user
                    )
                    promoted_count += 1

                    if auto_enroll_subjects:
                        sub_count = AcademicConfigCloningService.auto_enroll_student_in_subjects(
                            school=school, enrollment=new_enrollment, academic_year=target_academic_year
                        )
                        subject_enrollments_count += sub_count

            elif decision_type == PromotionDecisionType.RETAINED:
                enrollment.status = EnrollmentStatus.RETAINED
                enrollment.save()

                target_section = decision.allocated_section or Section.objects.filter(school=school, grade=enrollment.grade, is_active=True).first()
                if target_section:
                    new_enrollment = StudentEnrollment.objects.create(
                        school=school,
                        academic_year=target_academic_year,
                        student=student,
                        grade=enrollment.grade,
                        stream=enrollment.stream,
                        section=target_section,
                        status=EnrollmentStatus.ACTIVE,
                        admission_type=enrollment.admission_type
                    )
                    retained_count += 1

                    if auto_enroll_subjects:
                        sub_count = AcademicConfigCloningService.auto_enroll_student_in_subjects(
                            school=school, enrollment=new_enrollment, academic_year=target_academic_year
                        )
                        subject_enrollments_count += sub_count

            elif decision_type == PromotionDecisionType.GRADUATED:
                enrollment.status = EnrollmentStatus.GRADUATED
                enrollment.save()
                student.status = EnrollmentStatus.GRADUATED
                student.save()
                graduated_count += 1

        current_academic_year.is_active = False
        current_academic_year.status = AcademicYearStatus.ARCHIVED
        current_academic_year.save()

        target_academic_year.is_active = True
        target_academic_year.status = AcademicYearStatus.ACTIVE
        target_academic_year.save()

        return {
            'success': True,
            'promoted_count': promoted_count,
            'retained_count': retained_count,
            'graduated_count': graduated_count,
            'subject_enrollments_count': subject_enrollments_count,
            'active_academic_year': target_academic_year.name
        }
