import uuid
import secrets
from django.db import models
from django.utils import timezone
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Section, Subject


class MeetingType(models.TextChoices):
    VIRTUAL_CLASS = 'VIRTUAL_CLASS', 'Virtual Class / Live Lecture'
    PARENT_TEACHER = 'PARENT_TEACHER', 'Parent-Teacher Conference'
    STAFF_MEETING = 'STAFF_MEETING', 'Staff / Department Meeting'
    DIRECT_CALL = 'DIRECT_CALL', 'Direct 1-on-1 Consultation'
    GUEST_CONSULTATION = 'GUEST_CONSULTATION', 'Special Guest / VIP & External Call'
    GENERAL = 'GENERAL', 'General Meeting / Assembly'


class MeetingStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    LIVE = 'LIVE', 'Live Now'
    ENDED = 'ENDED', 'Ended'
    CANCELLED = 'CANCELLED', 'Cancelled'


class VideoMeeting(TenantAwareModel):
    """
    Tenant-aware video meeting / virtual classroom session.
    Supports scheduled live classes, instant consultations, school conferences,
    and external/special guest video calls.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    meeting_type = models.CharField(
        max_length=30,
        choices=MeetingType.choices,
        default=MeetingType.VIRTUAL_CLASS
    )
    host = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='hosted_video_meetings'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_meetings'
    )
    
    # Class-specific targeting (For Virtual Classes)
    target_grade = models.ForeignKey(
        Grade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_meetings'
    )
    target_section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_meetings'
    )
    target_subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='video_meetings'
    )

    # Specific invited users (for Parent-Teacher 1-on-1 or Staff)
    invited_participants = models.ManyToManyField(
        User,
        blank=True,
        related_name='invited_video_meetings'
    )

    # Guest Access for External Callers (MoE inspectors, prospective parents, guest lecturers)
    allow_guest_access = models.BooleanField(
        default=True,
        help_text="Allow external guests to join without logging in using a secure guest link"
    )
    guest_token = models.CharField(max_length=64, blank=True, null=True, unique=True)

    room_name = models.CharField(max_length=255, unique=True)
    passcode = models.CharField(max_length=50, blank=True, null=True)
    scheduled_start = models.DateTimeField(default=timezone.now)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=45)
    status = models.CharField(
        max_length=20,
        choices=MeetingStatus.choices,
        default=MeetingStatus.SCHEDULED
    )

    is_recorded = models.BooleanField(default=False)
    recording_url = models.URLField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(fields=['school', 'status', 'scheduled_start']),
            models.Index(fields=['school', 'meeting_type']),
            models.Index(fields=['guest_token']),
        ]

    def __str__(self):
        school_code = self.school.code if self.school else 'CORE'
        return f"[{school_code}] {self.title} ({self.get_meeting_type_display()})"

    def save(self, *args, **kwargs):
        if not self.room_name:
            school_prefix = (self.school.code if self.school else 'SCHOOL').replace(' ', '_').lower()
            random_hex = secrets.token_hex(6)
            self.room_name = f"ethioschool_{school_prefix}_{random_hex}"
        
        if not self.guest_token:
            self.guest_token = secrets.token_urlsafe(16)
        
        # Auto-calculate scheduled_end if missing
        if self.scheduled_start and not self.scheduled_end:
            self.scheduled_end = self.scheduled_start + timezone.timedelta(minutes=self.duration_minutes)
            
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        return self.status == MeetingStatus.LIVE

    @property
    def active_participant_count(self):
        return self.attendances.filter(left_at__isnull=True).count()

    @property
    def total_attendee_count(self):
        return self.attendances.count()

    def get_guest_url(self, request=None):
        path = f"/video-calls/guest/{self.guest_token}/"
        if request:
            return request.build_absolute_uri(path)
        return path

    def can_user_access(self, user):
        """
        Check if a given authenticated user has permission to join this meeting room.
        """
        if not user or not user.is_authenticated:
            return False
        
        # Super admin and host always have access
        if user.role == UserRole.SUPER_ADMIN or self.host_id == user.id or user.is_superuser:
            return True
        
        # School admin or principal
        if user.role in [UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
            return True

        # Check direct invitation
        if self.invited_participants.filter(id=user.id).exists():
            return True

        # Guest consultation or general meeting open to school
        if self.meeting_type in [MeetingType.GUEST_CONSULTATION, MeetingType.GENERAL]:
            return True

        # Check Virtual Class Grade/Section matching
        if self.meeting_type == MeetingType.VIRTUAL_CLASS:
            if user.role == UserRole.STUDENT:
                from apps.enrollment.models import StudentEnrollment
                enrollment = StudentEnrollment.objects.filter(
                    student__user=user,
                    school=self.school,
                    status='ACTIVE'
                )
                if self.target_grade:
                    enrollment = enrollment.filter(grade=self.target_grade)
                if self.target_section:
                    enrollment = enrollment.filter(section=self.target_section)
                return enrollment.exists()
            
            elif user.role == UserRole.PARENT:
                from apps.parents.models import GuardianRelationship
                children_student_ids = GuardianRelationship.objects.filter(
                    parent__user=user
                ).values_list('student_id', flat=True)
                
                from apps.enrollment.models import StudentEnrollment
                enrollment = StudentEnrollment.objects.filter(
                    student_id__in=children_student_ids,
                    school=self.school,
                    status='ACTIVE'
                )
                if self.target_grade:
                    enrollment = enrollment.filter(grade=self.target_grade)
                if self.target_section:
                    enrollment = enrollment.filter(section=self.target_section)
                return enrollment.exists()

            elif user.role == UserRole.TEACHER:
                # Teachers in the same school can join classes
                return True

        # Staff meetings accessible to all teachers & staff
        if self.meeting_type == MeetingType.STAFF_MEETING:
            return user.role in [UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.HR_MANAGER, UserRole.ACCOUNTANT]

        return False


class MeetingAttendance(TenantAwareModel):
    """
    Logs participant entry timestamp, exit timestamp, session duration, and guest information.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(
        VideoMeeting,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meeting_attendances'
    )
    guest_name = models.CharField(max_length=150, blank=True, null=True)
    is_guest = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_present = models.BooleanField(default=True)
    device_info = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-joined_at']
        indexes = [
            models.Index(fields=['meeting', 'user']),
            models.Index(fields=['meeting', 'is_guest']),
        ]

    def __str__(self):
        name = self.guest_name if self.is_guest else (self.user.get_full_name() or self.user.username if self.user else 'Anonymous')
        return f"{name} attended {self.meeting.title}"

    @property
    def display_name(self):
        if self.is_guest:
            return f"{self.guest_name} (Guest)"
        if self.user:
            return self.user.get_full_name() or self.user.username
        return "Unknown Participant"

    @property
    def duration_display(self):
        """Format duration_seconds into human readable 'Xh Ym Zs', 'Xm Ys', or 'Xs'."""
        secs = self.duration_seconds or 0
        if secs <= 0:
            if self.is_present and not self.left_at and self.joined_at:
                delta = max(0, int((timezone.now() - self.joined_at).total_seconds()))
                secs = delta
            else:
                return "0s"
        
        hours = secs // 3600
        mins = (secs % 3600) // 60
        remaining_secs = secs % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if mins > 0 or hours > 0:
            parts.append(f"{mins}m")
        parts.append(f"{remaining_secs}s")
        return " ".join(parts)

    def mark_left(self):
        if not self.left_at:
            self.left_at = timezone.now()
            delta = (self.left_at - self.joined_at).total_seconds()
            self.duration_seconds = max(0, int(delta))
            self.save(update_fields=['left_at', 'duration_seconds'])

