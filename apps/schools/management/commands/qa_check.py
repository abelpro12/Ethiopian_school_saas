from django.core.management.base import BaseCommand
from django.db import connection
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Grade, Stream, Section, Subject
from apps.enrollment.models import StudentEnrollment
from apps.students.models import StudentProfile
from apps.accounts.models import User

class Command(BaseCommand):
    help = "Runs a lightweight QA Health/Subsystem verification on the current database."

    def check_subsystem(self, name, check_func):
        try:
            result = check_func()
            if result:
                self.stdout.write(self.style.SUCCESS(f"[PASS] {name}"))
            else:
                self.stdout.write(self.style.ERROR(f"[FAIL] {name}"))
                self.has_errors = True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[FAIL] {name} - Exception: {str(e)}"))
            self.has_errors = True

    def handle(self, *args, **options):
        self.has_errors = False
        self.stdout.write("Starting QA Health Verification...")
        
        self.check_subsystem("Database Connection", self.check_db)
        self.check_subsystem("Multi-Tenant Architecture", self.check_tenancy)
        self.check_subsystem("RBAC Integrity", self.check_rbac)
        self.check_subsystem("Academic Structures", self.check_academics)
        self.check_subsystem("Enrollment Constraints", self.check_enrollment)
        
        if self.has_errors:
            self.stdout.write(self.style.ERROR("\nQA Check Failed! Please review the errors above."))
        else:
            self.stdout.write(self.style.SUCCESS("\nQA Check Passed! All subsystems are healthy."))

    def check_db(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            return row[0] == 1

    def check_tenancy(self):
        # Ensure that models derived from TenantModel have the 'school' field
        return hasattr(Grade, 'school') and hasattr(StudentProfile, 'school')

    def check_rbac(self):
        # Verify that all existing users have a valid role assignment if they are active
        invalid_users = User.objects.filter(is_active=True, role__isnull=True).exclude(is_superuser=True).count()
        return invalid_users == 0

    def check_academics(self):
        # Basic check to ensure required core academic models exist in schema
        from django.apps import apps
        AcademicsConfig = apps.get_app_config('academics')
        required_models = ['Grade', 'Stream', 'Subject', 'Section']
        for model in required_models:
            if not AcademicsConfig.get_model(model):
                return False
        return True

    def check_enrollment(self):
        # Check that there are no duplicate enrollments in the same academic year
        from django.db.models import Count
        dupes = StudentEnrollment.objects.values('student', 'academic_year').annotate(count=Count('id')).filter(count__gt=1).count()
        return dupes == 0
