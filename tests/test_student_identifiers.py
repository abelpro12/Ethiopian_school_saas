import uuid
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.students.models import StudentProfile
from apps.schools.search import CentralizedSearchEngine


class StudentIdentifiersTest(TestCase):
    def test_student_profile_separate_identifiers_and_uuid_pk(self):
        uid = uuid.uuid4().hex[:6]
        school = School.objects.create(name=f"ID Academy {uid}", subdomain=f"id-{uid}", code=f"IDA-{uid.upper()}")
        user = User.objects.create_user(username=f"student_{uid}", school=school, role=UserRole.STUDENT)

        student = StudentProfile.objects.create(
            school=school,
            user=user,
            student_id=f"AIA-STU-{uid}",
            admission_number=f"ADM-2016-{uid}",
            roll_number="12",
            national_id=f"ETH-NAT-{uid}",
            previous_school_id=f"OLD-SCH-{uid}",
            first_name="Taye",
            middle_name="Bikila",
            last_name="Tadesse",
            gender="M"
        )

        # 1. Primary Key is UUID (never an external identifier string)
        self.assertIsInstance(student.id, uuid.UUID)
        self.assertNotEqual(str(student.id), student.student_id)
        self.assertNotEqual(str(student.id), student.admission_number)

        # 2. Separate non-PK identifiers match expectations
        self.assertEqual(student.student_id, f"AIA-STU-{uid}")
        self.assertEqual(student.admission_number, f"ADM-2016-{uid}")
        self.assertEqual(student.roll_number, "12")
        self.assertEqual(student.national_id, f"ETH-NAT-{uid}")
        self.assertEqual(student.previous_school_id, f"OLD-SCH-{uid}")

        # 3. Search Engine queries by admission_number and national_id
        res_adm = CentralizedSearchEngine.search(school, f"ADM-2016-{uid}")
        self.assertIn(student.full_name, [s['title'] for s in res_adm['students']])

        res_nat = CentralizedSearchEngine.search(school, f"ETH-NAT-{uid}")
        self.assertIn(student.full_name, [s['title'] for s in res_nat['students']])

        print("\nSTUDENT IDENTIFIERS & INTERNAL UUID PK VERIFIED CLEANLY!")
