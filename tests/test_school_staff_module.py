import uuid
import datetime
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.teachers.models import StaffProfile, StaffPosition, StaffEmploymentStatus, StaffDocument, StaffDocumentType
from apps.schools.search import CentralizedSearchEngine


class SchoolStaffModuleTest(TestCase):
    def test_non_teaching_staff_creation_documents_and_search(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"Staff Academy {uid}", subdomain=f"staff-{uid}", code=f"SAC-{uid.upper()}")
        user = User.objects.create_user(username=f"librarian_{uid}", school=school, role=UserRole.SCHOOL_ADMIN)
        admin = User.objects.create_user(username=f"admin_{uid}", school=school, role=UserRole.SCHOOL_ADMIN)

        # 1. Create Non-Teaching Staff Profile (Librarian)
        staff = StaffProfile.objects.create(
            school=school,
            user=user,
            employee_id=f"STAFF-{uid}",
            department="Library Services",
            position=StaffPosition.LIBRARIAN,
            hire_date=datetime.date(2023, 9, 1),
            employment_status=StaffEmploymentStatus.ACTIVE,
            phone="+251911998877",
            email=f"librarian_{uid}@school.edu.et"
        )

        self.assertEqual(staff.position, StaffPosition.LIBRARIAN)
        self.assertEqual(staff.department, "Library Services")

        # 2. Upload Secure Staff HR Document
        doc_file = SimpleUploadedFile("contract.pdf", b"PDF contract content", content_type="application/pdf")
        staff_doc = StaffDocument.objects.create(
            school=school,
            staff=staff,
            document_type=StaffDocumentType.CONTRACT,
            title="Annual Employment Contract 2016 E.C.",
            file=doc_file,
            uploaded_by=admin
        )

        self.assertEqual(staff_doc.document_type, StaffDocumentType.CONTRACT)
        self.assertTrue('contract' in staff_doc.file.name)

        # 3. Search Engine Integration
        search_res = CentralizedSearchEngine.search(school, f"STAFF-{uid}")
        self.assertTrue(any(staff.employee_id in s['subtitle'] for s in search_res['staff']))

        search_pos = CentralizedSearchEngine.search(school, "Librarian")
        self.assertTrue(any(staff.employee_id in s['subtitle'] for s in search_pos['staff']))

        print("\nSCHOOL STAFF MODULE & HR DOCUMENTS VERIFIED CLEANLY!")
