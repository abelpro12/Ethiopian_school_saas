from apps.academics.models import Grade, Stream, Section, PromotionPolicy, StreamCriteria
from apps.enrollment.models import StudentEnrollment, StudentPromotionDecision, PromotionDecisionType, StudentStreamPreference, EnrollmentStatus, PromotionHistory
from apps.assessments.models import AcademicPeriodResult, SupplementaryExam, SupplementaryExamStatus
from apps.academics.services import AcademicYearRolloverService

class PromotionEvaluationEngine:
    @staticmethod
    def evaluate_student(enrollment, policy=None):
        school = enrollment.school
        academic_year = enrollment.academic_year
        if not policy:
            policy = PromotionPolicy.objects.filter(school=school, is_active=True).first()
            if not policy:
                policy, _ = PromotionPolicy.objects.get_or_create(
                    school=school,
                    name="Default Standard Policy",
                    defaults={
                        'minimum_average': 50.00,
                        'minimum_attendance_percentage': 75.00,
                        'maximum_failed_subjects': 2,
                        'allow_conditional_promotion': True,
                    }
                )

        # 1. Calculate Period Results Average
        period_results = AcademicPeriodResult.objects.filter(school=school, enrollment=enrollment)
        if period_results.exists():
            avg_score = sum(r.average_score for r in period_results) / len(period_results)
        else:
            avg_score = 0.0

        # Check for supplementary exam passed scores
        supp_exams = SupplementaryExam.objects.filter(school=school, enrollment=enrollment, status=SupplementaryExamStatus.PASSED)

        # 2. Failed Subjects Evaluation
        failed_subjects = []
        subject_scores = {}
        for r in period_results:
            r_json = r.results_json or {}
            for subj_code, score in r_json.items():
                if isinstance(score, (int, float, str)):
                    try:
                        val = float(score)
                        subject_scores.setdefault(subj_code, []).append(val)
                    except ValueError:
                        pass
        
        for subj_code, scores in subject_scores.items():
            subj_avg = sum(scores) / len(scores) if scores else 0
            if subj_avg < float(policy.minimum_average):
                failed_subjects.append({'subject': subj_code, 'average': subj_avg})

        failed_count = len(failed_subjects)
        attendance_pct = 100.00  # Default full attendance

        # 3. Recommendation Pipeline
        grade_level = enrollment.grade.level

        if grade_level == 12:
            if avg_score >= float(policy.graduation_minimum_gpa) and failed_count == 0:
                recommendation = PromotionDecisionType.GRADUATED
            else:
                recommendation = PromotionDecisionType.RETAINED
        elif avg_score >= float(policy.minimum_average) and failed_count == 0 and attendance_pct >= float(policy.minimum_attendance_percentage):
            recommendation = PromotionDecisionType.PROMOTED
        elif failed_count <= policy.maximum_failed_subjects and policy.allow_conditional_promotion:
            recommendation = PromotionDecisionType.PROMOTED_WITH_CONDITIONS
        elif failed_count > policy.maximum_failed_subjects:
            recommendation = PromotionDecisionType.RETAINED
        else:
            recommendation = PromotionDecisionType.SPECIAL_REVIEW

        allocated_grade = enrollment.grade
        allocated_stream = enrollment.stream

        if recommendation in [PromotionDecisionType.PROMOTED, PromotionDecisionType.PROMOTED_WITH_CONDITIONS]:
            next_level = grade_level + 1
            next_grade = Grade.objects.filter(school=school, level=next_level, stream_type=enrollment.grade.stream_type).first()
            if not next_grade:
                next_grade = Grade.objects.filter(school=school, level=next_level).first()
            if next_grade:
                allocated_grade = next_grade

        decision, created = StudentPromotionDecision.objects.update_or_create(
            school=school,
            enrollment=enrollment,
            defaults={
                'academic_year': academic_year,
                'policy_used': policy,
                'final_average': avg_score,
                'attendance_percentage': attendance_pct,
                'failed_subjects_count': failed_count,
                'failed_subjects_json': failed_subjects,
                'system_recommendation': recommendation,
                'allocated_grade': allocated_grade,
                'allocated_stream': allocated_stream,
            }
        )
        return decision

    @staticmethod
    def promote_student(school, current_enrollment, next_academic_year, next_section=None, promoted_by_user=None):
        """
        Promotes a single student from current_enrollment to next_academic_year and next_section.
        """
        from django.db import transaction
        with transaction.atomic():
            if current_enrollment.grade.level >= 12:
                current_enrollment.status = EnrollmentStatus.GRADUATED
                current_enrollment.save(update_fields=['status'])
                return None

            current_enrollment.status = EnrollmentStatus.PROMOTED
            current_enrollment.save(update_fields=['status'])

            next_grade = next_section.grade if next_section else (
                Grade.objects.filter(school=school, level=current_enrollment.grade.level + 1).first()
            )
            next_stream = next_section.stream if next_section else current_enrollment.stream

            new_enrollment, _ = StudentEnrollment.objects.update_or_create(
                school=school,
                student=current_enrollment.student,
                academic_year=next_academic_year,
                defaults={
                    'grade': next_grade,
                    'stream': next_stream,
                    'section': next_section,
                    'status': EnrollmentStatus.ACTIVE
                }
            )
            return new_enrollment


