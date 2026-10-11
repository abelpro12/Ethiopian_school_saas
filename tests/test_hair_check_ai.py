import json
import datetime
from io import BytesIO
from PIL import Image
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Section, Stream
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.communication.models import TelegramAccountLink
from apps.discipline.models import (
    HairCheckRecord, HairCheckStatus, DisciplinaryIncident,
    IncidentCategory, IncidentSeverity
)
from apps.discipline.hair_ai_service import HairCheckAIService
from apps.discipline.hair_notification_service import HairNotificationService


class HairCheckAITestCase(TestCase):
    """
    Test suite for AI Hair Check & Parent Notification System.
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Addis Future Academy",
            code="AFA",
            calendar_preference="ETHIOPIAN"
        )

        self.admin = User.objects.create_superuser(
            username="admin_hair",
            email="admin@addisfuture.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 6, 30),
            is_active=True
        )

        self.grade = Grade.objects.create(
            school=self.school,
            name="Grade 10",
            level=10,
            stream_type="GEN"
        )

        self.stream = Stream.objects.create(
            school=self.school,
            name="General",
            code="GEN"
        )

        self.section = Section.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="A"
        )


        # Student User & Profile
        self.student_user = User.objects.create_user(
            username="stu_abebe",
            first_name="Abebe",
            last_name="Kebede",
            role=UserRole.STUDENT,
            school=self.school
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            school=self.school,
            student_id="AFA-2024-001",
            first_name="Abebe",
            last_name="Kebede",
            gender="M",
            date_of_birth=datetime.date(2008, 5, 12)
        )

        StudentEnrollment.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            student=self.student,
            grade=self.grade,
            section=self.section,
            stream=self.stream
        )

        # Parent User & Profile
        self.parent_user = User.objects.create_user(
            username="parent_kebede",
            first_name="Kebede",
            last_name="Tadesse",
            email="kebede@gmail.com",
            phone="0911234567",
            role=UserRole.PARENT,
            school=self.school
        )
        self.parent = ParentProfile.objects.create(
            user=self.parent_user,
            school=self.school,
            phone="0911234567"
        )


        GuardianRelationship.objects.create(
            school=self.school,
            student=self.student,
            parent=self.parent,
            is_primary=True
        )

        # Telegram Account Link
        TelegramAccountLink.objects.create(
            school=self.school,
            user=self.parent_user,
            telegram_chat_id="987654321",
            is_verified=True
        )

        # Create a sample test image in memory
        im = Image.new('RGB', (160, 160), color=(40, 30, 20))
        buf = BytesIO()
        im.save(buf, format='JPEG')
        self.sample_image_bytes = buf.getvalue()

    def _get_test_uploaded_file(self):
        return SimpleUploadedFile("test_haircut.jpg", self.sample_image_bytes, content_type="image/jpeg")

    def test_hair_ai_service_analysis(self):
        """Verify HairCheckAIService returns valid structured analysis."""
        analysis = HairCheckAIService.analyze_hair_image(self.sample_image_bytes, student_name="Abebe Kebede")
        self.assertIn('status', analysis)
        self.assertIn(analysis['status'], ['ALLOWED', 'PROHIBITED'])
        self.assertIn('confidence', analysis)
        self.assertIn('recommendation', analysis)
        self.assertIn('violations', analysis)
        self.assertIn('ai_engine', analysis)

    def test_hair_notification_service_contacts(self):
        """Verify contact discovery across Telegram, SMS, and Email."""
        contacts = HairNotificationService.get_parent_contacts(self.student, self.school)
        self.assertEqual(len(contacts), 1)
        c = contacts[0]
        self.assertEqual(c['phone'], '0911234567')
        self.assertEqual(c['email'], 'kebede@gmail.com')
        self.assertEqual(c['telegram_chat_id'], '987654321')
        self.assertTrue(c['is_primary'])


    def test_hair_notification_dispatch_and_incident_creation(self):
        """Verify dispatching a prohibited hair violation creates disciplinary incident and logs."""
        hair_record = HairCheckRecord.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            student=self.student,
            checked_by=self.admin,
            status=HairCheckStatus.PROHIBITED,
            confidence=92,
            violations=["High skin fade on sides & back"],
            recommendation="Trim evenly to school standard cut.",
            deadline_date=datetime.date.today() + datetime.timedelta(days=2)
        )

        dispatch_res = HairNotificationService.dispatch_hair_notice(
            hair_record=hair_record,
            channels=['TELEGRAM', 'SMS', 'EMAIL'],
            custom_note="Please fix before Monday morning assembly.",
            operator_user=self.admin
        )

        self.assertTrue(dispatch_res['success'])
        self.assertGreaterEqual(dispatch_res['telegram_sent'] + dispatch_res['sms_sent'] + dispatch_res['email_sent'], 1)

        # Refresh hair record
        hair_record.refresh_from_db()
        self.assertTrue(hair_record.parent_notified)
        self.assertIn('TELEGRAM', hair_record.notification_channels)
        self.assertIsNotNone(hair_record.linked_incident)

        # Verify DisciplinaryIncident created
        incident = hair_record.linked_incident
        self.assertEqual(incident.category, IncidentCategory.DRESS_CODE)
        self.assertTrue(incident.parent_notified)
        self.assertIn(self.student, incident.students_involved.all())

    def test_scanner_view_authorized(self):
        """Verify scanner page renders 200 for authenticated staff."""
        self.client.force_login(self.admin)
        url = reverse('discipline:hair_check_scanner')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Hair Grooming Scanner")
        self.assertContains(response, "Abebe Kebede")

    def test_analyze_api(self):
        """Verify analyze API accepts photo and returns analysis."""
        self.client.force_login(self.admin)
        url = reverse('discipline:hair_check_analyze_api')
        photo = self._get_test_uploaded_file()

        response = self.client.post(url, {
            'photo': photo,
            'student_id': str(self.student.id)
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('analysis', data)
        self.assertEqual(data['student']['full_name'], 'Abebe Kebede')
        self.assertTrue(data['student']['has_telegram'])

    def test_dispatch_api(self):
        """Verify dispatch API saves record and sends parent notice."""
        self.client.force_login(self.admin)
        url = reverse('discipline:hair_check_dispatch_api')
        photo = self._get_test_uploaded_file()

        response = self.client.post(url, {
            'student_id': str(self.student.id),
            'photo': photo,
            'status': 'PROHIBITED',
            'confidence': 94,
            'violations': json.dumps(["Skin fade on sides/back", "Carved line"]),
            'recommendation': "Trim evenly to standard cut.",
            'channels': 'TELEGRAM,SMS,EMAIL',
            'deadline_days': '2',
            'custom_note': "Urgent notification"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('record_id', data)

        record = HairCheckRecord.objects.get(id=data['record_id'])
        self.assertEqual(record.status, HairCheckStatus.PROHIBITED)
        self.assertTrue(record.parent_notified)
        self.assertEqual(len(record.violations), 2)

    def test_history_view(self):
        """Verify history view renders audit records."""
        HairCheckRecord.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            student=self.student,
            checked_by=self.admin,
            status=HairCheckStatus.ALLOWED,
            confidence=95,
            violations=[]
        )
        self.client.force_login(self.admin)
        url = reverse('discipline:hair_check_history')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hair Grooming Inspection Logs")
        self.assertContains(response, "Abebe Kebede")
