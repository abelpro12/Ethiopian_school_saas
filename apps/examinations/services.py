from decimal import Decimal
import datetime
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.examinations.models import (
    ExamSchedule, OnlineExam, ExamQuestion, QuestionOption,
    StudentExamAttempt, StudentAnswer, ExamProctoringLog,
    QuestionType, AttemptStatus, ProctoringEventType
)
from apps.enrollment.models import StudentEnrollment
from apps.students.models import StudentProfile


class ExamGradingService:
    """
    Automated and manual grading engine for Online Examinations.
    Evaluates MCQ, Multiple Choice, True/False, and Short Answer questions,
    computes aggregate scores, and synchronizes marks with school gradebooks.
    """

    @classmethod
    def grade_attempt(cls, attempt: StudentExamAttempt, auto_grade_only: bool = True) -> StudentExamAttempt:
        """
        Grades all objective questions in an exam attempt, updates score totals,
        percentages, and pass/fail status.
        """
        exam = attempt.online_exam
        school = attempt.school
        answers = attempt.answers.select_related('question').prefetch_related('selected_options', 'question__options')

        total_awarded = Decimal('0.00')
        has_pending_essay = False

        for answer in answers:
            q = answer.question
            q_type = q.question_type
            points = q.points

            if q_type in [QuestionType.MCQ, QuestionType.TRUE_FALSE]:
                correct_opt = q.options.filter(is_correct=True).first()
                selected_opt = answer.selected_options.first()
                
                if correct_opt and selected_opt and selected_opt.id == correct_opt.id:
                    answer.is_correct = True
                    answer.marks_awarded = points
                else:
                    answer.is_correct = False
                    answer.marks_awarded = Decimal('0.00')
                answer.save(update_fields=['is_correct', 'marks_awarded'])
                total_awarded += answer.marks_awarded

            elif q_type == QuestionType.MULTIPLE_CHOICE:
                correct_opt_ids = set(q.options.filter(is_correct=True).values_list('id', flat=True))
                selected_opt_ids = set(answer.selected_options.values_list('id', flat=True))

                if correct_opt_ids and correct_opt_ids == selected_opt_ids:
                    answer.is_correct = True
                    answer.marks_awarded = points
                elif correct_opt_ids and selected_opt_ids.issubset(correct_opt_ids) and len(selected_opt_ids) > 0:
                    # Partial credit proportional
                    fraction = Decimal(len(selected_opt_ids)) / Decimal(len(correct_opt_ids))
                    answer.is_correct = False
                    answer.marks_awarded = round(points * fraction, 2)
                else:
                    answer.is_correct = False
                    answer.marks_awarded = Decimal('0.00')
                answer.save(update_fields=['is_correct', 'marks_awarded'])
                total_awarded += answer.marks_awarded

            elif q_type == QuestionType.SHORT_ANSWER:
                expected = (q.correct_short_answer or '').strip()
                given = (answer.text_response or '').strip()

                if not expected:
                    is_corr = False
                elif q.case_sensitive:
                    # Allow multiple pipe-separated or comma-separated answers
                    acceptable = [ans.strip() for ans in expected.replace('|', ',').split(',') if ans.strip()]
                    is_corr = given in acceptable
                else:
                    acceptable = [ans.strip().lower() for ans in expected.replace('|', ',').split(',') if ans.strip()]
                    is_corr = given.lower() in acceptable

                answer.is_correct = is_corr
                answer.marks_awarded = points if is_corr else Decimal('0.00')
                answer.save(update_fields=['is_correct', 'marks_awarded'])
                total_awarded += answer.marks_awarded

            elif q_type == QuestionType.ESSAY:
                if answer.is_correct is None and not auto_grade_only:
                    has_pending_essay = True
                elif answer.is_correct is not None:
                    total_awarded += answer.marks_awarded
                else:
                    has_pending_essay = True

        # Calculate percentages
        exam_total = exam.total_marks or exam.calculated_total_points or Decimal('100.00')
        if exam_total > 0:
            percentage = round((total_awarded / exam_total) * Decimal('100.00'), 2)
        else:
            percentage = Decimal('0.00')

        attempt.total_score = total_awarded
        attempt.percentage = percentage
        attempt.is_passed = percentage >= (exam.pass_mark or Decimal('50.00'))

        if has_pending_essay:
            attempt.status = AttemptStatus.SUBMITTED
        else:
            attempt.status = AttemptStatus.GRADED

        attempt.save(update_fields=['total_score', 'percentage', 'is_passed', 'status'])

        # If exam has an assessment component attached, sync automatically
        if exam.assessment_component and attempt.status == AttemptStatus.GRADED:
            cls.sync_mark_to_gradebook(attempt)

        return attempt

    @classmethod
    def sync_mark_to_gradebook(cls, attempt: StudentExamAttempt) -> bool:
        """
        Synchronizes an online exam score into the official StudentMark model for report cards.
        """
        exam = attempt.online_exam
        if not exam.assessment_component:
            return False

        from apps.assessments.models import StudentMark
        from apps.enrollment.models import StudentEnrollment

        student_user = attempt.student
        student_profile = getattr(student_user, 'student_profile', None)
        if not student_profile:
            return False

        enrollment = StudentEnrollment.objects.filter(
            school=attempt.school,
            student=student_profile,
            academic_year=exam.academic_year
        ).first()

        if not enrollment:
            return False

        comp = exam.assessment_component
        # Calculate raw points scored
        if exam.total_marks and comp.max_marks and exam.total_marks != comp.max_marks and exam.total_marks > 0:
            points_to_save = round((attempt.total_score / exam.total_marks) * comp.max_marks, 2)
        else:
            points_to_save = attempt.total_score

        mark, _ = StudentMark.objects.get_or_create(
            school=attempt.school,
            enrollment=enrollment,
            assessment_component=comp,
            defaults={
                'mark_value': points_to_save,
                'entered_by': attempt.graded_by or exam.created_by
            }
        )
        mark.mark_value = points_to_save
        mark.save()
        return True


