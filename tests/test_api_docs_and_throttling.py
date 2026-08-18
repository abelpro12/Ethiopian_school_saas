"""
Tests for API Documentation (drf-spectacular), Rate Throttling, and Authentication Security.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.conf import settings


@pytest.mark.django_db
class TestAPIDocumentationAndSecurity:

    def setup_method(self):
        self.client = APIClient()

    def test_openapi_schema_endpoint(self):
        """Verifies /api/v1/schema/ returns OpenAPI 3.0 JSON schema."""
        url = reverse("schema")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "openapi" in response.data or "openapi" in str(response.content)

    def test_swagger_ui_endpoint(self):
        """Verifies /api/v1/docs/ renders Swagger UI HTML page."""
        url = reverse("swagger-ui")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "swagger-ui" in response.content.decode("utf-8").lower()

    def test_redoc_ui_endpoint(self):
        """Verifies /api/v1/redoc/ renders Redoc UI HTML page."""
        url = reverse("redoc")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "redoc" in response.content.decode("utf-8").lower()

    def test_basic_auth_disabled_in_settings(self):
        """Ensures BasicAuthentication is NOT in DEFAULT_AUTHENTICATION_CLASSES."""
        auth_classes = settings.REST_FRAMEWORK.get("DEFAULT_AUTHENTICATION_CLASSES", [])
        assert "rest_framework.authentication.BasicAuthentication" not in auth_classes

    def test_drf_throttling_configured(self):
        """Ensures DRF throttling classes and rates are configured."""
        throttle_classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])
        assert len(throttle_classes) > 0
        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        assert "anon" in rates
        assert "user" in rates
