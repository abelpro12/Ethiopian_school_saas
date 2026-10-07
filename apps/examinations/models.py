import datetime
import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Subject, Section, Grade
from apps.students.models import StudentProfile


class ExamType(models.TextChoices):
    REGULAR = 'REGULAR', 'Regular'
    MAKEUP = 'MAKEUP', 'Make-up'
    SUPPLEMENTARY = 'SUPPLEMENTARY', 'Supplementary'


class ExamStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    ONGOING = 'ONGOING', 'Ongoing'
    COMPLETED = 'COMPLETED', 'Completed'
    LOCKED = 'LOCKED', 'Locked'


class Exam(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='exams')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='exams')
    name = models.CharField(max_length=100)  # e.g., "AcademicPeriod 1 Final Exam"
    exam_type = models.CharField(max_length=20, choices=ExamType.choices, default=ExamType.REGULAR)
    status = models.CharField(max_length=20, choices=ExamStatus.choices, default=ExamStatus.DRAFT)

    class Meta:
        unique_together = ('school', 'academic_year', 'period', 'name')

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class ExamSchedule(TenantAwareModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='schedules')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exam_schedules')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='exam_schedules')
    exam_date = models.DateField()
    room = models.CharField(max_length=50, blank=True, null=True)
    invigilator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ('school', 'exam', 'subject', 'section')

    def clean(self):
        """
        Invigilator Conflict Detection (Point 20):
        Prevents teacher from being assigned as invigilator in two halls/rooms on the same date.
        """
        if self.invigilator and self.exam_date:
            conflict = ExamSchedule.objects.filter(
                school=self.school,
                invigilator=self.invigilator,
                exam_date=self.exam_date
            ).exclude(pk=self.pk).first()

            if conflict:
                raise ValidationError(f"Invigilator {self.invigilator.username} is already assigned to Room '{conflict.room}' on {self.exam_date}.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.exam.name} - {self.subject.code} ({self.section.name})"


class ExamMark(TenantAwareModel):
    exam_schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name='marks')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='exam_marks')
    mark_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('school', 'exam_schedule', 'student')

    def __str__(self):
        return f"{self.student.full_name} - {self.exam_schedule}: {self.mark_obtained}"


# ============================================================================
# ONLINE EXAMINATIONS & CBT (COMPUTER-BASED TESTING) SYSTEM
# ============================================================================

class OnlineExamStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PUBLISHED = 'PUBLISHED', 'Published / Scheduled'
    ONGOING = 'ONGOING', 'Ongoing / Active'
    COMPLETED = 'COMPLETED', 'Completed / Closed'
    ARCHIVED = 'ARCHIVED', 'Archived'


class QuestionType(models.TextChoices):
    MCQ = 'MCQ', 'Multiple Choice (Single Answer)'
    MULTIPLE_CHOICE = 'MULTIPLE_CHOICE', 'Multiple Answers (Checkboxes)'
    TRUE_FALSE = 'TRUE_FALSE', 'True / False'
    SHORT_ANSWER = 'SHORT_ANSWER', 'Short Answer (Fill-in)'
    ESSAY = 'ESSAY', 'Essay / Long Answer'


class AttemptStatus(models.TextChoices):
    NOT_STARTED = 'NOT_STARTED', 'Not Started'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    AUTO_SUBMITTED = 'AUTO_SUBMITTED', 'Auto-Submitted (Time Out / Violation)'
    GRADED = 'GRADED', 'Graded'
    DISQUALIFIED = 'DISQUALIFIED', 'Disqualified'


