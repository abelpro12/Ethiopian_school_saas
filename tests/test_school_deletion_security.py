"""
Tests for Secure School Deletion with Super Admin Password Verification.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from apps.tenants.models import School
from apps.accounts.models import User, UserRole


@pytest.mark.django_db
class TestSchoolDeletionSecurity:

    def setup_method(self):
        self.superadmin_password = "SuperAdminPassword123!"
        self.superadmin = User.objects.create_superuser(
            username="super_admin_tester",
            email="superadmin@platform.et",
            password=self.superadmin_password,
            role=UserRole.SUPER_ADMIN
        )
        self.school = School.objects.create(
            name="Target Delete Academy",
            code="TDA01",
            subdomain="targetdelete"
        )

    def test_delete_school_wrong_password_fails(self, client):
        """Verifies school deletion fails if wrong super admin password is provided."""
        client.force_login(self.superadmin)
        url = reverse('platform:school_action', kwargs={'school_id': self.school.id})

        response = client.post(url, {
            'action': 'delete',
            'password': 'WrongPassword123'
        }, follow=True)

        assert response.status_code == status.HTTP_200_OK
        # Check school still exists in DB
        assert School.objects.filter(id=self.school.id).exists()

    def test_delete_school_correct_password_succeeds(self, client):
        """Verifies school deletion succeeds when correct super admin password is provided."""
        client.force_login(self.superadmin)
        url = reverse('platform:school_action', kwargs={'school_id': self.school.id})

        response = client.post(url, {
            'action': 'delete',
            'password': self.superadmin_password
        }, follow=True)

        assert response.status_code == status.HTTP_200_OK
        # Check school was permanently deleted from DB
        assert not School.objects.filter(id=self.school.id).exists()

    def test_delete_school_with_school_action_type_param(self, client):
        """Verifies school deletion succeeds when school_action_type parameter is sent."""
        client.force_login(self.superadmin)
        url = reverse('platform:school_action', kwargs={'school_id': self.school.id})

        response = client.post(url, {
            'school_action_type': 'delete',
            'password': self.superadmin_password
        }, follow=True)

        assert response.status_code == status.HTTP_200_OK
        assert not School.objects.filter(id=self.school.id).exists()
