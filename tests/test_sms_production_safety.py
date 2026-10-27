"""
ETHIOSCHOOL ERP - Production SMS False-Success Remediation Test Suite
Verifies that unconfigured or failing SMS providers in production fail closed,
never report false successes, never log credentials, record FAILED in NotificationLog,
and that development/test simulation functions only where explicitly intended.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from apps.schools.models import School
from apps.communication.models import NotificationLog, NotificationChannel
from apps.notifications.services import (
    NotificationService,
    SMSEthiopiaProvider,
    HahuSMSProvider,
    AfroMessageSMSProvider,
    MockSMSProvider,
    is_sms_simulation_allowed,
)
from apps.notifications.channels.sms import SMSNotificationChannel

User = get_user_model()


class SMSProductionSafetyTests(TestCase):
    def setUp(self):
        NotificationService.set_sms_provider(None)
        self.school = School.objects.create(
            name="Seattle Academy Addis",
            code="SEA01",
            subdomain="seattle-academy-addis"
        )
        self.user = User.objects.create_user(
            username="testparent_sms_sec",
            email="parent_sms_sec@example.com",
            password="AComplexPassword123!"
        )

    def tearDown(self):
        NotificationService.set_sms_provider(None)

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.1: Production with missing or invalid credentials (Fails Closed)
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_smsethiopia_production_missing_credentials_fails_closed(self, mock_post):
        """Missing SMSEthiopia credentials in production must fail closed without making HTTP calls."""
        provider = SMSEthiopiaProvider(api_key=None)
        sent = provider.send_sms("0911223344", "Production test alert")
        self.assertFalse(sent)
        mock_post.assert_not_called()
        self.assertIn("missing or unconfigured in production", provider.last_error)
        self.assertFalse(provider.last_details.get("simulated", False))

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_smsethiopia_production_dummy_key_fails_closed(self, mock_post):
        """Placeholder keys ('test_key', 'your_key_here') in production must fail closed."""
        for dummy in ("test_key", "your_key_here"):
            provider = SMSEthiopiaProvider(api_key=dummy)
            sent = provider.send_sms("0911223344", "Production test alert")
            self.assertFalse(sent)
            mock_post.assert_not_called()
            self.assertIn("missing or unconfigured in production", provider.last_error)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_hahu_production_missing_credentials_fails_closed(self, mock_post):
        """Missing Hahu credentials in production must fail closed without making HTTP calls."""
        provider = HahuSMSProvider(api_secret=None, device_id=None)
        sent = provider.send_sms("0911223344", "Production test alert")
        self.assertFalse(sent)
        mock_post.assert_not_called()
        self.assertIn("missing or unconfigured in production", provider.last_error)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_afromessage_production_missing_credentials_fails_closed(self, mock_post):
        """Missing AfroMessage credentials in production must fail closed without making HTTP calls."""
        provider = AfroMessageSMSProvider(api_key=None)
        sent = provider.send_sms("0911223344", "Production test alert")
        self.assertFalse(sent)
        mock_post.assert_not_called()
        self.assertIn("missing or unconfigured in production", provider.last_error)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    def test_mock_sms_provider_production_fails_closed(self):
        """MockSMSProvider invoked in production must fail closed and record failure reason."""
        provider = MockSMSProvider()
        sent = provider.send_sms("0911223344", "Production test alert")
        self.assertFalse(sent)
        self.assertIn("unconfigured in production", provider.last_error)
        self.assertFalse(provider.last_details.get("simulated", False))

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.2: Development/Test Simulation
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(DEBUG=True, SMS_SIMULATION_MODE=True)
    @patch("requests.post")
    def test_development_simulation_mode_explicitly_marked(self, mock_post):
        """In explicit simulation mode, missing credentials safely simulates dispatch."""
        provider = SMSEthiopiaProvider(api_key=None)
        sent = provider.send_sms("0911223344", "Simulation alert")
        self.assertTrue(sent)
        mock_post.assert_not_called()
        self.assertTrue(provider.last_details.get("simulated"))

    @override_settings(DEBUG=False, TESTING=True, SMS_SIMULATION_MODE=True)
    @patch("requests.post")
    def test_test_simulation_mode_explicitly_marked(self, mock_post):
        """In testing with explicit SMS_SIMULATION_MODE, simulation succeeds."""
        provider = HahuSMSProvider(api_secret=None, device_id=None)
        sent = provider.send_sms("0911223344", "Simulation alert")
        self.assertTrue(sent)
        mock_post.assert_not_called()
        self.assertTrue(provider.last_details.get("simulated"))

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.3: Actual provider failure & Documented Response Semantics
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_actual_provider_http_500_failure(self, mock_post):
        """HTTP error codes from gateway must return False and capture error text."""
        provider = SMSEthiopiaProvider(api_key="mock_live_sec_key_778899")
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.text = "Bad Gateway from Telecommunications Proxy"
        mock_resp.json.side_effect = Exception("Not JSON")
        mock_post.return_value = mock_resp

        sent = provider.send_sms("0911223344", "Failure alert")
        self.assertFalse(sent)
        self.assertIn("502", provider.last_error)
        self.assertIn("Bad Gateway", provider.last_error)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_http_200_with_error_payload_fails_documented_semantics(self, mock_post):
        """HTTP 200 containing error payload (e.g. error 10006 SenderID not approved) must fail."""
        provider = SMSEthiopiaProvider(api_key="mock_live_sec_key_778899")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"error_code": 10006, "error_message": "SenderID not approved"}'
        mock_resp.json.return_value = {"error_code": 10006, "error_message": "SenderID not approved"}
        mock_post.return_value = mock_resp

        sent = provider.send_sms("0911223344", "Semantic error test")
        self.assertFalse(sent)
        self.assertIn("Sender ID is not approved yet", provider.last_error)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_afromessage_http_200_with_error_payload_fails(self, mock_post):
        """AfroMessage HTTP 200 with error payload must fail."""
        provider = AfroMessageSMSProvider(api_key="mock_afro_sec_key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"acknowledge": "error", "response": {"message": "Insufficient balance"}}'
        mock_resp.json.return_value = {"acknowledge": "error", "response": {"message": "Insufficient balance"}}
        mock_post.return_value = mock_resp

        sent = provider.send_sms("0911223344", "Balance test")
        self.assertFalse(sent)
        self.assertIn("Insufficient balance", provider.last_error)

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.4: Existing Successful Mocked-Provider Behavior
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_existing_successful_mocked_provider_behavior(self, mock_post):
        """When provider succeeds with valid HTTP 200/201 and success payload, return True."""
        provider = SMSEthiopiaProvider(api_key="mock_live_sec_key_778899")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success", "message": "Dispatched to operator"}'
        mock_resp.json.return_value = {"status": "success", "message": "Dispatched to operator"}
        mock_post.return_value = mock_resp

        sent = provider.send_sms("0911223344", "Successful SMS message")
        self.assertTrue(sent)
        self.assertTrue(provider.last_details.get("direct_delivered"))

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.5: Correct NotificationLog Status Handling
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(
        DEBUG=False,
        TESTING=False,
        SMS_SIMULATION_MODE=False,
        HAHU_API_SECRET=None,
        HAHU_DEVICE_ID=None,
        SMSETHIOPIA_API_KEY=None,
        AFROMESSAGE_API_KEY=None
    )
    def test_notification_log_records_failed_status_when_no_provider_succeeds(self):
        """In production with unconfigured SMS gateways, NotificationLog MUST record FAILED, not SENT."""
        NotificationService.set_sms_provider(None)

        sent = NotificationService.send_notification(
            school=self.school,
            recipient_user=self.user,
            channel=NotificationChannel.SMS,
            message="Tuition payment overdue for student Abebe",
            phone_number="0911223344"
        )
        self.assertFalse(sent)

        # Inspect NotificationLog record
        log = NotificationLog.objects.filter(recipient=self.user, channel=NotificationChannel.SMS).latest("sent_at")
        self.assertEqual(log.status, "FAILED")
        self.assertNotEqual(log.status, "SENT")
        self.assertIsNotNone(log.failure_reason)
        self.assertIn("unconfigured in production", log.failure_reason)

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    def test_notification_service_send_sms_and_channel_delegation(self):
        """NotificationService.send_sms and SMSNotificationChannel.send_sms fail closed in production."""
        NotificationService.set_sms_provider(None)

        # Direct NotificationService.send_sms
        sent_direct = NotificationService.send_sms("0911223344", "Direct test message")
        self.assertFalse(sent_direct)
        self.assertIn("unconfigured in production", NotificationService.get_last_failure_reason())

        # Channel delegation
        sent_channel = SMSNotificationChannel.send_sms("0911223344", "Channel test message")
        self.assertFalse(sent_channel)
        self.assertIn("unconfigured in production", NotificationService.get_last_failure_reason())

    # ──────────────────────────────────────────────────────────────────────────
    # Task 4.6: Security - Never log credentials or sensitive request headers
    # ──────────────────────────────────────────────────────────────────────────

    @override_settings(DEBUG=False, TESTING=False, SMS_SIMULATION_MODE=False)
    @patch("requests.post")
    def test_credentials_never_logged_in_error_or_headers(self, mock_post):
        """Sensitive API keys and headers must never be logged or exposed in last_error."""
        secret_api_key = "TOP_SECRET_API_KEY_DO_NOT_EXPOSE_9988"
        provider = SMSEthiopiaProvider(api_key=secret_api_key)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized: Invalid API key credentials"
        mock_resp.json.side_effect = Exception("Not JSON")
        mock_post.return_value = mock_resp

        with self.assertLogs("apps.notifications.services", level="ERROR") as cm:
            sent = provider.send_sms("0911223344", "Security test")
            self.assertFalse(sent)

            # Ensure secret key is not in last_error or log records
            self.assertNotIn(secret_api_key, provider.last_error)
            for log_msg in cm.output:
                self.assertNotIn(secret_api_key, log_msg)
                self.assertNotIn("'KEY':", log_msg)
