from decimal import Decimal
from typing import Dict, Any, Optional
from apps.assessments.models import GradingScale, GradingScaleRule, GradingScaleType, AssessmentComponent


class GradingService:
    """
    Core engine for multi-tier assessment grading, letter-grade conversions,
    and below-average/high-performance classification.
    """

    @classmethod
    def get_effective_scale(cls, school, grade=None) -> GradingScale:
        """
        Resolves the active grading scale for the given grade or school.
        Falls back to creating the standard Ethiopian MOE Scale if none exists.
        """
        return GradingScale.get_effective_scale(school, grade=grade)

    @classmethod
    def evaluate_mark(cls, school, mark_value, max_marks=100.0, grade=None) -> Dict[str, Any]:
        """
        Calculates letter grade, GPA, performance tier, and passing status
        for a given numerical score.
        """
        scale = cls.get_effective_scale(school, grade=grade)
        if not scale:
            # Safe basic fallback
            val = float(mark_value or 0.0)
            max_m = float(max_marks or 100.0) if float(max_marks or 100.0) > 0 else 100.0
            percent = (val / max_m) * 100.0
            is_pass = percent >= 50.0
            tier = 'BELOW_AVERAGE' if percent < 60.0 else ('HIGH_PERFORMANCE' if percent >= 90.0 else 'NORMAL')
            return {
                'letter': 'A' if percent >= 85 else ('B' if percent >= 75 else ('C' if percent >= 60 else ('D' if percent >= 50 else 'F'))),
                'gpa': 4.0 if percent >= 85 else (3.0 if percent >= 75 else (2.0 if percent >= 60 else (1.0 if percent >= 50 else 0.0))),
                'description': 'Pass' if is_pass else 'Fail',
                'is_passing': is_pass,
                'tier': tier,
                'percent': round(percent, 2),
                'scale_name': 'Fallback Scale'
            }

        res = scale.evaluate_score(mark_value, max_marks=max_marks)
        res['letter_grade'] = res['letter']
        res['gpa_points'] = res['gpa']
        res['scale_name'] = scale.name
        return res

    @classmethod
    def convert_letter_to_score(cls, school, letter_grade: str, max_marks=100.0, grade=None) -> Optional[Decimal]:
        """
        Supports Option B (Direct Letter Grade Entry):
        Maps entered letter grade (e.g. 'A+', 'B') to standard mid-point numerical score
        for calculation and aggregation purposes.
        """
        if not letter_grade:
            return None
        clean_letter = letter_grade.strip().upper()
        scale = cls.get_effective_scale(school, grade=grade)
        if not scale:
            letter_defaults = {
                'A+': 95.0, 'A': 87.5, 'B+': 82.5, 'B': 77.5,
                'C+': 70.0, 'C': 57.5, 'D': 45.0, 'F': 25.0
            }
            score_100 = letter_defaults.get(clean_letter, 50.0)
            return Decimal(str(round((score_100 / 100.0) * float(max_marks), 2)))

        rule = scale.rules.filter(letter_grade__iexact=clean_letter).first()
        if rule:
            # Mid-point score of rule range
            mid_percent = (float(rule.min_score) + float(rule.max_score)) / 2.0
            return Decimal(str(round((mid_percent / 100.0) * float(max_marks), 2)))

        return None
