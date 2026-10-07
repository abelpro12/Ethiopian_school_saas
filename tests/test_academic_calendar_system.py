import datetime
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.schools.models import School
from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    SchoolEvent,
    EventCategory,
    EventType,
    EventStatus,
    TargetAudience
)
from apps.academics.calendar_service import AcademicCalendarService
from apps.audit.models import AuditLog

User = get_user_model()


class AcademicCalendarSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Alpha Academy",
            code="ALPHA",
            calendar_preference="ETHIOPIAN"
        )
        self.admin_user = User.objects.create_superuser(
            username="calendar_admin",
            email="admin@alpha.edu.et",
            password="adminpassword123",
            role="SCHOOL_ADMIN",
            school=self.school
        )

        # Create Academic Year 2017 E.C.
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            is_active=True
        )

        # Create Semesters
        self.sem1 = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            name="Semester 1",
            start_date=datetime.date(2024, 9, 16),
            end_date=datetime.date(2025, 1, 30),
            is_current=True
        )
        self.sem2 = AcademicPeriod.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            name="Semester 2",
            start_date=datetime.date(2025, 2, 10),
            end_date=datetime.date(2025, 6, 30),
            is_current=False
        )

        self.client.force_login(self.admin_user)

    def test_auto_generate_calendar_service(self):
        """Verify automated generation creates full schedule with milestones, exams & holidays."""
        res = AcademicCalendarService.generate_events_for_academic_year(
            academic_year=self.academic_year,
            user=self.admin_user,
            overwrite=False
        )
        self.assertTrue(res['success'])
        self.assertGreater(res['created'], 10)

        # Check milestones created
        year_start_ev = SchoolEvent.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            event_category=EventCategory.ACADEMIC,
            title__icontains="Academic Year Begins"
        ).first()
        self.assertIsNotNone(year_start_ev)
        self.assertTrue(year_start_ev.is_automated)
        self.assertFalse(year_start_ev.is_override)

        # Check Ethiopian holidays created (e.g. Meskel, Enkutatash, Genna, Timket, Adwa)
        adwa_ev = SchoolEvent.objects.filter(
            school=self.school,
            event_category=EventCategory.HOLIDAY,
            title__icontains="Adwa"
        ).first()
        self.assertIsNotNone(adwa_ev)

        # Check Audit log recorded
        audit = AuditLog.objects.filter(
            school=self.school,
            action="ACADEMIC_CALENDAR_GENERATED"
        ).first()
        self.assertIsNotNone(audit)

    def test_manual_override_preservation(self):
        """Verify that when an automated event is modified, is_override=True protects it from overwrite."""
        # Step 1: Generate initial events
        AcademicCalendarService.generate_events_for_academic_year(
            academic_year=self.academic_year,
            user=self.admin_user
        )

        # Step 2: Manually edit an event (e.g., change title or dates)
        ev = SchoolEvent.objects.filter(
            school=self.school,
            academic_year=self.academic_year,
            event_category=EventCategory.EXAMINATION
        ).first()
        self.assertIsNotNone(ev)

        # Update via endpoint or code
        update_url = reverse('calendar_event_update_ajax', kwargs={'event_id': ev.id})
        response = self.client.post(
            update_url,
            data={
                'title': "CUSTOM RESCHEDULED EXAMS",
                'event_category': EventCategory.EXAMINATION,
                'target_audience': TargetAudience.ALL,
                'status': EventStatus.SCHEDULED,
                'start_date': str(ev.start_date + datetime.timedelta(days=2)),
                'end_date': str(ev.end_date) if ev.end_date else '',
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        ev.refresh_from_db()
        self.assertEqual(ev.title, "CUSTOM RESCHEDULED EXAMS")
        self.assertTrue(ev.is_override)

        # Step 3: Trigger auto-generation with overwrite=True
        res2 = AcademicCalendarService.generate_events_for_academic_year(
            academic_year=self.academic_year,
            user=self.admin_user,
            overwrite=True
        )
        self.assertTrue(res2['success'])
        self.assertGreaterEqual(res2['preserved_overrides'], 1)

        # Verify custom event was preserved and not deleted
        ev.refresh_from_db()
        self.assertEqual(ev.title, "CUSTOM RESCHEDULED EXAMS")

    def test_calendar_views_and_json_feed(self):
        """Verify school calendar HTML view and JSON API feed."""
        # Auto-generate some events
        AcademicCalendarService.generate_events_for_academic_year(
            academic_year=self.academic_year,
            user=self.admin_user
        )

        # 1. HTML View
        page_resp = self.client.get(reverse('school_calendar'))
        self.assertEqual(page_resp.status_code, 200)
        self.assertContains(page_resp, "Academic Calendar")
        self.assertContains(page_resp, "schoolCalendar")

        # 2. JSON Endpoint
        json_resp = self.client.get(reverse('calendar_events_json'))
        self.assertEqual(json_resp.status_code, 200)
        events_data = json_resp.json()
        self.assertIsInstance(events_data, list)
        self.assertGreater(len(events_data), 5)

        # Test category filtering in JSON
        filter_resp = self.client.get(f"{reverse('calendar_events_json')}?category={EventCategory.HOLIDAY}")
        self.assertEqual(filter_resp.status_code, 200)
        holiday_events = filter_resp.json()
        for h in holiday_events:
            self.assertEqual(h['category'], EventCategory.HOLIDAY)

    def test_calendar_event_crud_ajax(self):
        """Verify AJAX create, update, and cancel/delete workflows."""
        # 1. Create custom event
        create_url = reverse('calendar_event_create_ajax')
        create_payload = {
            'title': "Annual Science & Tech Fair",
            'event_category': EventCategory.CEREMONY,
            'target_audience': TargetAudience.ALL,
            'status': EventStatus.SCHEDULED,
            'start_date': "2024-11-20",
            'end_date': "2024-11-21",
            'start_time': "09:00:00",
            'end_time': "16:00:00",
            'location': "Main Science Laboratory",
            'description': "Exhibition of student inventions and robotics."
        }
        create_resp = self.client.post(create_url, data=create_payload, content_type='application/json')
        self.assertEqual(create_resp.status_code, 200)
        event_id = create_resp.json()['event_id']

        created_ev = SchoolEvent.objects.get(id=event_id)
        self.assertEqual(created_ev.title, "Annual Science & Tech Fair")
        self.assertFalse(created_ev.is_automated)

        # 2. Cancel event
        cancel_url = reverse('calendar_event_delete_ajax', kwargs={'event_id': event_id})
        cancel_resp = self.client.post(cancel_url, data={'action': 'cancel'}, content_type='application/json')
        self.assertEqual(cancel_resp.status_code, 200)

        created_ev.refresh_from_db()
        self.assertEqual(created_ev.status, EventStatus.CANCELLED)

        # 3. Delete event
        delete_resp = self.client.post(cancel_url, data={'action': 'delete'}, content_type='application/json')
        self.assertEqual(delete_resp.status_code, 200)
        self.assertFalse(SchoolEvent.objects.filter(id=event_id).exists())
