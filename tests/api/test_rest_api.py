from django.test import TestCase


class RestApiTest(TestCase):
    def test_api_v1_structure(self):
        endpoint = "/api/v1/schools/"
        self.assertTrue(endpoint.startswith("/api/v1/"))