class ProctoringEventType(models.TextChoices):
    TAB_SWITCH = 'TAB_SWITCH', 'Tab Switch Detected'
    FULLSCREEN_EXIT = 'FULLSCREEN_EXIT', 'Fullscreen Exited'
    RIGHT_CLICK = 'RIGHT_CLICK', 'Right Click / Context Menu'
    COPY_PASTE = 'COPY_PASTE', 'Copy / Paste Attempt'
    WINDOW_BLUR = 'WINDOW_BLUR', 'Window Blur / Focus Lost'
    FORCE_SUBMIT = 'FORCE_SUBMIT', 'Invigilator Force-Submitted'
    EXTEND_TIME = 'EXTEND_TIME', 'Invigilator Extended Time'
    DISQUALIFIED = 'DISQUALIFIED', 'Candidate Disqualified'


class OnlineExam(TenantAwareModel):
    """
    Core Online Exam / CBT Assessment definition.
    Can be linked to formal semester/quarter Exam, or run as standalone tests.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True, related_name='online_exams', help_text="Optional link to formal scheduled exam")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='online_exams')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.SET_NULL, null=True, blank=True, related_name='online_exams')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='online_exams')
    grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True, related_name='online_exams')
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='online_exams', help_text="Optional section filter. If null, open to entire grade.")
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    instructions = models.TextField(blank=True, null=True, default="Read each question carefully before answering. Do not switch tabs or leave fullscreen mode during the test.")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_online_exams')
    
    # Timing & Availability
    start_time = models.DateTimeField(help_text="When students can begin taking the exam")
    end_time = models.DateTimeField(help_text="Deadline when exam closes")
    duration_minutes = models.PositiveIntegerField(default=60, help_text="Exam duration in minutes once started")
    
    # Grading & Marks
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.00)
    pass_mark = models.DecimalField(max_digits=6, decimal_places=2, default=50.00)
    
    status = models.CharField(max_length=20, choices=OnlineExamStatus.choices, default=OnlineExamStatus.DRAFT)
    
    # Anti-Cheating & Proctoring Settings
    shuffle_questions = models.BooleanField(default=True, help_text="Randomize question order for each student")
    shuffle_options = models.BooleanField(default=True, help_text="Randomize MCQ options order for each student")
    allow_backtracking = models.BooleanField(default=True, help_text="Allow students to navigate back to previous questions")
    show_results_immediately = models.BooleanField(default=False, help_text="Show score immediately after submission")
    show_correct_answers_after_submission = models.BooleanField(default=False, help_text="Allow student to review question solutions after grading")
    enable_proctoring = models.BooleanField(default=True, help_text="Enforce fullscreen and detect tab-switching/blur")
    max_violations_allowed = models.PositiveIntegerField(default=3, help_text="Maximum allowed anti-cheat violations before auto-submit/flag")
    
    # Gradebook Link
    assessment_component = models.ForeignKey('assessments.AssessmentComponent', on_delete=models.SET_NULL, null=True, blank=True, related_name='online_exams', help_text="Optionally sync scored marks directly to student mark sheet")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.subject.name})"

    @property
    def is_active_now(self):
        now = timezone.now()
        return self.status in [OnlineExamStatus.PUBLISHED, OnlineExamStatus.ONGOING] and self.start_time <= now <= self.end_time

    @property
    def is_upcoming(self):
        now = timezone.now()
        return self.status == OnlineExamStatus.PUBLISHED and now < self.start_time

    @property
    def is_past_due(self):
        now = timezone.now()
        return timezone.now() > self.end_time or self.status == OnlineExamStatus.COMPLETED

    @property
    def question_count(self):
        return self.questions.count()

    @property
    def calculated_total_points(self):
        return self.questions.aggregate(models.Sum('points'))['points__sum'] or 0

    @property
    def total_candidates_count(self):
        return self.attempts.count()

    @property
    def completed_candidates_count(self):
        return self.attempts.filter(status__in=[AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED, AttemptStatus.GRADED]).count()

    @property
    def in_progress_count(self):
        return self.attempts.filter(status=AttemptStatus.IN_PROGRESS).count()


class ExamQuestion(TenantAwareModel):
    """
    Individual question belonging to an OnlineExam.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    online_exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField(help_text="The question prompt or description")
    question_type = models.CharField(max_length=20, choices=QuestionType.choices, default=QuestionType.MCQ)
    points = models.DecimalField(max_digits=5, decimal_places=2, default=1.00)
    order = models.PositiveIntegerField(default=0)
    explanation = models.TextField(blank=True, null=True, help_text="Explanation shown during result review")
    
    # For SHORT_ANSWER auto-grading:
    correct_short_answer = models.CharField(max_length=255, blank=True, null=True, help_text="Expected answer for auto-graded fill-in questions")
    case_sensitive = models.BooleanField(default=False)

    class Meta:
        ordering = ['order', 'question_text']

    def __str__(self):
        return f"Q{self.order + 1} ({self.get_question_type_display()}): {self.question_text[:50]}"


