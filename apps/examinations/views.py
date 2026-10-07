import json
from decimal import Decimal
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import models

from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Section, Grade
from apps.enrollment.models import StudentEnrollment
from apps.students.models import StudentProfile
from apps.assessments.models import AssessmentComponent

from .models import (
    OnlineExam, ExamQuestion, QuestionOption, StudentExamAttempt,
    StudentAnswer, ExamProctoringLog, OnlineExamStatus, QuestionType,
    AttemptStatus, ProctoringEventType
)
from .services import ExamGradingService, ExamSecurityService, ExamAnalyticsService


def _is_staff_or_teacher(user):
    return user.role in [
        UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN,
        UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.TEACHER
    ]


def _group_by_grade_and_stream(queryset, grade_attr='grade', stream_attr='stream'):
    grouped = {}
    for item in queryset:
        grade = getattr(item, grade_attr, None)
        stream = getattr(item, stream_attr, None)
        if grade and stream:
            key = f"{grade.name} ({stream.name})"
        elif grade:
            key = grade.name
        else:
            key = "General"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
    return grouped


def _group_components_by_grade_and_stream(components):
    grouped = {}
    for comp in components:
        subj = getattr(comp, 'subject', None)
        grade = getattr(subj, 'grade', None) if subj else None
        stream = getattr(subj, 'stream', None) if subj else None
        if grade and stream:
            key = f"{grade.name} ({stream.name})"
        elif grade:
            key = grade.name
        else:
            key = "General"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(comp)
    return grouped


# ============================================================================
# TEACHER & SCHOOL ADMIN MANAGEMENT VIEWS
# ============================================================================

@login_required
def online_exam_list_view(request):
    """
    Teacher and Admin Exam Dashboard:
    List all online exams with status filters, search, and overall metrics.
    """
    school = getattr(request, 'school', None)
    user = request.user

    if user.role == UserRole.STUDENT:
        return redirect('examinations:student_list')

    if not _is_staff_or_teacher(user):
        messages.error(request, "Access restricted to teaching and administrative staff.")
        return redirect('index')

    current_ay = getattr(request, 'academic_year', None)
    exams = OnlineExam.objects.filter(school=school).select_related(
        'academic_year', 'period', 'subject__grade', 'subject__stream', 'grade', 'section', 'created_by'
    )

    if user.role == UserRole.TEACHER:
        teacher = getattr(user, 'teacher_profile', None)
        from apps.teachers.models import TeacherAssignment
        if teacher and current_ay:
            assigned_sub_ids = TeacherAssignment.objects.filter(
                school=school, teacher=teacher, academic_year=current_ay
            ).values_list('subject_id', flat=True)
            exams = exams.filter(models.Q(created_by=user) | models.Q(subject_id__in=assigned_sub_ids))
        else:
            exams = exams.filter(created_by=user)

    # Filtering
    status_filter = request.GET.get('status')
    if status_filter:
        exams = exams.filter(status=status_filter)

    grade_filter = request.GET.get('grade')
    if grade_filter:
        exams = exams.filter(models.Q(grade_id=grade_filter) | models.Q(subject__grade_id=grade_filter))

    subject_filter = request.GET.get('subject')
    if subject_filter:
        exams = exams.filter(subject_id=subject_filter)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        exams = exams.filter(title__icontains=search_query)

    # Metrics
    total_exams = exams.count()
    now = timezone.now()
    active_now = sum(1 for e in exams if e.is_active_now)
    total_submissions = StudentExamAttempt.objects.filter(
        school=school, online_exam__in=exams, status__in=[AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]
    ).count()

    subjects = Subject.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'stream__name', 'name')
    grouped_subjects = _group_by_grade_and_stream(subjects)
    grades = Grade.objects.filter(school=school).order_by('level')

    return render(request, 'examinations/list.html', {
        'exams': exams,
        'total_exams': total_exams,
        'active_now': active_now,
        'total_submissions': total_submissions,
        'subjects': subjects,
        'grouped_subjects': grouped_subjects,
        'grades': grades,
        'status_filter': status_filter,
        'grade_filter': grade_filter,
        'subject_filter': subject_filter,
        'search_query': search_query,
        'current_ay': current_ay,
    })


