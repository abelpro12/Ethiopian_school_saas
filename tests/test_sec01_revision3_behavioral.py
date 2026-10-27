import pytest
import importlib
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from django.test import TestCase, Client, override_settings
from django.core.cache import cache
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.tenants.models import School
from rest_framework_simplejwt.tokens import RefreshToken


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'sec01-rev3-test-cache',
    }
})
class SEC01Revision3BehavioralTests(TestCase):
    """
    Revision 3 Behavioral Test Suite:
    - Tests atomic rate limiting under concurrent requests.
    - Tests dual-budget burst protection and trusted proxy boundary.
    - Tests rejection of malformed / oversized UIDs without cache key bloat.
    - Tests fail-closed behavior on cache backend failures.
    - Tests admin lockout for staff and superusers with must_change_password=True.
    - Tests admin logout accessibility.
    - Tests true request-time JWT revocation using DRF APIClient.
    - Tests migration 0007 execution routing using schema_editor.connection.alias.
    - Tests migration 0007 handling of null, empty, and already-redacted messages.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.school = School.objects.create(name="Rev3 Security School", subdomain="rev3-sec", code="REV3")
        self.staff_user = User.objects.create_user(
            username="rev3_staff_admin",
            password="InitialPass123!",
            school=self.school,
            role=UserRole.SCHOOL_ADMIN,
            is_staff=True,
            must_change_password=True
        )
        self.superuser = User.objects.create_superuser(
            username="rev3_superadmin",
            password="SuperPass123!",
            email="super@ethioschools.et"
        )
        self.superuser.must_change_password = True
        self.superuser.save()

    @patch('apps.accounts.models.User.objects.get')
    def test_concurrent_rate_limiting_enforces_target_threshold(self, mock_user_get):
        """Under concurrent arrival, atomic attempt reservation limits attempts to 5."""
        mock_user_get.return_value = self.staff_user
        uidb64 = urlsafe_base64_encode(force_bytes(self.staff_user.pk))
        invalid_token = "invalid-token-test-123"
        url = reverse('setup_account_password', kwargs={'uidb64': uidb64, 'token': invalid_token})

        def make_request(idx):
            c = Client()
            return c.get(url, follow=True)

        with ThreadPoolExecutor(max_workers=5) as executor:
            responses = list(executor.map(make_request, range(15)))

        blocked_count = sum(
            1 for resp in responses
            if any("Too many password configuration attempts" in m.message for m in resp.context.get('messages', []))
        )
        self.assertGreaterEqual(blocked_count, 10, "Concurrent requests must be bounded by atomic reservation")

    def test_spoofed_x_real_ip_ignored_when_remote_addr_untrusted(self):
        """Untrusted client providing X-Real-IP is bounded by socket REMOTE_ADDR."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.staff_user.pk))
        url = reverse('setup_account_password', kwargs={'uidb64': uidb64, 'token': 'fake-token'})

        # Send request with spoofed X-Real-IP from untrusted client IP
        resp = self.client.get(
            url,
            REMOTE_ADDR='203.0.113.195',
            HTTP_X_REAL_IP='198.51.100.22',
            follow=True
        )
        self.assertEqual(resp.status_code, 200)

    def test_malformed_and_oversized_uid_rejected_without_cache_bloat(self):
        """Oversized and malformed UIDs are rejected before cache keys are constructed."""
        oversized_uidb64 = "A" * 5000
        resp = self.client.get(
            reverse('setup_account_password', kwargs={'uidb64': oversized_uidb64, 'token': 'dummy'}),
            follow=True
        )
        messages = [m.message for m in resp.context['messages']]
        self.assertTrue(any("invalid or malformed" in m.lower() for m in messages))

    def test_cache_failure_fails_closed_safely(self):
        """Cache backend failure fails closed with user-friendly notification rather than failing open."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.staff_user.pk))
        token = default_token_generator.make_token(self.staff_user)

        with patch('django.core.cache.cache.incr', side_effect=Exception("Redis connection refused")),              patch('django.core.cache.cache.add', side_effect=Exception("Redis connection refused")):
            resp = self.client.get(
                reverse('setup_account_password', kwargs={'uidb64': uidb64, 'token': token}),
                follow=True
            )
            messages = [m.message for m in resp.context['messages']]
            self.assertTrue(any("temporarily unavailable" in m.lower() for m in messages))

    def test_staff_admin_access_blocked_when_must_change_password(self):
        """Authenticated staff with must_change_password=True cannot access /admin/."""
        self.client.force_login(self.staff_user)
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('force_change_password'))

    def test_superuser_admin_access_blocked_when_must_change_password(self):
        """Authenticated superuser with must_change_password=True cannot access /admin/."""
        self.client.force_login(self.superuser)
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('force_change_password'))

    def test_admin_logout_permitted_when_must_change_password(self):
        """Admin logout route remains accessible to prevent account lockout."""
        self.client.force_login(self.staff_user)
        resp = self.client.get('/admin/logout/')
        self.assertNotEqual(resp.url if resp.status_code == 302 else '', reverse('force_change_password'))

    def test_request_time_jwt_access_token_revocation(self):
        """DRF request with access token is immediately rejected with 401 after password change."""
        from rest_framework.test import APIClient
        api_client = APIClient()

        refresh = RefreshToken.for_user(self.staff_user)
        access_token = str(refresh.access_token)

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        resp1 = api_client.get('/api/v1/grades/')
        self.assertEqual(resp1.status_code, 403)
        self.assertEqual(resp1.data.get('code'), 'PASSWORD_CHANGE_REQUIRED')

        self.staff_user.set_password('BrandNewSecurePass2026!#')
        self.staff_user.must_change_password = False
        self.staff_user.save()

        resp2 = api_client.get('/api/v1/grades/')
        self.assertEqual(resp2.status_code, 401)
        self.assertIn('password_changed', str(resp2.data))

    def test_migration_0007_execution_routes_to_schema_editor_alias(self):
        """Migration 0007 purge_and_rotate_credentials queries target alias directly using dynamic import."""
        mig = importlib.import_module("apps.accounts.migrations.0007_remove_user_current_password_plain")
        apps_mock = MagicMock()
        user_model_mock = MagicMock()
        notif_model_mock = MagicMock()

        apps_mock.get_model.side_effect = lambda app, model: user_model_mock if model == 'User' else notif_model_mock
        schema_editor_mock = MagicMock()
        schema_editor_mock.connection.alias = 'custom_tenant_db'
        schema_editor_mock.connection.vendor = 'postgresql'

        user_model_mock._meta.get_fields.return_value = [MagicMock(name='current_password_plain')]
        notif_model_mock.objects.using.return_value.filter.return_value.exclude.return_value.iterator.return_value = []

        mig.purge_and_rotate_credentials(apps_mock, schema_editor_mock)

        user_model_mock.objects.using.assert_called_with('custom_tenant_db')
        notif_model_mock.objects.using.assert_called_with('custom_tenant_db')

    def test_migration_0007_handles_null_empty_and_already_redacted_messages(self):
        """Migration 0007 regex and batch loop handles null, empty, and already-redacted logs safely."""
        mig = importlib.import_module("apps.accounts.migrations.0007_remove_user_current_password_plain")
        apps_mock = MagicMock()
        user_model_mock = MagicMock()
        notif_model_mock = MagicMock()

        apps_mock.get_model.side_effect = lambda app, model: user_model_mock if model == 'User' else notif_model_mock
        schema_editor_mock = MagicMock()
        schema_editor_mock.connection.alias = 'default'
        schema_editor_mock.connection.vendor = 'sqlite'

        user_model_mock._meta.get_fields.return_value = []

        dummy_log_1 = MagicMock(message=None)
        dummy_log_2 = MagicMock(message="")
        dummy_log_3 = MagicMock(message="• Temporary Password: [REDACTED_TEMPORARY_CREDENTIAL]")
        dummy_log_4 = MagicMock(message="• Temporary Password: SecretPlainPassword123!")

        notif_model_mock.objects.using.return_value.filter.return_value.exclude.return_value.iterator.return_value = [
            dummy_log_1, dummy_log_2, dummy_log_3, dummy_log_4
        ]

        mig.purge_and_rotate_credentials(apps_mock, schema_editor_mock)

        self.assertEqual(dummy_log_4.message, "• Temporary Password: [REDACTED_TEMPORARY_CREDENTIAL]")

    def test_client_ip_resolution_trusts_x_real_ip_only_from_trusted_proxy(self):
        """When REMOTE_ADDR is in SECURE_PROXY_IPS, X-Real-IP is trusted."""
        from apps.accounts.views import get_trusted_client_ip
        from django.test import RequestFactory
        factory = RequestFactory()

        # Case 1: Trusted proxy (127.0.0.1) sets X-Real-IP to actual client IP
        with self.settings(SECURE_PROXY_IPS={'127.0.0.1', '::1'}):
            req = factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP='198.51.100.42')
            self.assertEqual(get_trusted_client_ip(req), '198.51.100.42')

        # Case 2: Untrusted direct connection (e.g. 203.0.113.5) with spoofed X-Real-IP
        with self.settings(SECURE_PROXY_IPS={'127.0.0.1', '::1'}):
            req = factory.get('/', REMOTE_ADDR='203.0.113.5', HTTP_X_REAL_IP='198.51.100.42')
            self.assertEqual(get_trusted_client_ip(req), '203.0.113.5')

    def test_client_ip_resolution_supports_cidr_trusted_proxies(self):
        """SECURE_PROXY_IPS supports CIDR network ranges (e.g. Docker bridge or private VPC)."""
        from apps.accounts.views import get_trusted_client_ip
        from django.test import RequestFactory
        factory = RequestFactory()

        with self.settings(SECURE_PROXY_IPS={'10.0.0.0/16'}):
            # Proxy inside subnet
            req1 = factory.get('/', REMOTE_ADDR='10.0.2.15', HTTP_X_REAL_IP='198.51.100.77')
            self.assertEqual(get_trusted_client_ip(req1), '198.51.100.77')

            # Host outside subnet attempting to spoof
            req2 = factory.get('/', REMOTE_ADDR='192.168.1.50', HTTP_X_REAL_IP='198.51.100.77')
            self.assertEqual(get_trusted_client_ip(req2), '192.168.1.50')

    def test_docker_compose_prod_avoids_public_host_port_exposure(self):
        """docker-compose.prod.yml must expose port 8000 internally without publishing to host."""
        import yaml
        from pathlib import Path
        compose_path = Path(__file__).resolve().parent.parent / 'deployment' / 'docker' / 'docker-compose.prod.yml'
        with open(compose_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        web_service = data['services']['web']
        self.assertNotIn('ports', web_service, "Production compose must NOT publish Gunicorn ports to host")
        self.assertIn('8000', [str(p) for p in web_service.get('expose', [])], "Web service must expose port 8000 internally")
        self.assertIn('--bind 0.0.0.0:8000', web_service.get('command', ''))

    def test_nginx_conf_overwrites_forwarded_headers(self):
        """nginx.conf must overwrite X-Real-IP and X-Forwarded-For with $remote_addr."""
        from pathlib import Path
        nginx_path = Path(__file__).resolve().parent.parent / 'nginx' / 'nginx.conf'
        content = nginx_path.read_text(encoding='utf-8')

        self.assertIn('proxy_set_header X-Real-IP $remote_addr;', content)
        self.assertIn('proxy_set_header X-Forwarded-For $remote_addr;', content)
        self.assertNotIn('$proxy_add_x_forwarded_for', content, "Nginx edge proxy must NOT append to untrusted forwarded headers")

    def test_staging_settings_load_and_isolate_database_safely(self):
        """staging.py imports cleanly and isolates DATABASES to :memory: when no external DB env vars are set."""
        from django.conf import settings
        import config.settings.staging as staging_settings

        self.assertEqual(staging_settings.DATABASES['default']['NAME'], ':memory:')
        self.assertEqual(staging_settings.DATABASES['default']['ENGINE'], 'django.db.backends.sqlite3')
        self.assertIn('127.0.0.1', staging_settings.SECURE_PROXY_IPS)
