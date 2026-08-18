import datetime
from django.test import TestCase, Client
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject, PeriodSlot, TimetableSlot, DayOfWeek
from apps.subscriptions.models import SubscriptionPlan, SchoolSubscription, PlanTier, TenantUsageMeter
from apps.documents.models import SchoolDocument, DocumentCategory
from django.core.files.uploadedfile import SimpleUploadedFile


class NewSubsystemsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(name="Addis Secondary", subdomain="addis-sec", code="SEC-01")

        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2016 E.C.",
            ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023, 9, 12),
            gregorian_end_date=datetime.date(2024, 6, 30)
        )
        self.grade = Grade.objects.create(school=self.school, level=9, name="Grade 9")
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="A")
        self.subject = Subject.objects.create(school=self.school, code="ENG-09", name="English", grade=self.grade, stream=self.stream)

    def test_timetable_creation(self):
        period = PeriodSlot.objects.create(
            school=self.school,
            name="Period 1",
            start_time=datetime.time(8, 30),
            end_time=datetime.time(9, 15)
        )
        slot = TimetableSlot.objects.create(
            school=self.school,
            section=self.section,
            subject=self.subject,
            day_of_week=DayOfWeek.MONDAY,
            period_slot=period,
            room="Room 101"
        )
        self.assertEqual(slot.room, "Room 101")
        self.assertEqual(slot.day_of_week, DayOfWeek.MONDAY)

    def test_subscription_and_usage_metering(self):
        plan = SubscriptionPlan.objects.create(
            name="Basic Plan",
            tier=PlanTier.BASIC,
            max_students=500,
            max_teachers=30,
            price_per_year_etb=15000.00
        )
        sub = SchoolSubscription.objects.create(
            school=self.school,
            plan=plan,
            end_date=datetime.date(2025, 9, 12)
        )
        meter = TenantUsageMeter.objects.create(
            school=self.school,
            current_students_count=120,
            current_teachers_count=15
        )
        self.assertEqual(sub.plan.max_students, 500)
        self.assertEqual(meter.current_students_count, 120)

    def test_document_management(self):
        dummy_file = SimpleUploadedFile("transcript.pdf", b"PDF file content sample", content_type="application/pdf")
        doc = SchoolDocument.objects.create(
            school=self.school,
            title="Grade 8 Official Transcript",
            category=DocumentCategory.STUDENT_TRANSCRIPT,
            file=dummy_file
        )
        self.assertEqual(doc.category, DocumentCategory.STUDENT_TRANSCRIPT)
        self.assertIn("transcript", doc.file.name)

    def test_health_check_monitoring_endpoint(self):
        res = self.client.get('/health/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['database'], 'healthy')
