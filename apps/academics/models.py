from django.db import models
from django.core.exceptions import ValidationError
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User

class AcademicYearStatus(models.TextChoices):
    PLANNING = 'PLANNING', 'Planning'
    ACTIVE = 'ACTIVE', 'Active'
    CLOSING = 'CLOSING', 'Closing'
    ARCHIVED = 'ARCHIVED', 'Archived'

class AcademicYear(TenantAwareModel):
    name = models.CharField(max_length=100)  # e.g., "2016 E.C. (2023/24)"
    ethiopian_year = models.IntegerField(default=2016)
    gregorian_start_date = models.DateField()
    gregorian_end_date = models.DateField()
    ethiopian_start_date = models.CharField(max_length=50, blank=True, null=True)
    ethiopian_end_date = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=AcademicYearStatus.choices, default=AcademicYearStatus.ACTIVE)

    class Meta:
        unique_together = ('school', 'name')

    def clean(self):
        super().clean()
        import datetime
        start = self.gregorian_start_date
        if isinstance(start, str) and start:
            try:
                start = datetime.date.fromisoformat(start)
            except ValueError:
                start = None

        end = self.gregorian_end_date
        if isinstance(end, str) and end:
            try:
                end = datetime.date.fromisoformat(end)
            except ValueError:
                end = None

        if start and end and start >= end:
            raise ValidationError("Gregorian start date must be before Gregorian end date.")

    def save(self, *args, **kwargs):
        if self.ethiopian_year:
            try:
                from apps.academics.ethiopian_date import ethiopian_to_gregorian, gregorian_to_ethiopian
                calc_start = ethiopian_to_gregorian(self.ethiopian_year, 1, 1)
                calc_end = ethiopian_to_gregorian(self.ethiopian_year, 10, 30)
                if not self.gregorian_start_date or (self.gregorian_start_date and gregorian_to_ethiopian(self.gregorian_start_date)[0] != self.ethiopian_year):
                    self.gregorian_start_date = calc_start
                if not self.gregorian_end_date or (self.gregorian_end_date and gregorian_to_ethiopian(self.gregorian_end_date)[0] != self.ethiopian_year):
                    self.gregorian_end_date = calc_end
            except Exception:
                pass

        self.clean()
        if self.gregorian_start_date:
            try:
                from apps.academics.ethiopian_date import format_ethiopian_date
                self.ethiopian_start_date = format_ethiopian_date(self.gregorian_start_date)
            except Exception:
                pass
        if self.gregorian_end_date:
            try:
                from apps.academics.ethiopian_date import format_ethiopian_date
                self.ethiopian_end_date = format_ethiopian_date(self.gregorian_end_date)
            except Exception:
                pass
        if self.is_active:
            # Deactivate all other years for this school
            AcademicYear.objects.filter(school=self.school, is_active=True).exclude(pk=self.pk).update(is_active=False, status=AcademicYearStatus.ARCHIVED)
            self.status = AcademicYearStatus.ACTIVE
        super().save(*args, **kwargs)

    def formatted_name(self, pref=None):
        if not pref:
            try:
                from apps.academics.middleware import get_current_calendar_preference
                pref = get_current_calendar_preference()
            except Exception:
                pref = None
            if not pref:
                pref = getattr(self.school, 'calendar_preference', 'ETHIOPIAN') if self.school else 'ETHIOPIAN'

        if pref == 'GREGORIAN':
            start_y = self.gregorian_start_date.year if self.gregorian_start_date else (self.ethiopian_year + 8)
            end_y = self.gregorian_end_date.year if self.gregorian_end_date else (self.ethiopian_year + 9)
            return f"{start_y}/{end_y} G.C."
        else:
            return f"{self.ethiopian_year} E.C."

    @property
    def display_name(self):
        return self.formatted_name()

    def __str__(self):
        return f"{self.display_name}"


class PeriodStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    CLOSING = 'CLOSING', 'Closing'
    CLOSED = 'CLOSED', 'Closed'
    LOCKED = 'LOCKED', 'Locked'


class PeriodType(models.TextChoices):
    SEMESTER = 'SEMESTER', 'Semester'
    TERM = 'TERM', 'Term'
    QUARTER = 'QUARTER', 'Quarter'
    CUSTOM = 'CUSTOM', 'Custom'

