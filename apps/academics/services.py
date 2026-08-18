from django.db import transaction
from django.utils import timezone
from apps.academics.models import AcademicYear, AcademicYearStatus, Grade, Section, Stream
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus, StudentPromotionDecision, PromotionDecisionType, PromotionHistory
from apps.assessments.models import StudentMark, MarkStatus, AcademicPeriodResult


class RolloverValidationError(Exception):
    pass

class AcademicYearRolloverService:
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
    def execute_rollover(school, current_academic_year, target_academic_year, admin_user, default_allocation_strategy='BALANCED_CAPACITY'):
        from apps.enrollment.services import PromotionEvaluationEngine, StreamAllocationEngine, SectionAllocationEngine
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
            'active_academic_year': target_academic_year.name
        }