@login_required
def online_exam_create_view(request):
    """
    Wizard / Form to create a new Online Examination.
    """
    school = getattr(request, 'school', None)
    user = request.user
    current_ay = getattr(request, 'academic_year', None)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized to create online exams.")
        return redirect('examinations:list')

    subjects = Subject.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'stream__name', 'name')
    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    periods = AcademicPeriod.objects.filter(school=school)
    if current_ay:
        periods = periods.filter(academic_year=current_ay)
    components = AssessmentComponent.objects.filter(school=school).select_related('subject__grade', 'subject__stream', 'period').order_by('subject__grade__level', 'subject__stream__name', 'subject__name', 'name')
    if current_ay:
        components = components.filter(academic_year=current_ay)

    grouped_subjects = _group_by_grade_and_stream(subjects)
    grouped_sections = _group_by_grade_and_stream(sections)
    grouped_components = _group_components_by_grade_and_stream(components)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        subject_id = request.POST.get('subject_id')
        grade_id = request.POST.get('grade_id') or None
        section_id = request.POST.get('section_id') or None
        period_id = request.POST.get('period_id') or None
        component_id = request.POST.get('assessment_component_id') or None
        
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        duration_minutes = int(request.POST.get('duration_minutes', 60))
        total_marks = Decimal(request.POST.get('total_marks', '100.00'))
        pass_mark = Decimal(request.POST.get('pass_mark', '50.00'))
        
        description = request.POST.get('description', '').strip()
        instructions = request.POST.get('instructions', '').strip()
        
        shuffle_questions = request.POST.get('shuffle_questions') == 'on'
        shuffle_options = request.POST.get('shuffle_options') == 'on'
        allow_backtracking = request.POST.get('allow_backtracking') == 'on'
        show_results_immediately = request.POST.get('show_results_immediately') == 'on'
        show_correct_answers = request.POST.get('show_correct_answers') == 'on'
        enable_proctoring = request.POST.get('enable_proctoring') == 'on'
        max_violations = int(request.POST.get('max_violations_allowed', 3))

        try:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            
            end_time = datetime.datetime.fromisoformat(end_time_str)
            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            if end_time <= start_time:
                messages.error(request, "Exam end time must be after the start time.")
                return render(request, 'examinations/create_edit.html', {
                    'subjects': subjects, 'grouped_subjects': grouped_subjects,
                    'grades': grades, 'sections': sections, 'grouped_sections': grouped_sections,
                    'periods': periods, 'components': components, 'grouped_components': grouped_components,
                    'is_edit': False
                })

            subject = Subject.objects.get(id=subject_id, school=school)
            grade = Grade.objects.get(id=grade_id, school=school) if grade_id else subject.grade
            section = Section.objects.get(id=section_id, school=school) if section_id else None
            period = AcademicPeriod.objects.get(id=period_id, school=school) if period_id else None
            component = AssessmentComponent.objects.get(id=component_id, school=school) if component_id else None

            exam = OnlineExam.objects.create(
                school=school,
                academic_year=current_ay or AcademicYear.objects.filter(school=school, is_active=True).first(),
                period=period,
                subject=subject,
                grade=grade,
                section=section,
                title=title,
                description=description,
                instructions=instructions,
                created_by=user,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                total_marks=total_marks,
                pass_mark=pass_mark,
                status=OnlineExamStatus.DRAFT,
                shuffle_questions=shuffle_questions,
                shuffle_options=shuffle_options,
                allow_backtracking=allow_backtracking,
                show_results_immediately=show_results_immediately,
                show_correct_answers_after_submission=show_correct_answers,
                enable_proctoring=enable_proctoring,
                max_violations_allowed=max_violations,
                assessment_component=component
            )
            messages.success(request, f"Online Exam '{exam.title}' created successfully! Now add questions.")
            return redirect('examinations:questions_builder', exam_id=exam.id)

        except Exception as e:
            messages.error(request, f"Error creating exam: {str(e)}")

    return render(request, 'examinations/create_edit.html', {
        'subjects': subjects,
        'grouped_subjects': grouped_subjects,
        'grades': grades,
        'sections': sections,
        'grouped_sections': grouped_sections,
        'periods': periods,
        'components': components,
        'grouped_components': grouped_components,
        'is_edit': False
    })


