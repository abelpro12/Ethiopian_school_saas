from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tenants.models import School

User = get_user_model()


class JWTAuthenticationTestCase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test Academy", code="TAC")
        self.user = User.objects.create_user(
            username="jwt_user",
            password="securepassword123",
            role="TEACHER",
            school=self.school
        )
        self.client = APIClient()

    def test_obtain_token_pair(self):
        """Verify token obtain endpoint returns access and refresh tokens."""
        response = self.client.post('/api/v1/token/', {
            'username': 'jwt_user',
            'password': 'securepassword123'
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_token_refresh(self):
        """Verify refresh endpoint issues a new access token."""
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post('/api/v1/token/refresh/', {
            'refresh': str(refresh)
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

    def test_token_verify(self):
        """Verify token verify endpoint checks access token validity."""
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post('/api/v1/token/verify/', {
            'token': str(refresh.access_token)
        }, format='json')
        self.assertEqual(response.status_code, 200)

    def test_authenticated_api_request_with_jwt(self):
        """Verify API request with Authorization: Bearer <access_token> succeeds."""
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        response = self.client.get('/api/v1/schools/')
        self.assertEqual(response.status_code, 200)
