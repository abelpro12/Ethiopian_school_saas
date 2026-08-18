import io
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Grade
from apps.students.models import StudentProfile

User = get_user_model()


class BulkStudentImportTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Model School", code="MS", subdomain="model", status="ACTIVE")
        self.admin = User.objects.create_user(
            username="school_admin",
            password="password123",
            role="SCHOOL_ADMIN",
            school=self.school
        )
        self.ay = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            is_active=True
        )
        self.grade = Grade.objects.create(school=self.school, level=9)
        from apps.academics.models import Section, Stream
        self.stream = Stream.objects.create(school=self.school, name="General")
        self.section = Section.objects.create(school=self.school, grade=self.grade, stream=self.stream, name="A")

        self.client = Client()
        self.client.force_login(self.admin)

    def test_bulk_import_template_download(self):
        """Verify CSV template download view returns CSV file with BOM."""
        url = reverse('students:bulk_import_template')
        response = self.client.get(url, HTTP_HOST="model.testserver")
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('first_name,middle_name', response.content.decode('utf-8-sig'))

    def test_bulk_import_students_success(self):
        """Verify successful CSV upload creates StudentProfile and User with Student ID."""
        url = reverse('students:bulk_import')
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_data = (
            "first_name,middle_name,last_name,gender,date_of_birth,phone,region,woreda,kebele,national_id,admission_number,grade_level,section_name,amharic_name\n"
            "Abebe,Girma,Tadesse,M,2007-03-15,+251911234567,Addis Ababa,Bole,07,,ADM-001,9,A,አበበ ጊርማ\n"
            "Tigist,Haile,Belay,F,2007-05-20,+251911234568,Addis Ababa,Yeka,03,,ADM-002,9,A,ትግስት ኃይሌ\n"
        )
        file_obj = SimpleUploadedFile("students.csv", csv_data.encode('utf-8'), content_type="text/csv")

        response = self.client.post(url, {
            'csv_file': file_obj,
            'academic_year': str(self.ay.id),
            'default_grade': str(self.grade.id),
        }, HTTP_HOST="model.testserver", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 2)

        st1 = StudentProfile.objects.get(first_name="Abebe")
        self.assertEqual(st1.middle_name, "Girma")
        self.assertEqual(st1.gender, "M")
        self.assertEqual(st1.amharic_name, "አበበ ጊርማ")
        self.assertTrue(st1.student_id.startswith("MS-STU-"))

    def test_bulk_import_invalid_gender_error(self):
        """Verify row with invalid gender reports error without crashing."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        url = reverse('students:bulk_import')
        csv_data = (
            "first_name,middle_name,last_name,gender\n"
            "Kassahun,Kebede,Worku,X\n"
        )
        file_obj = SimpleUploadedFile("invalid.csv", csv_data.encode('utf-8'), content_type="text/csv")

        response = self.client.post(url, {
            'csv_file': file_obj,
            'academic_year': str(self.ay.id),
        }, HTTP_HOST="model.testserver", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 0)
