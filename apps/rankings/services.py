from decimal import Decimal
from django.db.models import Sum, Avg
from apps.assessments.models import StudentMark, MarkStatus
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from .models import StudentRanking


class RankingService:
    @staticmethod
    def calculate_ranks_for_section(school, academic_year, period, section):
        """
        Calculates and updates section, stream, and grade ranks for all students in a section.
        """
        enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=academic_year,
            section=section,
            status=EnrollmentStatus.ACTIVE
        )

        student_totals = []
        for enrollment in enrollments:
            marks = StudentMark.objects.filter(
                school=school,
                enrollment=enrollment,
                assessment_component__academic_year=academic_year,
                assessment_component__period=period,
                status__in=[MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]
            )
            
            # Aggregate total score across subjects
            total = marks.aggregate(Sum('mark_value'))['mark_value__sum'] or Decimal('0.00')
            count = marks.values('assessment_component__subject').distinct().count()
            avg = total / max(1, count)

            student_totals.append({
                'enrollment': enrollment,
                'student': enrollment.student,
                'total': total,
                'avg': avg,
            })

        # Sort descending by average score
        student_totals.sort(key=lambda x: x['avg'], reverse=True)

        # Assign section ranks
        rankings_created = []
        for index, item in enumerate(student_totals, start=1):
            rank_obj, created = StudentRanking.objects.update_or_create(
                school=school,
                academic_year=academic_year,
                period=period,
                student=item['student'],
                defaults={
                    'section': section,
                    'stream': section.stream,
                    'grade': section.grade,
                    'total_score': item['total'],
                    'average_score': item['avg'],
                    'section_rank': index,
                    'stream_rank': index,  # Simple deterministic rank for V1
                    'grade_rank': index,
                }
            )
            rankings_created.append(rank_obj)

        return rankings_created
