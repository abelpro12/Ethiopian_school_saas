import datetime
import uuid
from decimal import Decimal
from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.schools.models import AdministrativeHierarchy, HierarchyLevel
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile, StudentStatus
from apps.teachers.models import TeacherProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.reports.models import RegionalReportTemplate
from apps.reports.services import EthiopianEducationReportingService


class EthiopianRegionalReportingTest(TestCase):
    def test_administrative_hierarchy_and_regional_report(self):
        uid = uuid.uuid4().hex[:6]

        # 1. Build Administrative Hierarchy (Federal -> Region -> Zone -> Woreda)
        fed = AdministrativeHierarchy.objects.create(name="Federal MoE", level=HierarchyLevel.FEDERAL, code=f"FED-{uid}")
        region = AdministrativeHierarchy.objects.create(name="Oromia Region", level=HierarchyLevel.REGION, parent=fed, code=f"REG-{uid}")
        zone = AdministrativeHierarchy.objects.create(name="Bole Zone", level=HierarchyLevel.ZONE, parent=region, code=f"ZON-{uid}")
        woreda = AdministrativeHierarchy.objects.create(name="Woreda 03", level=HierarchyLevel.WOREDA, parent=zone, code=f"WOR-{uid}")

        self.assertEqual(woreda.parent.parent.name, "Oromia Region")

        # 2. Setup School & Academic Year
        school = School.objects.create(
            name=f"Regional High School {uid}",
            subdomain=f"reg-{uid}",
            code=f"RHS-{uid.upper()}",
            region="Oromia",
            woreda="Woreda 03"
        )
        ay = AcademicYear.objects.create(
            school=school, name="2016 E.C.", ethiopian_year=2016,
            gregorian_start_date=datetime.date(2023,9,12), gregorian_end_date=datetime.date(2024,6,30)
        )

        # 3. Setup Academic Structure & Students
        grade11 = Grade.objects.create(school=school, level=11, name="Grade 11")
        nat_stream = Stream.objects.create(school=school, name="Natural Science", code="NAT")
        section = Section.objects.create(school=school, grade=grade11, stream=nat_stream, name="11-NAT-A", capacity=60)

        teacher_user = User.objects.create_user(username=f"t_{uid}", school=school, role=UserRole.TEACHER)
        TeacherProfile.objects.create(school=school, user=teacher_user, employee_id=f"T-{uid}")

        stu_user = User.objects.create_user(username=f"s_{uid}", school=school, role=UserRole.STUDENT)
        student = StudentProfile.objects.create(
            school=school, user=stu_user, student_id=f"S-{uid}", first_name="Abebe", last_name="Tadesse", gender="M"
        )

        StudentEnrollment.objects.create(
            school=school, academic_year=ay, student=student, grade=grade11, stream=nat_stream, section=section, status=EnrollmentStatus.ACTIVE
        )

        # 4. Generate Regional Report
        template = RegionalReportTemplate.objects.create(
            school=school, name="Oromia Regional Census Template", config_json={'include_all': True}
        )

        report = EthiopianEducationReportingService.generate_standardized_report(school, ay, template)

        self.assertEqual(report['total_students'], 1)
        self.assertEqual(report['gender_breakdown']['male'], 1)
        self.assertEqual(report['teachers_count'], 1)
        self.assertEqual(report['students_by_grade']['Grade 11'], 1)
        self.assertEqual(report['students_by_stream']['Natural Science'], 1)
        self.assertEqual(report['capacity_statistics']['utilization_percentage'], 1.67)

        print("\nETHIOPIAN REGIONAL REPORTING & ADMINISTRATIVE HIERARCHY VERIFIED CLEANLY!")
