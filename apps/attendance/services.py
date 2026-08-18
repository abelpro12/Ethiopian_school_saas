import datetime
from django.utils import timezone
from apps.teachers.models import StaffLeaveRequest, LeaveRequestStatus
from apps.attendance.models import StaffAttendanceRecord, StaffAttendanceStatus
from apps.accounts.models import User


class StaffLeaveService:
    """
    Staff Leave Management & Attendance Synchronization Service (Requirement 10).
    Workflow: Request -> Review -> Approve/Reject -> Record.
    Automatically populates StaffAttendanceRecord with status 'LEAVE' upon approval.
    """
    @staticmethod
    def approve_leave_request(leave_request: StaffLeaveRequest, reviewer: User) -> StaffLeaveRequest:
        leave_request.status = LeaveRequestStatus.APPROVED
        leave_request.reviewed_by = reviewer
        leave_request.reviewed_at = timezone.now()
        leave_request.save()

        # Automatically record 'LEAVE' in StaffAttendanceRecord for each day in range
        current_date = leave_request.start_date
        while current_date <= leave_request.end_date:
            StaffAttendanceRecord.objects.update_or_create(
                school=leave_request.school,
                staff_user=leave_request.staff_user,
                date=current_date,
                defaults={
                    'status': StaffAttendanceStatus.LEAVE,
                    'recorded_by': reviewer,
                    'remarks': f"Approved {leave_request.get_leave_type_display()}"
                }
            )
            current_date += datetime.timedelta(days=1)

        return leave_request

    @staticmethod
    def reject_leave_request(leave_request: StaffLeaveRequest, reviewer: User, rejection_reason: str = None) -> StaffLeaveRequest:
        leave_request.status = LeaveRequestStatus.REJECTED
        leave_request.reviewed_by = reviewer
        leave_request.reviewed_at = timezone.now()
        leave_request.rejection_reason = rejection_reason
        leave_request.save()
        return leave_request


def check_attendance_alerts(school, threshold=3):
    """
    Scans student attendance records and returns students with consecutive absences exceeding threshold.
    """
    from apps.attendance.models import AttendanceRecord
    from apps.students.models import StudentProfile
    from django.db.models import Count

    flagged_students = StudentProfile.objects.filter(
        school=school,
        attendance_records__status='ABSENT'
    ).annotate(
        absence_count=Count('attendance_records')
    ).filter(absence_count__gte=threshold)

    return list(flagged_students)
