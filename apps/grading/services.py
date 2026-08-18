from decimal import Decimal
from django.db.models import Sum
from .models import GradeScaleRule
from apps.assessments.models import StudentMark, MarkStatus
from apps.enrollment.models import StudentEnrollment
from apps.academics.models import AcademicPeriod, AcademicYear, Subject

class GradeService:
    @staticmethod
    def get_letter_grade(school, total_score: float) -> str:
        """
        Determines the letter grade for a given total percentage score based on school rules.
        Default standard scale fallback if no custom scale rules configured yet.
        """
        rules = GradeScaleRule.objects.filter(school=school).order_by('-min_score')
        if rules.exists():
            for rule in rules:
                if rule.min_score <= total_score <= rule.max_score:
                    return rule.grade_letter
        
        # Standard Ethiopian High School Grading Scale Fallback
        score = float(total_score)
        if score >= 90:
            return 'A+'
        elif score >= 83:
            return 'A'
        elif score >= 75:
            return 'B+'
        elif score >= 68:
            return 'B'
        elif score >= 60:
            return 'C+'
        elif score >= 50:
            return 'C'
        elif score >= 40:
            return 'D'
        else:
            return 'F'


def calculate_subject_total(enrollment: StudentEnrollment, subject: Subject, period: AcademicPeriod):
    """
    Calculates the total marks for a specific subject in a specific period.
    Only considers PUBLISHED marks.
    """
    marks = StudentMark.objects.filter(
        enrollment=enrollment,
        assessment_component__subject=subject,
        assessment_component__period=period,
        status=MarkStatus.PUBLISHED
    ).aggregate(total=Sum('mark_value'))
    
    return marks['total'] or Decimal('0.00')


def calculate_period_average(enrollment: StudentEnrollment, period: AcademicPeriod):
    """
    Calculates the period average for a student.
    """
    subjects = enrollment.section.stream.subjects.all()
    if not subjects:
        return Decimal('0.00')

    total_score = Decimal('0.00')
    for subject in subjects:
        total_score += calculate_subject_total(enrollment, subject, period)

    return round(total_score / len(subjects), 2)


def calculate_rankings(enrollments, period: AcademicPeriod):
    """
    Calculates rankings for a given queryset of enrollments (e.g. section, grade, or stream).
    Handles ties deterministically (Standard Competition Ranking).
    """
    student_scores = []
    for enrollment in enrollments:
        avg = calculate_period_average(enrollment, period)
        student_scores.append({'enrollment': enrollment, 'average': avg})

    # Sort descending
    student_scores.sort(key=lambda x: x['average'], reverse=True)

    rankings = []
    current_rank = 1
    previous_average = None
    
    for i, data in enumerate(student_scores):
        if previous_average is not None and data['average'] < previous_average:
            current_rank = i + 1
            
        rankings.append({
            'enrollment': data['enrollment'],
            'average': data['average'],
            'rank': current_rank
        })
        previous_average = data['average']

    return rankings