@login_required
def online_exam_edit_view(request, exam_id):
    """
    Edit settings of an existing Online Exam.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    subjects = Subject.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'stream__name', 'name')
    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    periods = AcademicPeriod.objects.filter(school=school)
    components = AssessmentComponent.objects.filter(school=school).select_related('subject__grade', 'subject__stream', 'period').order_by('subject__grade__level', 'subject__stream__name', 'subject__name', 'name')

    grouped_subjects = _group_by_grade_and_stream(subjects)
    grouped_sections = _group_by_grade_and_stream(sections)
    grouped_components = _group_components_by_grade_and_stream(components)

    if request.method == 'POST':
        exam.title = request.POST.get('title', '').strip()
        exam.subject_id = request.POST.get('subject_id')
        exam.grade_id = request.POST.get('grade_id') or None
        exam.section_id = request.POST.get('section_id') or None
        exam.period_id = request.POST.get('period_id') or None
        exam.assessment_component_id = request.POST.get('assessment_component_id') or None
        
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        exam.duration_minutes = int(request.POST.get('duration_minutes', 60))
        exam.total_marks = Decimal(request.POST.get('total_marks', '100.00'))
        exam.pass_mark = Decimal(request.POST.get('pass_mark', '50.00'))
        
        exam.description = request.POST.get('description', '').strip()
        exam.instructions = request.POST.get('instructions', '').strip()
        
        exam.shuffle_questions = request.POST.get('shuffle_questions') == 'on'
        exam.shuffle_options = request.POST.get('shuffle_options') == 'on'
        exam.allow_backtracking = request.POST.get('allow_backtracking') == 'on'
        exam.show_results_immediately = request.POST.get('show_results_immediately') == 'on'
        exam.show_correct_answers_after_submission = request.POST.get('show_correct_answers') == 'on'
        exam.enable_proctoring = request.POST.get('enable_proctoring') == 'on'
        exam.max_violations_allowed = int(request.POST.get('max_violations_allowed', 3))

        try:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            
            end_time = datetime.datetime.fromisoformat(end_time_str)
            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)

            if end_time <= start_time:
                messages.error(request, "Exam end time must be after the start time.")
            else:
                exam.start_time = start_time
                exam.end_time = end_time
                exam.save()
                messages.success(request, f"Exam '{exam.title}' updated successfully.")
                return redirect('examinations:detail', exam_id=exam.id)
        except Exception as e:
            messages.error(request, f"Error updating exam: {str(e)}")

    return render(request, 'examinations/create_edit.html', {
        'exam': exam,
        'subjects': subjects,
        'grouped_subjects': grouped_subjects,
        'grades': grades,
        'sections': sections,
        'grouped_sections': grouped_sections,
        'periods': periods,
        'components': components,
        'grouped_components': grouped_components,
        'is_edit': True
    })


@login_required
def online_exam_detail_view(request, exam_id):
    """
    Exam Details Hub: Overview, quick links to Builder, Proctoring Monitor, Grading, and Analytics.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    questions = exam.questions.prefetch_related('options').all()
    attempts = exam.attempts.select_related('student').all()
    
    in_progress_count = attempts.filter(status=AttemptStatus.IN_PROGRESS).count()
    completed_count = attempts.filter(status__in=[AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]).count()
    flagged_count = attempts.filter(is_flagged=True).count()

    return render(request, 'examinations/detail.html', {
        'exam': exam,
        'questions': questions,
        'attempts': attempts[:10],
        'total_attempts': attempts.count(),
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'flagged_count': flagged_count,
    })


@login_required
def online_exam_toggle_publish_view(request, exam_id):
    """Toggle publish / draft status of an exam."""
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if exam.status == OnlineExamStatus.DRAFT:
        if exam.questions.count() == 0:
            messages.error(request, "Cannot publish an exam with zero questions. Add questions first.")
            return redirect('examinations:questions_builder', exam_id=exam.id)
        exam.status = OnlineExamStatus.PUBLISHED
        messages.success(request, f"Exam '{exam.title}' is now PUBLISHED and available to students during its schedule.")
    else:
        exam.status = OnlineExamStatus.DRAFT
        messages.info(request, f"Exam '{exam.title}' has been moved to DRAFT.")
    exam.save(update_fields=['status'])
    return redirect('examinations:detail', exam_id=exam.id)


@login_required
def online_exam_delete_view(request, exam_id):
    """Safe exam deletion."""
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)
    title = exam.title
    exam.delete()
    messages.success(request, f"Exam '{title}' has been deleted.")
    return redirect('examinations:list')


# ============================================================================
# QUESTION BUILDER STUDIO & BULK IMPORTER
# ============================================================================

