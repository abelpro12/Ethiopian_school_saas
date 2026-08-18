from django.test import TestCase
from apps.tenants.models import School
from apps.accounts.models import User


class ModelsTest(TestCase):
    def test_school_model_creation(self):
        school = School.objects.create(name="Unit Test School", code="UTS01", subdomain="uts01")
        self.assertEqual(str(school), "Unit Test School (UTS01)"
)
