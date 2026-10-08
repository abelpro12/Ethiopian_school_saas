import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import (
    AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject,
    PeriodSlot, TimetableSlot, DayOfWeek
)
from apps.teachers.models import TeacherProfile, TeacherAssignment, Department
from apps.teachers.workload_service import TeacherWorkloadService
from apps.timetable.generator_service import TimetableGeneratorService


class WorkloadAndTimetableGeneratorTests(TestCase):
    """
    Comprehensive tests for:
    - Item 5: Department, Section, Subject & Teacher Workload Management
    - Item 6: Automatic Timetable Generator + Manual Drag-and-Drop / Slot Editor
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Seattle Academy",
            code="SEA",
            calendar_preference="ETHIOPIAN"
        )

        # Admin user
        self.admin = User.objects.create_superuser(
            username="admin_sea",
            email="admin@seattle.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        # Faculty Members
        self.teacher_user1 = User.objects.create_user(
            username="teacher_almaz",
            email="almaz@seattle.edu.et",
            password="teacherpass123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Almaz",
            last_name="Kebede"
        )
        self.teacher1 = TeacherProfile.objects.create(
            user=self.teacher_user1,
            school=self.school,
            employee_id="SEA-TCH-0001",
            max_weekly_periods=24,
            max_daily_periods=5
        )

        self.teacher_user2 = User.objects.create_user(
            username="teacher_dawit",
            email="dawit@seattle.edu.et",
            password="teacherpass123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Dawit",
            last_name="Bekele"
        )
        self.teacher2 = TeacherProfile.objects.create(
            user=self.teacher_user2,
            school=self.school,
            employee_id="SEA-TCH-0002",
            max_weekly_periods=26,
            max_daily_periods=6
        )

        # Academic Year & Period
        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            is_active=True
        )

        self.grade = Grade.objects.create(school=self.school, name="Grade 9", level=9)
        self.stream = Stream.objects.create(school=self.school, name="General Stream", code="GEN")
        self.section = Section.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="9-A",
            is_active=True
        )

        # Period Slots (Morning P1, P2, P3, Afternoon P4, P5)
        self.p1 = PeriodSlot.objects.create(
            school=self.school, name="Period 1",
            start_time=datetime.time(8, 30), end_time=datetime.time(9, 15)
        )
        self.p2 = PeriodSlot.objects.create(
            school=self.school, name="Period 2",
            start_time=datetime.time(9, 20), end_time=datetime.time(10, 5)
        )
        self.p3 = PeriodSlot.objects.create(
            school=self.school, name="Period 3",
            start_time=datetime.time(10, 20), end_time=datetime.time(11, 5)
        )
        self.p4 = PeriodSlot.objects.create(
            school=self.school, name="Period 4",
            start_time=datetime.time(11, 10), end_time=datetime.time(11, 55)
        )
        self.p5 = PeriodSlot.objects.create(
            school=self.school, name="Period 5",
            start_time=datetime.time(13, 0), end_time=datetime.time(13, 45)
        )

        # Department
        self.dept_stem = Department.objects.create(
            school=self.school,
            name="Mathematics & IT",
            code="MATH",
            head_of_department=self.teacher1
        )
        self.teacher1.department_obj = self.dept_stem
        self.teacher1.save()

        # Subjects: Math (Core, 5 periods), Physics (Core, 4 periods), Art (Non-core, 2 periods)
        self.sub_math = Subject.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="Mathematics",
            code="MATH-9",
            weekly_periods=5,
            is_core=True,
            department=self.dept_stem
        )
        self.sub_physics = Subject.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="Physics",
            code="PHYS-9",
            weekly_periods=4,
            is_core=True
        )
        self.sub_art = Subject.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="Art & Aesthetics",
            code="ART-9",
            weekly_periods=2,
            is_core=False
        )

        # Assignments
        TeacherAssignment.objects.create(
            school=self.school,
            academic_year=self.ay,
            teacher=self.teacher1,
            subject=self.sub_math,
            section=self.section
        )
        TeacherAssignment.objects.create(
            school=self.school,
            academic_year=self.ay,
            teacher=self.teacher2,
            subject=self.sub_physics,
            section=self.section
        )
        TeacherAssignment.objects.create(
            school=self.school,
            academic_year=self.ay,
            teacher=self.teacher2,
            subject=self.sub_art,
            section=self.section
        )

    def test_department_and_workload_models(self):
        """Test Department creation and TeacherProfile workload attributes."""
        self.assertEqual(self.dept_stem.head_of_department, self.teacher1)
        self.assertEqual(self.teacher1.max_weekly_periods, 24)
        self.assertEqual(self.teacher1.max_daily_periods, 5)

        # Subject attributes
        self.assertEqual(self.sub_math.weekly_periods, 5)
        self.assertTrue(self.sub_math.is_core)
        self.assertFalse(self.sub_art.is_core)

    def test_teacher_workload_service_metrics(self):
        """Test TeacherWorkloadService metrics and capacity evaluation."""
        metrics = TeacherWorkloadService.get_teacher_workload_metrics(
            school=self.school,
            academic_year=self.ay
        )
        self.assertEqual(metrics['total_teachers'], 2)
        # Teacher 1 has Math (5 periods), Teacher 2 has Physics (4) + Art (2) = 6 periods
        self.assertEqual(metrics['total_school_periods'], 11)

        # Capacity check
        cap_check = TeacherWorkloadService.check_teacher_capacity(
            teacher=self.teacher1,
            additional_periods=5
        )
        self.assertFalse(cap_check['would_overload'])

        # Overload test
        cap_check_over = TeacherWorkloadService.check_teacher_capacity(
            teacher=self.teacher1,
            additional_periods=25
        )
        self.assertTrue(cap_check_over['would_overload'])

    def test_automatic_timetable_generator_constraint_satisfaction(self):
        """Test TimetableGeneratorService schedules without any conflicts and respects core morning slots."""
        result = TimetableGeneratorService.generate_timetable(
            school=self.school,
            academic_year=self.ay,
            section_ids=[self.section.id],
            prioritize_core_morning=True
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['slots_created'], 11)  # 5 Math + 4 Physics + 2 Art
        self.assertEqual(result['fulfillment_rate'], 100.0)

        # Verify no section double-booking
        slots = TimetableSlot.objects.filter(school=self.school, section=self.section)
        slot_keys = set()
        for s in slots:
            key = (s.day_of_week, s.period_slot_id)
            self.assertNotIn(key, slot_keys, "Section slot duplicate found!")
            slot_keys.add(key)

        # Verify no teacher double-booking
        for teacher in [self.teacher1, self.teacher2]:
            t_slots = TimetableSlot.objects.filter(school=self.school, teacher=teacher)
            t_keys = set()
            for s in t_slots:
                key = (s.day_of_week, s.period_slot_id)
                self.assertNotIn(key, t_keys, f"Teacher {teacher} duplicate found!")
                t_keys.add(key)

        # Verify Core morning priority: Math (core) should be largely in P1, P2, P3
        math_slots = slots.filter(subject=self.sub_math)
        self.assertEqual(math_slots.count(), 5)
        morning_math = math_slots.filter(period_slot__in=[self.p1, self.p2, self.p3]).count()
        self.assertGreaterEqual(morning_math, 3)

    def test_timetable_slot_pinning_and_preservation(self):
        """Test locked/pinned slots are preserved during automatic regeneration."""
        # Pin a specific slot: Friday Period 5 is Art
        pinned_slot = TimetableSlot.objects.create(
            school=self.school,
            academic_year=self.ay,
            section=self.section,
            subject=self.sub_art,
            teacher=self.teacher2,
            day_of_week=DayOfWeek.FRIDAY.value,
            period_slot=self.p5,
            is_locked=True
        )

        # Regenerate with clear_unlocked=True
        result = TimetableGeneratorService.generate_timetable(
            school=self.school,
            academic_year=self.ay,
            section_ids=[self.section.id],
            clear_unlocked=True
        )

        # The pinned slot should still exist at Friday P5
        self.assertTrue(
            TimetableSlot.objects.filter(
                id=pinned_slot.id,
                is_locked=True,
                day_of_week=DayOfWeek.FRIDAY.value,
                period_slot=self.p5
            ).exists()
        )
        # Total slots should still be 11 (1 pinned + 10 newly created)
        self.assertEqual(TimetableSlot.objects.filter(school=self.school, section=self.section).count(), 11)

    def test_interactive_move_and_swap_api(self):
        """Test moving a slot and cleanly swapping two slots with zero conflicts."""
        self.client.force_login(self.admin)

        slot1 = TimetableSlot.objects.create(
            school=self.school,
            academic_year=self.ay,
            section=self.section,
            subject=self.sub_math,
            teacher=self.teacher1,
            day_of_week=DayOfWeek.MONDAY.value,
            period_slot=self.p1
        )
        slot2 = TimetableSlot.objects.create(
            school=self.school,
            academic_year=self.ay,
            section=self.section,
            subject=self.sub_physics,
            teacher=self.teacher2,
            day_of_week=DayOfWeek.MONDAY.value,
            period_slot=self.p2
        )

        # 1. Swap slot1 and slot2
        url = reverse('timetable:move_or_swap_slot')
        response = self.client.post(url, {
            'source_slot_id': slot1.id,
            'target_day': DayOfWeek.MONDAY.value,
            'target_period_id': self.p2.id,
            'section_id': self.section.id
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        slot1.refresh_from_db()
        slot2.refresh_from_db()
        self.assertEqual(slot1.period_slot, self.p2)
        self.assertEqual(slot2.period_slot, self.p1)

        # 2. Move slot1 to empty cell (Tuesday P3)
        response2 = self.client.post(url, {
            'source_slot_id': slot1.id,
            'target_day': DayOfWeek.TUESDAY.value,
            'target_period_id': self.p3.id,
            'section_id': self.section.id
        })
        self.assertEqual(response2.status_code, 200)
        self.assertTrue(response2.json()['success'])

        slot1.refresh_from_db()
        self.assertEqual(slot1.day_of_week, DayOfWeek.TUESDAY.value)
        self.assertEqual(slot1.period_slot, self.p3)

    def test_toggle_slot_lock_api(self):
        """Test API toggles slot lock state."""
        self.client.force_login(self.admin)

        slot = TimetableSlot.objects.create(
            school=self.school,
            academic_year=self.ay,
            section=self.section,
            subject=self.sub_math,
            teacher=self.teacher1,
            day_of_week=DayOfWeek.MONDAY.value,
            period_slot=self.p1,
            is_locked=False
        )

        url = reverse('timetable:toggle_slot_lock')
        response = self.client.post(url, {'slot_id': slot.id})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_locked'])

        slot.refresh_from_db()
        self.assertTrue(slot.is_locked)

    def test_workload_views_and_capacity_update(self):
        """Test workload dashboard view and capacity limit update."""
        self.client.force_login(self.admin)

        # Dashboard View
        url = reverse('teachers:workload_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teacher Workload & Capacity Hub")
        self.assertContains(response, "Almaz Kebede")

        # Update Capacity Post
        update_url = reverse('teachers:update_capacity')
        post_resp = self.client.post(update_url, {
            'teacher_id': self.teacher1.id,
            'max_weekly_periods': '28',
            'max_daily_periods': '6',
            'department_id': str(self.dept_stem.id)
        })
        self.assertEqual(post_resp.status_code, 302)

        self.teacher1.refresh_from_db()
        self.assertEqual(self.teacher1.max_weekly_periods, 28)
        self.assertEqual(self.teacher1.max_daily_periods, 6)

    def test_export_timetable_views(self):
        """Test Printable HTML and CSV export views."""
        self.client.force_login(self.admin)

        TimetableSlot.objects.create(
            school=self.school,
            academic_year=self.ay,
            section=self.section,
            subject=self.sub_math,
            teacher=self.teacher1,
            day_of_week=DayOfWeek.MONDAY.value,
            period_slot=self.p1
        )

        # Printable View
        url_print = reverse('timetable:export') + f"?section_id={self.section.id}"
        resp_print = self.client.get(url_print)
        self.assertEqual(resp_print.status_code, 200)
        self.assertContains(resp_print, "Official Weekly Class Timetable")
        self.assertContains(resp_print, "Mathematics")

        # CSV View
        url_csv = reverse('timetable:export') + f"?section_id={self.section.id}&format=csv"
        resp_csv = self.client.get(url_csv)
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv['Content-Type'], 'text/csv')
        self.assertIn("Mathematics", resp_csv.content.decode())