class QuestionOption(TenantAwareModel):
    """
    Options for MCQ, MULTIPLE_CHOICE, or TRUE_FALSE questions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.option_text} ({'Correct' if self.is_correct else 'Incorrect'})"


class StudentExamAttempt(TenantAwareModel):
    """
    Record of a student taking an OnlineExam session.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    online_exam = models.ForeignKey(OnlineExam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_attempts')
    
    status = models.CharField(max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.NOT_STARTED)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    
    # Extra time granted by invigilator during live proctoring (in minutes)
    extra_time_minutes = models.PositiveIntegerField(default=0)
    
    # Scoring
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_passed = models.BooleanField(default=False)
    
    # Anti-Cheating & Violations Tracking
    violation_count = models.PositiveIntegerField(default=0)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True, null=True)
    
    # Session metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Teacher grading & feedback
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_exam_attempts')
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('school', 'online_exam', 'student')
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.student.get_full_name() or self.student.username} - {self.online_exam.title} ({self.status})"

    @property
    def total_allowed_minutes(self):
        return self.online_exam.duration_minutes + self.extra_time_minutes

    @property
    def remaining_seconds(self):
        if not self.started_at:
            return self.total_allowed_minutes * 60
        elapsed = (timezone.now() - self.started_at).total_seconds()
        total_sec = self.total_allowed_minutes * 60
        remaining = total_sec - elapsed
        return max(0, int(remaining))

    @property
    def answered_count(self):
        return self.answers.filter(
            models.Q(selected_options__isnull=False) | 
            models.Q(text_response__isnull=False, text_response__gt='')
        ).distinct().count()

    @property
    def pending_essay_count(self):
        return self.answers.filter(
            question__question_type=QuestionType.ESSAY,
            is_correct__isnull=True
        ).count()


class StudentAnswer(TenantAwareModel):
    """
    Individual response submitted by student for an ExamQuestion during an attempt.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(StudentExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name='student_answers')
    
    # For MCQ / MULTIPLE_CHOICE / TRUE_FALSE
    selected_options = models.ManyToManyField(QuestionOption, blank=True, related_name='student_selections')
    
    # For SHORT_ANSWER / ESSAY
    text_response = models.TextField(blank=True, null=True)
    
    # Grading results
    is_correct = models.BooleanField(null=True, blank=True)
    marks_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    teacher_feedback = models.TextField(blank=True, null=True)
    
    # Candidate status during exam
    is_marked_for_review = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('school', 'attempt', 'question')

    def __str__(self):
        return f"Ans: {self.attempt.student.username} - {self.question.question_text[:30]} ({self.marks_awarded} pts)"


class ExamProctoringLog(TenantAwareModel):
    """
    Real-time security log tracking tab switches, fullscreen exits, right-clicks,
    and invigilator actions during an online exam session.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(StudentExamAttempt, on_delete=models.CASCADE, related_name='proctoring_logs')
    event_type = models.CharField(max_length=30, choices=ProctoringEventType.choices)
    event_description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.attempt.student.username} - {self.get_event_type_display()} at {self.timestamp.strftime('%H:%M:%S')}"