PromotionService = PromotionEvaluationEngine



class StreamAllocationEngine:
    @staticmethod
    def allocate_grade10_streams(school, academic_year):
        grade10_decisions = StudentPromotionDecision.objects.filter(
            school=school,
            academic_year=academic_year,
            enrollment__grade__level=10,
            system_recommendation__in=[PromotionDecisionType.PROMOTED, PromotionDecisionType.PROMOTED_WITH_CONDITIONS]
        )

        results = []
        for dec in grade10_decisions:
            student = dec.enrollment.student
            pref = StudentStreamPreference.objects.filter(school=school, student=student, academic_year=academic_year).first()
            
            pref_stream = pref.preference_1 if pref else Stream.objects.filter(school=school, code='NAT').first()
            
            criteria = StreamCriteria.objects.filter(school=school, stream=pref_stream, is_active=True).first()
            
            is_eligible = True
            if criteria and dec.final_average < criteria.minimum_overall_average:
                is_eligible = False

            if is_eligible and pref_stream:
                dec.allocated_stream = pref_stream
                g11 = Grade.objects.filter(school=school, level=11, stream_type=pref_stream.code).first()
                if g11:
                    dec.allocated_grade = g11
            else:
                alt_stream = pref.preference_2 if (pref and pref.preference_2) else Stream.objects.filter(school=school, code='SOC').first()
                dec.allocated_stream = alt_stream
                g11 = Grade.objects.filter(school=school, level=11, stream_type=alt_stream.code).first() if alt_stream else None
                if g11:
                    dec.allocated_grade = g11
            
            dec.save()
            results.append(dec)
        return results


import random

class SectionAllocationEngine:
    @staticmethod
    def allocate_sections(school, target_academic_year, strategy='BALANCED_CAPACITY'):
        decisions = StudentPromotionDecision.objects.filter(
            school=school,
            academic_year=target_academic_year,
            admin_decision__isnull=False
        ).exclude(admin_decision__in=[PromotionDecisionType.GRADUATED, PromotionDecisionType.WITHDRAWN, PromotionDecisionType.TRANSFERRED])

        if strategy == 'MANUAL':
            return decisions

        # Group decisions by allocated grade
        grades_map = {}
        for dec in decisions:
            if dec.allocated_grade:
                grades_map.setdefault(dec.allocated_grade, []).append(dec)

        for grade, grade_decisions in grades_map.items():
            available_sections = list(Section.objects.filter(
                school=school,
                grade=grade,
                is_active=True
            ).order_by('name'))

            if not available_sections:
                continue

            sec_count = len(available_sections)

            if strategy == 'ACADEMIC_BALANCED':
                # Serpentine / Zigzag sorting by final GPA to balance academic performance
                sorted_decisions = sorted(grade_decisions, key=lambda d: float(d.final_average), reverse=True)
                for index, dec in enumerate(sorted_decisions):
                    cycle = index // sec_count
                    pos = index % sec_count
                    # Reverse order on odd cycles (serpentine zigzag distribution)
                    target_index = (sec_count - 1 - pos) if (cycle % 2 == 1) else pos
                    dec.allocated_section = available_sections[target_index]
                    dec.save()

            elif strategy == 'RANDOM':
                shuffled_decisions = list(grade_decisions)
                random.shuffle(shuffled_decisions)
                for index, dec in enumerate(shuffled_decisions):
                    dec.allocated_section = available_sections[index % sec_count]
                    dec.save()

            else:  # BALANCED_CAPACITY
                for dec in grade_decisions:
                    section = min(
                        available_sections,
                        key=lambda sec: StudentEnrollment.objects.filter(school=school, academic_year=target_academic_year, section=sec).count()
                    )
                    dec.allocated_section = section
                    dec.save()

        return decisions

