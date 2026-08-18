from django.test import TestCase
from apps.tenants.models import School


class ViewsTest(TestCase):
    def test_health_check_endpoint(self):
        school = School.objects.create(name="Health School", code="HS01", subdomain="hs01")
        self.assertTrue(school.is_active)