class AcademicPeriod(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='academic_periods')
    name = models.CharField(max_length=100)  # e.g., "Semester 1", "Term 1", "Quarter 1"
    period_type = models.CharField(max_length=20, choices=PeriodType.choices, default=PeriodType.SEMESTER)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=PeriodStatus.choices, default=PeriodStatus.OPEN)


    class Meta:
        unique_together = ('school', 'academic_year', 'name')
        ordering = ['start_date']

    def clean(self):
        super().clean()
        import datetime

        start = self.start_date
        if isinstance(start, str) and start:
            try:
                start = datetime.date.fromisoformat(start)
            except ValueError:
                start = None

        end = self.end_date
        if isinstance(end, str) and end:
            try:
                end = datetime.date.fromisoformat(end)
            except ValueError:
                end = None

        if start and end and start >= end:
            raise ValidationError("Period start date must be before end date.")

        if self.academic_year:
            ay_start = self.academic_year.gregorian_start_date
            if isinstance(ay_start, str) and ay_start:
                try:
                    ay_start = datetime.date.fromisoformat(ay_start)
                except ValueError:
                    ay_start = None

            ay_end = self.academic_year.gregorian_end_date
            if isinstance(ay_end, str) and ay_end:
                try:
                    ay_end = datetime.date.fromisoformat(ay_end)
                except ValueError:
                    ay_end = None

            if start and ay_start and start < ay_start:
                raise ValidationError("Period start date cannot be before Academic Year start date.")
            if end and ay_end and end > ay_end:
                raise ValidationError("Period end date cannot be after Academic Year end date.")

    def save(self, *args, **kwargs):
        self.clean()
        if self.is_current:
            AcademicPeriod.objects.filter(school=self.school, is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


ETHIOPIAN_GRADES = [
    {'level': 9,  'name': 'Grade 9',      'stream_type': 'GEN'},
    {'level': 10, 'name': 'Grade 10',     'stream_type': 'GEN'},
    {'level': 11, 'name': 'Grade 11 (NS)','stream_type': 'NAT'},
    {'level': 11, 'name': 'Grade 11 (SS)','stream_type': 'SOC'},
    {'level': 12, 'name': 'Grade 12 (NS)','stream_type': 'NAT'},
    {'level': 12, 'name': 'Grade 12 (SS)','stream_type': 'SOC'},
]


class Grade(TenantAwareModel):
    STREAM_TYPE_CHOICES = [
        ('GEN', 'General'),
        ('NAT', 'Natural Science'),
        ('SOC', 'Social Science'),
    ]
    level = models.IntegerField()  # 9, 10, 11, 12
    name = models.CharField(max_length=50)  # "Grade 9", "Grade 11 (NS)"
    stream_type = models.CharField(max_length=10, choices=STREAM_TYPE_CHOICES, default='GEN')

    class Meta:
        unique_together = ('school', 'level', 'stream_type')
        ordering = ['level', 'stream_type']

    def __str__(self):
        return self.name

class Stream(TenantAwareModel):
    STREAM_TYPES = [
        ('GEN', 'General'),
        ('NAT', 'Natural Science'),
        ('SOC', 'Social Science'),
    ]
    name = models.CharField(max_length=100)  # "Natural Science"
    code = models.CharField(max_length=10, choices=STREAM_TYPES, default='GEN')

    class Meta:
        unique_together = ('school', 'code')

    def __str__(self):
        return self.name


class Section(TenantAwareModel):
    SHIFT_CHOICES = [
        ('MORNING', 'Morning'),
        ('AFTERNOON', 'Afternoon'),
        ('FULL_DAY', 'Full Day'),
    ]


    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='sections')
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=50)  # e.g., "A", "11-Nat-1"
    capacity = models.IntegerField(default=45)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='FULL_DAY')
    class_teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_sections')
    tutorial_teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tutorial_sections', help_text="Teacher assigned as Tutorial Controller for this section")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'grade', 'stream', 'name')

    def __str__(self):
        return f"{self.grade.name}-{self.name} ({self.stream.name})"


class Subject(TenantAwareModel):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)  # e.g. "Physics"
    amharic_name = models.CharField(max_length=100, blank=True, null=True)  # e.g. "ፊዚክስ"
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='subjects')
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='subjects')

    class Meta:
        unique_together = ('school', 'code', 'grade', 'stream')

    def __str__(self):
        return f"{self.name} ({self.grade.name} {self.stream.code})"


class DayOfWeek(models.TextChoices):
    MONDAY = 'MONDAY', 'Monday / ሰኞ'
    TUESDAY = 'TUESDAY', 'Tuesday / ማክሰኞ'
    WEDNESDAY = 'WEDNESDAY', 'Wednesday / ረቡዕ'
    THURSDAY = 'THURSDAY', 'Thursday / ሐሙስ'
    FRIDAY = 'FRIDAY', 'Friday / አርብ'


