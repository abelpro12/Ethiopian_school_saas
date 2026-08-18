import datetime
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import Section, TimetableSlot
from apps.students.models import StudentProfile


class AttendanceStatus(models.TextChoices):
    PRESENT = 'PRESENT', 'Present'
    ABSENT = 'ABSENT', 'Absent'
    LATE = 'LATE', 'Late'
    EXCUSED = 'EXCUSED', 'Excused'


class AttendanceRecord(TenantAwareModel):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    reason = models.CharField(max_length=255, blank=True, null=True, help_text="Reason for absence or lateness")
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'section', 'student', 'date')
        indexes = [
            models.Index(fields=['school', 'date']),
            models.Index(fields=['school', 'section', 'date']),
            models.Index(fields=['school', 'student', 'status']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.date}: {self.status}"


class TutorialAttendanceRecord(TenantAwareModel):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='tutorial_attendance_records')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='tutorial_attendance_records')
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    reason = models.CharField(max_length=255, blank=True, null=True, help_text="Reason for absence or lateness in tutorial")
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'section', 'student', 'date')
        indexes = [
            models.Index(fields=['school', 'date']),
            models.Index(fields=['school', 'section', 'date']),
            models.Index(fields=['school', 'student', 'status']),
        ]

    def __str__(self):
        return f"Tutorial - {self.student.full_name} - {self.date}: {self.status}"


class AttendanceCorrection(TenantAwareModel):
    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='corrections')
    old_status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    new_status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    reason = models.TextField()
    corrected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Correction on {self.attendance_record}: {self.old_status} -> {self.new_status}"


class SubjectAttendanceRecord(TenantAwareModel):
    timetable_slot = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='subject_attendance_records')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='subject_attendance_records')
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'timetable_slot', 'student', 'date')

    def __str__(self):
        return f"{self.student.full_name} - {self.timetable_slot.subject.name} on {self.date}: {self.status}"


class CorrectionRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class AttendanceCorrectionRequest(TenantAwareModel):
    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='correction_requests')
    requested_status = models.CharField(max_length=20, choices=AttendanceStatus.choices)
    reason = models.TextField()
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_correction_requests')
    status = models.CharField(max_length=20, choices=CorrectionRequestStatus.choices, default=CorrectionRequestStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_attendance_corrections')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Correction Request for {self.attendance_record} to {self.requested_status}"


# --- Staff Attendance Module (Requirement 9) ---

class StaffAttendanceStatus(models.TextChoices):
    PRESENT = 'PRESENT', 'Present'
    ABSENT = 'ABSENT', 'Absent'
    LATE = 'LATE', 'Late'
    LEAVE = 'LEAVE', 'On Leave'
    EXCUSED = 'EXCUSED', 'Excused'


class StaffAttendanceRecord(TenantAwareModel):
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='staff_attendance_records')
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(max_length=20, choices=StaffAttendanceStatus.choices, default=StaffAttendanceStatus.PRESENT)
    time_in = models.TimeField(blank=True, null=True)
    time_out = models.TimeField(blank=True, null=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='recorded_staff_attendances')
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'staff_user', 'date')

    def __str__(self):
        return f"Staff Attendance: {self.staff_user.username} on {self.date} - {self.get_status_display()}"
