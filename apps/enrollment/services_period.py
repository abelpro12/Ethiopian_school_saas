"""
AcademicPeriod-Close Service
Computes final student results for a period, assigns ranks, and publishes.
"""
from decimal import Decimal
from django.utils import timezone
from apps.academics.models import AcademicPeriod
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import (
    StudentMark, MarkStatus, AcademicPeriodResult, AcademicPeriodPublishLog
)
from apps.grading.models import GradeScaleRule


class AcademicPeriodCloseService:

    @staticmethod
    def get_grade_letter(school, score):
        """Returns letter grade for a numeric score using school's GradeScaleRule."""
        rule = GradeScaleRule.objects.filter(
            school=school, min_score__lte=score, max_score__gte=score
        ).first()
        return rule.grade_letter if rule else ('A' if score >= 85 else ('B' if score >= 75 else ('C' if score >= 60 else ('D' if score >= 50 else 'F'))))

    @staticmethod
    def preview_period_close(period, school):
        """
        Returns a preview dict of what will happen when period is closed:
        - How many students have marks
        - How many are missing marks
        - Subject breakdown
        """
        enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=period.academic_year,
            status=EnrollmentStatus.ACTIVE
        ).select_related('student', 'section', 'grade')

        marks_qs = StudentMark.objects.filter(
            school=school,
            assessment_component__period=period,
        )

        students_with_marks = marks_qs.values_list('enrollment__student_id', flat=True).distinct()
        total_students = enrollments.count()
        students_with_marks_count = len(set(students_with_marks))
        missing_count = total_students - students_with_marks_count

        # Check how many marks are still in DRAFT state
        draft_marks = marks_qs.filter(status=MarkStatus.DRAFT).count()
        submitted_marks = marks_qs.filter(status=MarkStatus.SUBMITTED).count()
        approved_marks = marks_qs.filter(status__in=[MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]).count()

        return {
            'total_students': total_students,
            'students_with_marks': students_with_marks_count,
            'missing_marks': missing_count,
            'draft_marks': draft_marks,
            'submitted_marks': submitted_marks,
            'approved_marks': approved_marks,
            'period': period,
        }

    @classmethod
    def execute_period_close(cls, period, school, published_by):
        """
        Main execution:
        1. Aggregate all marks per student per subject
        2. Compute weighted total & average
        3. Rank within section
        4. Write AcademicPeriodResult records
        5. Set AcademicPeriod.is_current = False
        6. Log the publish event
        Returns (success, message, count)
        """
        enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=period.academic_year,
            status=EnrollmentStatus.ACTIVE
        ).select_related('student', 'section', 'grade')

        # Group all marks for this period
        all_marks = StudentMark.objects.filter(
            school=school,
            assessment_component__period=period,
        ).select_related('assessment_component__subject', 'enrollment')

        # Build per-enrollment mark aggregation
        enrollment_data = {}
        for m in all_marks:
            eid = m.enrollment_id
            if eid not in enrollment_data:
                enrollment_data[eid] = {'subjects': {}, 'enrollment': m.enrollment}
            sub_name = m.assessment_component.subject.name
            sub_code = m.assessment_component.subject.code
            if sub_code not in enrollment_data[eid]['subjects']:
                enrollment_data[eid]['subjects'][sub_code] = {
                    'name': sub_name, 'code': sub_code,
                    'total': Decimal('0'), 'max_possible': Decimal('0'), 'components': []
                }
            comp = m.assessment_component
            enrollment_data[eid]['subjects'][sub_code]['total'] += m.mark_value
            enrollment_data[eid]['subjects'][sub_code]['max_possible'] += comp.max_marks
            enrollment_data[eid]['subjects'][sub_code]['components'].append({
                'name': comp.name, 'mark': float(m.mark_value), 'max': float(comp.max_marks)
            })

        # Section-based ranking preparation
        section_results = {}  # section_id -> [(enrollment_id, avg_score)]

        results_to_create = []
        for enrollment in enrollments:
            eid = enrollment.id
            data = enrollment_data.get(eid, {})
            subjects = data.get('subjects', {})

            subject_results = []
            total_score = Decimal('0')
            passed = 0
            failed = 0

            for sub_code, sub_data in subjects.items():
                max_p = sub_data['max_possible'] or Decimal('100')
                raw = sub_data['total']
                # Normalize to 100-point scale
                normalized = (raw / max_p) * Decimal('100') if max_p > 0 else raw
                letter = cls.get_grade_letter(school, float(normalized))
                is_pass = float(normalized) >= 50
                if is_pass:
                    passed += 1
                else:
                    failed += 1
                total_score += normalized
                subject_results.append({
                    'code': sub_code,
                    'name': sub_data['name'],
                    'raw_score': float(raw),
                    'normalized': round(float(normalized), 2),
                    'letter': letter,
                    'passed': is_pass,
                    'components': sub_data['components']
                })

            subject_count = len(subjects) or 1
            avg_score = total_score / subject_count

            # Get conduct grade
            from apps.assessments.models import StudentConduct
            conduct = StudentConduct.objects.filter(
                school=school, enrollment=enrollment, period=period
            ).first()
            conduct_grade = conduct.grade if conduct else 'B'

            results_to_create.append({
                'enrollment': enrollment,
                'avg_score': avg_score,
                'total_score': total_score,
                'passed': passed,
                'failed': failed,
                'conduct_grade': conduct_grade,
                'subjects_json': subject_results,
                'section_id': enrollment.section_id,
            })

            sec_id = enrollment.section_id
            if sec_id not in section_results:
                section_results[sec_id] = []
            section_results[sec_id].append((enrollment.id, float(avg_score)))

        # Compute section ranks
        section_ranks = {}
        for sec_id, eid_scores in section_results.items():
            sorted_scores = sorted(eid_scores, key=lambda x: x[1], reverse=True)
            for rank, (eid, _) in enumerate(sorted_scores, start=1):
                section_ranks[eid] = rank

        # Write AcademicPeriodResult records
        count = 0
        for r in results_to_create:
            enrollment = r['enrollment']
            section_rank = section_ranks.get(enrollment.id, None)
            AcademicPeriodResult.objects.update_or_create(
                school=school,
                enrollment=enrollment,
                period=period,
                defaults={
                    'total_score': r['total_score'],
                    'average_score': r['avg_score'],
                    'subjects_passed': r['passed'],
                    'subjects_failed': r['failed'],
                    'section_rank': section_rank,
                    'conduct_grade': r['conduct_grade'],
                    'is_published': True,
                    'published_at': timezone.now(),
                    'results_json': r['subjects_json'],
                }
            )
            count += 1

        # Close the period
        period.is_current = False
        period.save()

        # Write audit log
        AcademicPeriodPublishLog.objects.create(
            school=school,
            period=period,
            published_by=published_by,
            students_count=count,
        )

        return True, f"AcademicPeriod '{period.name}' closed successfully. {count} student results computed & published.", count