@login_required
def online_exam_questions_builder_view(request, exam_id):
    """
    Interactive Question Builder:
    Add MCQ, Multi-Select, True/False, Short Answer, and Essay questions with options and points.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    if request.method == 'POST':
        action = request.POST.get('action', 'add_question')

        if action == 'add_question':
            q_text = request.POST.get('question_text', '').strip()
            q_type = request.POST.get('question_type', QuestionType.MCQ)
            points = Decimal(request.POST.get('points', '1.00'))
            explanation = request.POST.get('explanation', '').strip()
            correct_short = request.POST.get('correct_short_answer', '').strip()
            case_sensitive = request.POST.get('case_sensitive') == 'on'

            if not q_text:
                messages.error(request, "Question text cannot be empty.")
                return redirect('examinations:questions_builder', exam_id=exam.id)

            next_order = exam.questions.count()
            question = ExamQuestion.objects.create(
                school=school,
                online_exam=exam,
                question_text=q_text,
                question_type=q_type,
                points=points,
                order=next_order,
                explanation=explanation,
                correct_short_answer=correct_short if q_type == QuestionType.SHORT_ANSWER else None,
                case_sensitive=case_sensitive
            )

            # Process options for MCQ, Multi-select, and True/False
            if q_type in [QuestionType.MCQ, QuestionType.MULTIPLE_CHOICE]:
                option_texts = request.POST.getlist('option_text[]')
                correct_indices = request.POST.getlist('is_correct[]')

                for idx, opt_text in enumerate(option_texts):
                    opt_text = opt_text.strip()
                    if opt_text:
                        is_corr = str(idx) in correct_indices
                        QuestionOption.objects.create(
                            school=school,
                            question=question,
                            option_text=opt_text,
                            is_correct=is_corr,
                            order=idx
                        )

            elif q_type == QuestionType.TRUE_FALSE:
                tf_correct = request.POST.get('tf_correct', 'True')
                QuestionOption.objects.create(
                    school=school, question=question, option_text="True",
                    is_correct=(tf_correct == 'True'), order=0
                )
                QuestionOption.objects.create(
                    school=school, question=question, option_text="False",
                    is_correct=(tf_correct == 'False'), order=1
                )

            messages.success(request, f"Question added successfully.")
            return redirect('examinations:questions_builder', exam_id=exam.id)

    questions = exam.questions.prefetch_related('options').all()
    total_points = sum(q.points for q in questions)

    return render(request, 'examinations/questions_builder.html', {
        'exam': exam,
        'questions': questions,
        'total_points': total_points,
        'question_types': QuestionType.choices
    })


@login_required
def online_exam_question_delete_view(request, exam_id, question_id):
    """Delete a single question from an exam."""
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)
    question = get_object_or_404(ExamQuestion, id=question_id, online_exam=exam, school=school)
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect('examinations:questions_builder', exam_id=exam.id)


@login_required
def online_exam_bulk_questions_view(request, exam_id):
    """
    Bulk Question Importer via quick text/JSON format.
    """
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if request.method == 'POST':
        raw_data = request.POST.get('bulk_data', '').strip()
        try:
            items = json.loads(raw_data)
            created_count = 0
            curr_order = exam.questions.count()

            for item in items:
                q_text = item.get('question')
                q_type = item.get('type', 'MCQ')
                points = Decimal(str(item.get('points', 1.0)))
                options = item.get('options', [])
                correct_ans = item.get('correct_answer')

                if q_text:
                    q = ExamQuestion.objects.create(
                        school=school,
                        online_exam=exam,
                        question_text=q_text,
                        question_type=q_type,
                        points=points,
                        order=curr_order,
                        correct_short_answer=correct_ans if q_type == 'SHORT_ANSWER' else None
                    )
                    curr_order += 1
                    created_count += 1

                    for idx, opt in enumerate(options):
                        opt_text = opt if isinstance(opt, str) else opt.get('text', '')
                        is_corr = (opt_text == correct_ans) if isinstance(opt, str) else opt.get('is_correct', False)
                        QuestionOption.objects.create(
                            school=school, question=q, option_text=opt_text, is_correct=is_corr, order=idx
                        )

            messages.success(request, f"Successfully imported {created_count} questions!")
            return redirect('examinations:questions_builder', exam_id=exam.id)

        except Exception as e:
            messages.error(request, f"Invalid JSON format: {str(e)}")

    return render(request, 'examinations/bulk_questions.html', {'exam': exam})


# ============================================================================
# LIVE PROCTORING & INVIGILATION MONITOR
# ============================================================================

@login_required
def online_exam_monitor_view(request, exam_id):
    """
    Live Invigilation & Proctoring Cockpit:
    Real-time candidate cards with progress, timer, violation counter, and intervention controls.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    attempts = exam.attempts.select_related('student').prefetch_related('answers', 'proctoring_logs').all()
    
    total_assigned = attempts.count()
    in_progress = attempts.filter(status=AttemptStatus.IN_PROGRESS).count()
    completed = attempts.filter(status__in=[AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]).count()
    flagged = attempts.filter(is_flagged=True).count()

    recent_logs = ExamProctoringLog.objects.filter(
        school=school, attempt__online_exam=exam
    ).select_related('attempt__student').order_by('-timestamp')[:25]

    return render(request, 'examinations/monitor.html', {
        'exam': exam,
        'attempts': attempts,
        'total_assigned': total_assigned,
        'in_progress': in_progress,
        'completed': completed,
        'flagged': flagged,
        'recent_logs': recent_logs,
    })