class PeriodSlot(TenantAwareModel):
    name = models.CharField(max_length=50)  # e.g., "Period 1"
    start_time = models.TimeField()
    end_time = models.TimeField()
    shift = models.CharField(max_length=20, default='FULL_DAY')

    class Meta:
        unique_together = ('school', 'name', 'shift')
        ordering = ['start_time']

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class TimetableSlot(TenantAwareModel):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='timetable_slots')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_slots')
    teacher = models.ForeignKey('teachers.TeacherProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='timetable_slots')
    day_of_week = models.CharField(max_length=20, choices=DayOfWeek.choices)
    period_slot = models.ForeignKey(PeriodSlot, on_delete=models.CASCADE, related_name='timetable_slots')
    room = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        unique_together = ('school', 'section', 'day_of_week', 'period_slot')

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        # Teacher Conflict Detection
        if self.teacher:
            teacher_conflict = TimetableSlot.objects.filter(
                school=self.school,
                teacher=self.teacher,
                day_of_week=self.day_of_week,
                period_slot=self.period_slot
            ).exclude(pk=self.pk).exists()
            
            if teacher_conflict:
                raise ValidationError(f"Teacher {self.teacher} is already scheduled during {self.day_of_week} - {self.period_slot.name}.")
                
        # Room Conflict Detection
        if self.room:
            room_conflict = TimetableSlot.objects.filter(
                school=self.school,
                room=self.room,
                day_of_week=self.day_of_week,
                period_slot=self.period_slot
            ).exclude(pk=self.pk).exists()
            
            if room_conflict:
                raise ValidationError(f"Room {self.room} is already booked during {self.day_of_week} - {self.period_slot.name}.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.section.name} - {self.day_of_week} {self.period_slot.name}: {self.subject.code}"


class EventType(models.TextChoices):
    SCHOOL_EVENT = 'SCHOOL_EVENT', 'School Event'
    PARENT_MEETING = 'PARENT_MEETING', 'Parent Meeting'
    TEACHER_MEETING = 'TEACHER_MEETING', 'Teacher Meeting'
    HOLIDAY = 'HOLIDAY', 'Holiday'
    CEREMONY = 'CEREMONY', 'School Ceremony / Celebration'
    EXAM_PERIOD = 'EXAM_PERIOD', 'Examination Period'
    REGISTRATION_PERIOD = 'REGISTRATION_PERIOD', 'Registration Period'
    RESULT_PUBLICATION = 'RESULT_PUBLICATION', 'Result Publication Date'
    YEAR_CLOSING = 'YEAR_CLOSING', 'Year Closing'


class TargetAudience(models.TextChoices):
    ALL = 'ALL', 'All Users'
    PARENTS = 'PARENTS', 'Parents'
    TEACHERS = 'TEACHERS', 'Teachers'
    STUDENTS = 'STUDENTS', 'Students'


class SchoolEvent(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='school_events')
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=50, choices=EventType.choices, default=EventType.SCHOOL_EVENT)
    target_audience = models.CharField(max_length=20, choices=TargetAudience.choices, default=TargetAudience.ALL)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()}) [{self.start_date}]"


class AcademicEvent(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()})"


class PromotionPolicy(TenantAwareModel):
    name = models.CharField(max_length=100, default="Default Promotion Policy")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='promotion_policies', null=True, blank=True)
    minimum_average = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    minimum_attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=75.00)
    maximum_failed_subjects = models.IntegerField(default=2)
    allow_conditional_promotion = models.BooleanField(default=True)
    allow_supplementary_exam = models.BooleanField(default=True)
    graduation_minimum_gpa = models.DecimalField(max_digits=5, decimal_places=2, default=50.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'name')

    def __str__(self):
        return f"{self.school.name} - {self.name} (Min Avg: {self.minimum_average}%)"


class StreamCriteria(TenantAwareModel):
    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name='criteria')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='stream_criteria', null=True, blank=True)
    minimum_overall_average = models.DecimalField(max_digits=5, decimal_places=2, default=60.00)
    subject_requirements = models.JSONField(default=dict, help_text="Minimum marks dictionary e.g. {'MATH': 75.0, 'PHYS': 70.0}")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'stream', 'academic_year')




from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Subject)
def auto_sync_components_for_new_subject(sender, instance, created, **kwargs):
    if created and instance.school:
        try:
            from apps.assessments.models import AssessmentComponent
            master_comps = AssessmentComponent.objects.filter(school=instance.school)
            if master_comps.exists():
                seen_keys = set()
                for mc in master_comps:
                    key = (mc.academic_year_id, mc.period_id, mc.name)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        AssessmentComponent.objects.get_or_create(
                            school=instance.school,
                            academic_year=mc.academic_year,
                            period=mc.period,
                            subject=instance,
                            name=mc.name,
                            defaults={'weight': mc.weight, 'max_marks': mc.max_marks}
                        )
        except Exception:
            pass


