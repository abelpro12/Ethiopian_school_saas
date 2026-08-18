import io
import uuid
from PIL import Image
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.students.models import StudentProfile, StudentPhotoHistory, StudentDemographics
from apps.academics.models import AcademicYear
from utils.photo_processor import PhotoProcessingService
from apps.reports.services import EthiopianEducationReportingService


class PhotoAndDemographicsTest(TestCase):
    def test_student_photo_management_and_history(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"Photo Academy {uid}", subdomain=f"photo-{uid}", code=f"PAC-{uid.upper()}")
        user = User.objects.create_user(username=f"student_{uid}", school=school, role=UserRole.STUDENT)
        admin = User.objects.create_user(username=f"admin_{uid}", school=school, role=UserRole.SCHOOL_ADMIN)

        student = StudentProfile.objects.create(
            school=school, user=user, student_id=f"STU-{uid}", first_name="Tadesse", last_name="Bikila", gender="M"
        )

        # Create dummy image in memory using Pillow
        img = Image.new('RGB', (600, 600), color='blue')
        img_io = io.BytesIO()
        img.save(img_io, format='JPEG')
        img_file = SimpleUploadedFile(f"test_{uid}.jpg", img_io.getvalue(), content_type='image/jpeg')

        # 1. Update Student Photo using PhotoProcessingService
        PhotoProcessingService.update_student_photo(student, img_file, uploaded_by=admin)

        student.refresh_from_db()
        self.assertTrue(student.photo.name.endswith('.jpg'))
        self.assertTrue(student.thumbnail.name.endswith('.jpg'))

        # Check Photo History
        history = StudentPhotoHistory.objects.filter(school=school, student=student)
        self.assertEqual(history.count(), 1)
        self.assertTrue(history.first().is_active)

        # 2. Upload replacement photo
        img2 = Image.new('RGB', (800, 800), color='red')
        img2_io = io.BytesIO()
        img2.save(img2_io, format='JPEG')
        img2_file = SimpleUploadedFile(f"test2_{uid}.jpg", img2_io.getvalue(), content_type='image/jpeg')

        PhotoProcessingService.update_student_photo(student, img2_file, uploaded_by=admin)

        # Verify photo history holds both photos (1 inactive, 1 active)
        history_updated = StudentPhotoHistory.objects.filter(school=school, student=student)
        self.assertEqual(history_updated.count(), 2)
        self.assertEqual(history_updated.filter(is_active=True).count(), 1)
        self.assertEqual(history_updated.filter(is_active=False).count(), 1)

    def test_configurable_demographic_reporting(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"Demo School {uid}", subdomain=f"demo-{uid}", code=f"DEM-{uid.upper()}")
        user = User.objects.create_user(username=f"student_{uid}", school=school)
        student = StudentProfile.objects.create(school=school, user=user, student_id=f"STU-{uid}", first_name="Abebe", last_name="Kebede", gender="M")

        # Create Custom Demographics
        StudentDemographics.objects.create(
            school=school,
            student=student,
            gender_identity="Male",
            custom_demographics={
                'primary_language': 'Afaan Oromoo',
                'disability_support': 'None',
                'regional_origin': 'Oromia'
            }
        )

        ay = AcademicYear.objects.create(
            school=school, name="2016 E.C.", gregorian_start_date="2023-09-12", gregorian_end_date="2024-06-30"
        )

        report = EthiopianEducationReportingService.generate_standardized_report(school, ay)
        self.assertIn('custom_demographics_summary', report)
        self.assertEqual(report['custom_demographics_summary']['primary_language']['Afaan Oromoo'], 1)
        self.assertEqual(report['custom_demographics_summary']['regional_origin']['Oromia'], 1)

        print("\nSTUDENT PHOTO MANAGEMENT & CONFIGURABLE DEMOGRAPHICS TEST PASSED PERFECTLY!")