@login_required
@require_POST
def online_exam_monitor_action_view(request, exam_id):
    """
    Invigilator intervention actions: Extend time, Force submit, Disqualify, or Clear flags.
    """
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)
    attempt_id = request.POST.get('attempt_id')
    action = request.POST.get('action')
    reason = request.POST.get('reason', '').strip()

    attempt = get_object_or_404(StudentExamAttempt, id=attempt_id, online_exam=exam, school=school)

    if action == 'extend_time':
        extra_mins = int(request.POST.get('extra_minutes', 10))
        attempt.extra_time_minutes += extra_mins
        attempt.save(update_fields=['extra_time_minutes'])
        ExamProctoringLog.objects.create(
            school=school, attempt=attempt,
            event_type=ProctoringEventType.EXTEND_TIME,
            event_description=f"Invigilator {request.user.username} granted +{extra_mins} extra minutes. Reason: {reason or 'None'}"
        )
        messages.success(request, f"Added {extra_mins} extra minutes for {attempt.student.get_full_name()}.")

    elif action == 'force_submit':
        attempt.status = AttemptStatus.AUTO_SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['status', 'submitted_at'])
        ExamGradingService.grade_attempt(attempt)
        ExamProctoringLog.objects.create(
            school=school, attempt=attempt,
            event_type=ProctoringEventType.FORCE_SUBMIT,
            event_description=f"Invigilator {request.user.username} force-submitted exam. Reason: {reason or 'None'}"
        )
        messages.warning(request, f"Force-submitted exam for {attempt.student.get_full_name()}.")

    elif action == 'disqualify':
        attempt.status = AttemptStatus.DISQUALIFIED
        attempt.is_flagged = True
        attempt.flag_reason = reason or "Disqualified by Invigilator for academic dishonesty."
        attempt.save(update_fields=['status', 'is_flagged', 'flag_reason'])
        ExamProctoringLog.objects.create(
            school=school, attempt=attempt,
            event_type=ProctoringEventType.DISQUALIFIED,
            event_description=f"Disqualified by {request.user.username}. Reason: {reason}"
        )
        messages.error(request, f"Disqualified {attempt.student.get_full_name()}.")

    elif action == 'clear_flag':
        attempt.is_flagged = False
        attempt.flag_reason = None
        attempt.save(update_fields=['is_flagged', 'flag_reason'])
        messages.success(request, f"Cleared flags for {attempt.student.get_full_name()}.")

    return redirect('examinations:monitor', exam_id=exam.id)


@login_required
def online_exam_live_status_api(request, exam_id):
    """
    JSON polling endpoint for the Live Monitor dashboard to auto-refresh student status.
    """
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    attempts = exam.attempts.select_related('student').prefetch_related('answers').all()
    data = []

    for a in attempts:
        data.append({
            'id': str(a.id),
            'student_name': a.student.get_full_name() or a.student.username,
            'student_id': getattr(getattr(a.student, 'student_profile', None), 'student_id', 'N/A'),
            'status': a.status,
            'status_display': a.get_status_display(),
            'answered_count': a.answered_count,
            'total_questions': exam.question_count,
            'remaining_seconds': a.remaining_seconds,
            'violation_count': a.violation_count,
            'is_flagged': a.is_flagged,
            'flag_reason': a.flag_reason or '',
            'total_score': float(a.total_score),
            'percentage': float(a.percentage)
        })

    return JsonResponse({'status': 'success', 'attempts': data})