class ExamSecurityService:
    """
    Handles proctoring incident detection, event logging, and anti-cheating policy enforcement.
    """

    @classmethod
    def log_incident(
        cls,
        attempt: StudentExamAttempt,
        event_type: str,
        description: str = "",
        ip_address: str = None,
        user_agent: str = None
    ) -> dict:
        """
        Logs a security incident and increments candidate violation count.
        If violations exceed the exam threshold, flags or auto-submits the attempt.
        """
        exam = attempt.online_exam
        school = attempt.school

        # Create log entry
        ExamProctoringLog.objects.create(
            school=school,
            attempt=attempt,
            event_type=event_type,
            event_description=description
        )

        # Increment violation counter for cheating indicators
        is_violation = event_type in [
            ProctoringEventType.TAB_SWITCH,
            ProctoringEventType.FULLSCREEN_EXIT,
            ProctoringEventType.WINDOW_BLUR,
            ProctoringEventType.COPY_PASTE
        ]

        if is_violation:
            attempt.violation_count += 1
            if attempt.violation_count >= exam.max_violations_allowed:
                attempt.is_flagged = True
                attempt.flag_reason = f"Exceeded maximum allowed security violations ({attempt.violation_count} incidents recorded)."

        if ip_address and not attempt.ip_address:
            attempt.ip_address = ip_address
        if user_agent and not attempt.user_agent:
            attempt.user_agent = user_agent

        attempt.save(update_fields=['violation_count', 'is_flagged', 'flag_reason', 'ip_address', 'user_agent'])

        should_auto_submit = attempt.violation_count >= exam.max_violations_allowed and exam.enable_proctoring

        return {
            'violation_count': attempt.violation_count,
            'max_allowed': exam.max_violations_allowed,
            'is_flagged': attempt.is_flagged,
            'should_auto_submit': should_auto_submit
        }


class ExamAnalyticsService:
    """
    Computes performance distributions, pass rates, and item difficulty analytics for an exam.
    """

    @classmethod
    def get_exam_analytics(cls, exam: OnlineExam) -> dict:
        attempts = exam.attempts.filter(status__in=[AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED])
        total_attempts = attempts.count()

        if total_attempts == 0:
            return {
                'total_candidates': 0,
                'average_score': 0,
                'average_percentage': 0,
                'pass_count': 0,
                'fail_count': 0,
                'pass_rate': 0,
                'highest_score': 0,
                'lowest_score': 0,
                'distribution': {'0-40': 0, '41-60': 0, '61-80': 0, '81-100': 0},
                'questions_analytics': []
            }

        scores = [float(a.total_score) for a in attempts]
        percentages = [float(a.percentage) for a in attempts]
        passed_attempts = attempts.filter(is_passed=True).count()

        avg_score = round(sum(scores) / total_attempts, 2)
        avg_pct = round(sum(percentages) / total_attempts, 2)
        pass_rate = round((passed_attempts / total_attempts) * 100, 1)

        # Distribution buckets
        distribution = {
            '0-40': sum(1 for p in percentages if p <= 40),
            '41-60': sum(1 for p in percentages if 40 < p <= 60),
            '61-80': sum(1 for p in percentages if 60 < p <= 80),
            '81-100': sum(1 for p in percentages if p > 80),
        }

        # Item difficulty analysis
        questions_analytics = []
        for q in exam.questions.all():
            total_answers = StudentAnswer.objects.filter(question=q, attempt__in=attempts).count()
            correct_answers = StudentAnswer.objects.filter(question=q, attempt__in=attempts, is_correct=True).count()
            success_rate = round((correct_answers / total_answers * 100), 1) if total_answers > 0 else 0
            
            questions_analytics.append({
                'id': str(q.id),
                'order': q.order + 1,
                'type': q.get_question_type_display(),
                'text': q.question_text[:80],
                'points': float(q.points),
                'total_answers': total_answers,
                'correct_answers': correct_answers,
                'success_rate': success_rate
            })

        return {
            'total_candidates': total_attempts,
            'average_score': avg_score,
            'average_percentage': avg_pct,
            'pass_count': passed_attempts,
            'fail_count': total_attempts - passed_attempts,
            'pass_rate': pass_rate,
            'highest_score': max(scores) if scores else 0,
            'lowest_score': min(scores) if scores else 0,
            'distribution': distribution,
            'questions_analytics': questions_analytics
        }


class ExamSeatingGeneratorService:
    """
    Automated Exam Seating Generator (Point 21).
    Assigns students to Hall, Row, Seat, and generates printable seating plans.
    """
    @staticmethod
    def generate_seating_plan(exam_schedule: ExamSchedule, rows_per_hall: int = 5, seats_per_row: int = 8):
        school = exam_schedule.school
        section = exam_schedule.section

        enrollments = StudentEnrollment.objects.filter(
            school=school, section=section, status='ACTIVE'
        ).order_by('student__last_name', 'student__first_name')
        
        seating_plan = []
        seat_num = 1

        for idx, enrollment in enumerate(enrollments):
            row_num = (idx // seats_per_row) + 1
            seat_in_row = (idx % seats_per_row) + 1
            
            seating_plan.append({
                'student_id': enrollment.student.student_id,
                'student_name': enrollment.student.full_name,
                'hall': exam_schedule.room or 'Main Hall',
                'row': f"Row {row_num}",
                'seat': f"Seat {seat_in_row}",
                'seating_number': f"SEAT-{seat_num:03d}"
            })
            seat_num += 1

        return seating_plan
