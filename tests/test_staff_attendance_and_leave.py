import uuid
import datetime
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.teachers.models import StaffProfile, StaffPosition, StaffLeaveRequest, LeaveType, LeaveRequestStatus
from apps.attendance.models import StaffAttendanceRecord, StaffAttendanceStatus
from apps.attendance.services import StaffLeaveService


class StaffAttendanceAndLeaveTest(TestCase):
    def test_staff_attendance_and_leave_approval_workflow(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"Leave Academy {uid}", subdomain=f"leave-{uid}", code=f"LAC-{uid.upper()}")
        staff_user = User.objects.create_user(username=f"accountant_{uid}", school=school, role=UserRole.ACCOUNTANT)
        admin_user = User.objects.create_user(username=f"admin_{uid}", school=school, role=UserRole.SCHOOL_ADMIN)

        StaffProfile.objects.create(
            school=school, user=staff_user, employee_id=f"ACC-{uid}", department="Finance", position=StaffPosition.ACCOUNTANT
        )

        # 1. Record Staff Attendance (PRESENT & LATE)
        d1 = datetime.date(2024, 1, 10)
        d2 = datetime.date(2024, 1, 11)

        att1 = StaffAttendanceRecord.objects.create(
            school=school, staff_user=staff_user, date=d1, status=StaffAttendanceStatus.PRESENT, recorded_by=admin_user
        )
        self.assertEqual(att1.status, StaffAttendanceStatus.PRESENT)

        att2 = StaffAttendanceRecord.objects.create(
            school=school, staff_user=staff_user, date=d2, status=StaffAttendanceStatus.LATE, time_in=datetime.time(8, 45), recorded_by=admin_user
        )
        self.assertEqual(att2.status, StaffAttendanceStatus.LATE)

        # 2. Submit Staff Leave Request
        leave_start = datetime.date(2024, 1, 15)
        leave_end = datetime.date(2024, 1, 17)

        leave_req = StaffLeaveRequest.objects.create(
            school=school,
            staff_user=staff_user,
            leave_type=LeaveType.ANNUAL,
            start_date=leave_start,
            end_date=leave_end,
            reason="Annual family vacation"
        )
        self.assertEqual(leave_req.status, LeaveRequestStatus.PENDING)

        # 3. Approve Leave Request & Verify Automatic Staff Attendance Synchronization
        approved_req = StaffLeaveService.approve_leave_request(leave_req, reviewer=admin_user)
        self.assertEqual(approved_req.status, LeaveRequestStatus.APPROVED)

        # Verify 3 StaffAttendanceRecords created with status 'LEAVE' for Jan 15, 16, 17
        leave_attendances = StaffAttendanceRecord.objects.filter(school=school, staff_user=staff_user, status=StaffAttendanceStatus.LEAVE)
        self.assertEqual(leave_attendances.count(), 3)

        print("\nSTAFF ATTENDANCE & LEAVE APPROVAL WORKFLOW TEST PASSED CLEANLY!")