# ============================================================================
# EVALUATION, GRADING STUDIO & ANALYTICS
# ============================================================================

@login_required
def online_exam_grading_list_view(request, exam_id):
    """
    Grading Hub: List of student submissions with scores and pending essay count.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    attempts = exam.attempts.select_related('student').prefetch_related('answers__question').all()

    return render(request, 'examinations/grading_list.html', {
        'exam': exam,
        'attempts': attempts,
    })


@login_required
def online_exam_submission_grade_view(request, exam_id, attempt_id):
    """
    Teacher Evaluation Studio for an individual student attempt.
    Review student essay answers, award points, provide feedback, and compute final mark.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)
    attempt = get_object_or_404(StudentExamAttempt, id=attempt_id, online_exam=exam, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    answers = attempt.answers.select_related('question').prefetch_related('selected_options', 'question__options').all()

    if request.method == 'POST':
        for ans in answers:
            if ans.question.question_type == QuestionType.ESSAY:
                score_key = f"score_{ans.id}"
                feedback_key = f"feedback_{ans.id}"
                
                awarded_str = request.POST.get(score_key, '0.00')
                feedback_str = request.POST.get(feedback_key, '').strip()

                try:
                    awarded = Decimal(awarded_str)
                    awarded = min(awarded, ans.question.points)  # Cap at max points
                    ans.marks_awarded = awarded
                    ans.is_correct = (awarded > 0)
                    ans.teacher_feedback = feedback_str
                    ans.save(update_fields=['marks_awarded', 'is_correct', 'teacher_feedback'])
                except Exception:
                    pass

        attempt.graded_by = user
        attempt.feedback = request.POST.get('general_feedback', '').strip()
        attempt.save(update_fields=['graded_by', 'feedback'])

        # Recalculate score totals
        ExamGradingService.grade_attempt(attempt, auto_grade_only=False)

        messages.success(request, f"Evaluation saved for {attempt.student.get_full_name()}! Total Score: {attempt.total_score}/{exam.total_marks}")
        return redirect('examinations:grading_list', exam_id=exam.id)

    return render(request, 'examinations/grade_submission.html', {
        'exam': exam,
        'attempt': attempt,
        'answers': answers,
    })


@login_required
def online_exam_sync_grades_view(request, exam_id):
    """
    One-click push of all graded online exam marks to official gradebook.
    """
    school = getattr(request, 'school', None)
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not exam.assessment_component:
        messages.error(request, "This exam is not linked to any Assessment Component. Link one in Exam Settings first.")
        return redirect('examinations:detail', exam_id=exam.id)

    attempts = exam.attempts.filter(status=AttemptStatus.GRADED)
    synced_count = 0

    for attempt in attempts:
        if ExamGradingService.sync_mark_to_gradebook(attempt):
            synced_count += 1

    messages.success(request, f"Successfully synchronized {synced_count} student marks into '{exam.assessment_component.name}' gradebook!")
    return redirect('examinations:detail', exam_id=exam.id)


@login_required
def online_exam_analytics_view(request, exam_id):
    """
    Visual Analytics Dashboard: Score distribution, pass rate, and item difficulty matrix.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    if not _is_staff_or_teacher(user):
        messages.error(request, "Unauthorized.")
        return redirect('examinations:list')

    analytics = ExamAnalyticsService.get_exam_analytics(exam)

    return render(request, 'examinations/analytics.html', {
        'exam': exam,
        'analytics': analytics,
        'distribution_json': json.dumps(analytics['distribution']),
    })


# ============================================================================
# STUDENT CBT TAKING ENVIRONMENT
# ============================================================================

@login_required
def student_exam_list_view(request):
    """
    Student Portal:
    View available exams, upcoming scheduled exams, and past completed exam results.
    """
    school = getattr(request, 'school', None)
    user = request.user
    current_ay = getattr(request, 'academic_year', None)

    # Get student profile & enrollment
    student_profile = getattr(user, 'student_profile', None)
    user_section = None
    user_grade = None

    if student_profile and current_ay:
        enrollment = StudentEnrollment.objects.filter(
            school=school, student=student_profile, academic_year=current_ay
        ).select_related('section__grade').first()
        if enrollment:
            user_section = enrollment.section
            user_grade = enrollment.section.grade

    exams = OnlineExam.objects.filter(
        school=school,
        status__in=[OnlineExamStatus.PUBLISHED, OnlineExamStatus.ONGOING, OnlineExamStatus.COMPLETED]
    ).select_related('subject', 'academic_year', 'period')

    if user_section:
        exams = exams.filter(
            models.Q(section=user_section) |
            models.Q(grade=user_grade, section__isnull=True) |
            models.Q(grade__isnull=True, section__isnull=True)
        )

    now = timezone.now()
    available_exams = []
    upcoming_exams = []
    past_exams = []

    for exam in exams:
        attempt = StudentExamAttempt.objects.filter(school=school, online_exam=exam, student=user).first()
        exam_data = {'exam': exam, 'attempt': attempt}

        if attempt and attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]:
            past_exams.append(exam_data)
        elif exam.start_time <= now <= exam.end_time:
            available_exams.append(exam_data)
        elif now < exam.start_time:
            upcoming_exams.append(exam_data)
        else:
            past_exams.append(exam_data)

    return render(request, 'examinations/student_list.html', {
        'available_exams': available_exams,
        'upcoming_exams': upcoming_exams,
        'past_exams': past_exams,
        'current_ay': current_ay,
    })


@login_required
def student_exam_instructions_view(request, exam_id):
    """
    Pre-Test Instructions & Readiness Verification Screen.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    attempt = StudentExamAttempt.objects.filter(school=school, online_exam=exam, student=user).first()
    if attempt and attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]:
        return redirect('examinations:student_result', attempt_id=attempt.id)

    now = timezone.now()
    if now < exam.start_time:
        messages.info(request, f"This exam has not started yet. It will open at {exam.start_time.strftime('%Y-%m-%d %H:%M')}.")
        return redirect('examinations:student_list')

    if now > exam.end_time:
        messages.error(request, "This exam window has closed.")
        return redirect('examinations:student_list')

    return render(request, 'examinations/student_instructions.html', {
        'exam': exam,
        'attempt': attempt,
    })


@login_required
def student_exam_room_view(request, exam_id):
    """
    Interactive CBT Exam Room:
    Distraction-free environment with countdown timer, question palette,
    auto-save on every answer, fullscreen enforcement, and anti-cheating monitoring.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)

    # Initialize or retrieve attempt
    attempt, created = StudentExamAttempt.objects.get_or_create(
        school=school,
        online_exam=exam,
        student=user,
        defaults={
            'status': AttemptStatus.IN_PROGRESS,
            'started_at': timezone.now(),
            'ip_address': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT')
        }
    )

    if attempt.status in [AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]:
        return redirect('examinations:student_result', attempt_id=attempt.id)

    if attempt.status == AttemptStatus.DISQUALIFIED:
        messages.error(request, f"You have been disqualified from this exam: {attempt.flag_reason}")
        return redirect('examinations:student_list')

    if not attempt.started_at:
        attempt.started_at = timezone.now()
        attempt.status = AttemptStatus.IN_PROGRESS
        attempt.save(update_fields=['started_at', 'status'])

    # Check if time expired
    if attempt.remaining_seconds <= 0:
        attempt.status = AttemptStatus.AUTO_SUBMITTED
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=['status', 'submitted_at'])
        ExamGradingService.grade_attempt(attempt)
        return redirect('examinations:student_result', attempt_id=attempt.id)

    # Load questions (shuffled if configured)
    questions = list(exam.questions.prefetch_related('options').all())
    if exam.shuffle_questions:
        import random
        random.seed(str(attempt.id))
        random.shuffle(questions)

    # Load existing student answers
    existing_answers = {
        ans.question_id: ans for ans in attempt.answers.prefetch_related('selected_options').all()
    }

    questions_data = []
    for idx, q in enumerate(questions):
        ans = existing_answers.get(q.id)
        selected_opt_ids = list(ans.selected_options.values_list('id', flat=True)) if ans else []
        text_resp = ans.text_response if ans else ''
        is_flagged = ans.is_marked_for_review if ans else False

        options = list(q.options.all())
        if exam.shuffle_options:
            import random
            random.seed(f"{attempt.id}_{q.id}")
            random.shuffle(options)

        questions_data.append({
            'question': q,
            'order_index': idx + 1,
            'options': options,
            'selected_option_ids': [str(opt_id) for opt_id in selected_opt_ids],
            'text_response': text_resp,
            'is_marked_for_review': is_flagged,
            'is_answered': len(selected_opt_ids) > 0 or bool(text_resp.strip())
        })

    return render(request, 'examinations/student_exam_room.html', {
        'exam': exam,
        'attempt': attempt,
        'questions_data': questions_data,
        'remaining_seconds': attempt.remaining_seconds,
        'total_questions': len(questions),
    })


@login_required
@csrf_exempt
@require_POST
def student_save_answer_api(request):
    """
    AJAX Autosave Endpoint:
    Silently persists candidate answers as they type or select options.
    """
    school = getattr(request, 'school', None)
    user = request.user

    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        question_id = data.get('question_id')
        selected_option_ids = data.get('selected_option_ids', [])
        text_response = data.get('text_response', '').strip()
        is_marked_for_review = data.get('is_marked_for_review', False)

        attempt = get_object_or_404(StudentExamAttempt, id=attempt_id, student=user, school=school)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return JsonResponse({'success': False, 'error': 'Exam session is closed.'}, status=403)

        question = get_object_or_404(ExamQuestion, id=question_id, online_exam=attempt.online_exam)

        answer, _ = StudentAnswer.objects.get_or_create(
            school=school,
            attempt=attempt,
            question=question
        )

        answer.text_response = text_response
        answer.is_marked_for_review = is_marked_for_review
        answer.save()

        # Update options
        if selected_option_ids:
            options = QuestionOption.objects.filter(id__in=selected_option_ids, question=question)
            answer.selected_options.set(options)
        else:
            answer.selected_options.clear()

        return JsonResponse({
            'success': True,
            'answered_count': attempt.answered_count,
            'remaining_seconds': attempt.remaining_seconds
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@csrf_exempt
@require_POST
def student_log_proctoring_event_api(request):
    """
    AJAX Anti-Cheat Incident Tracker:
    Logs tab switching, fullscreen exit, blur events and returns violation count.
    """
    school = getattr(request, 'school', None)
    user = request.user

    try:
        data = json.loads(request.body)
        attempt_id = data.get('attempt_id')
        event_type = data.get('event_type')
        description = data.get('description', '')

        attempt = get_object_or_404(StudentExamAttempt, id=attempt_id, student=user, school=school)
        if attempt.status != AttemptStatus.IN_PROGRESS:
            return JsonResponse({'success': False, 'error': 'Exam session is closed.'}, status=403)

        result = ExamSecurityService.log_incident(
            attempt=attempt,
            event_type=event_type,
            description=description,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )

        if result.get('should_auto_submit'):
            attempt.status = AttemptStatus.AUTO_SUBMITTED
            attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['status', 'submitted_at'])
            ExamGradingService.grade_attempt(attempt)

        return JsonResponse({
            'success': True,
            'violation_count': result['violation_count'],
            'max_allowed': result['max_allowed'],
            'should_auto_submit': result['should_auto_submit']
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def student_submit_exam_view(request, exam_id):
    """
    Final submission handler triggered when student finishes or timer runs out.
    Runs automated grading and routes candidate to scorecard.
    """
    school = getattr(request, 'school', None)
    user = request.user
    exam = get_object_or_404(OnlineExam, id=exam_id, school=school)
    attempt = get_object_or_404(StudentExamAttempt, online_exam=exam, student=user, school=school)

    if attempt.status == AttemptStatus.IN_PROGRESS:
        attempt.status = AttemptStatus.SUBMITTED
        attempt.submitted_at = timezone.now()
        if attempt.started_at:
            attempt.time_spent_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
        attempt.save(update_fields=['status', 'submitted_at', 'time_spent_seconds'])

        # Auto-grade
        ExamGradingService.grade_attempt(attempt)

    messages.success(request, f"Exam '{exam.title}' submitted successfully!")
    return redirect('examinations:student_result', attempt_id=attempt.id)


@login_required
def student_exam_result_view(request, attempt_id):
    """
    Student Scorecard & Result Review screen.
    """
    school = getattr(request, 'school', None)
    user = request.user
    attempt = get_object_or_404(StudentExamAttempt, id=attempt_id, school=school)

    # Permission check: Student can view their own attempt; Teachers/Admins can view any
    if user.role == UserRole.STUDENT and attempt.student != user:
        return HttpResponseForbidden("Unauthorized to view this result.")

    exam = attempt.online_exam
    answers = attempt.answers.select_related('question').prefetch_related('selected_options', 'question__options').all()

    return render(request, 'examinations/student_result.html', {
        'exam': exam,
        'attempt': attempt,
        'answers': answers,
        'allow_review': exam.show_correct_answers_after_submission or user.role != UserRole.STUDENT,
    })
