import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from apps.notifications.services import (
    HahuSMSProvider,
    NotificationService,
    MockSMSProvider
)


class HahuSMSProviderTests(TestCase):
    def setUp(self):
        self.provider = HahuSMSProvider(
            api_url="https://hahu.io/api/send/sms",
            api_secret="dummy_hahu_secret_token",
            device_id="00000000-0000-0000-0000-000000000000",
            sim_slot=1,
            priority=1
        )

    def test_phone_normalization(self):
        self.assertEqual(self.provider.normalize_phone("0937381801"), "+251937381801")
        self.assertEqual(self.provider.normalize_phone("0712345678"), "+251712345678")
        self.assertEqual(self.provider.normalize_phone("+251937381801"), "+251937381801")
        self.assertEqual(self.provider.normalize_phone("251937381801"), "+251937381801")
        self.assertEqual(self.provider.normalize_phone(" 0911223344 "), "+251911223344")

    @patch("requests.post")
    def test_send_sms_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": 200,
            "message": "Message has been queued for sending!",
            "data": False
        }
        mock_post.return_value = mock_response

        success = self.provider.send_sms("0937381801", "Hello from Test Suite")
        self.assertTrue(success)
        mock_post.assert_called_once()
        
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://hahu.io/api/send/sms")
        self.assertIn("params", kwargs)
        params = kwargs["params"]
        self.assertEqual(params["secret"], "dummy_hahu_secret_token")
        self.assertEqual(params["device"], "00000000-0000-0000-0000-000000000000")
        self.assertEqual(params["mode"], "devices")
        self.assertEqual(params["phone"], "+251937381801")
        self.assertEqual(params["message"], "Hello from Test Suite")
        self.assertEqual(params["sim"], 1)

    @patch("requests.post")
    def test_send_sms_failure_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "status": 400,
            "message": "Device not connected or offline."
        }
        mock_post.return_value = mock_response

        success = self.provider.send_sms("0937381801", "Test failure")
        self.assertFalse(success)
        self.assertIn("Device not connected or offline", self.provider.last_error)

    @patch("requests.post")
    def test_send_sms_exception(self, mock_post):
        mock_post.side_effect = Exception("Network timeout")

        success = self.provider.send_sms("0937381801", "Test exception")
        self.assertFalse(success)
        self.assertIn("Network timeout", self.provider.last_error)

    @override_settings(DEBUG=False, TESTING=False)
    def test_missing_credentials_fails_in_production(self):
        unconfigured = HahuSMSProvider(api_secret="", device_id="")
        success = unconfigured.send_sms("0937381801", "Unconfigured message")
        self.assertFalse(success)
        self.assertIn("missing or unconfigured in production", unconfigured.last_error)

    def test_missing_credentials_simulates_in_simulation_mode(self):
        with override_settings(SMS_SIMULATION_MODE=True):
            unconfigured = HahuSMSProvider(api_secret="", device_id="")
            success = unconfigured.send_sms("0937381801", "Simulated message")
            self.assertTrue(success)
            self.assertTrue(unconfigured.last_details.get("simulated"))

    @override_settings(
        TESTING=False,
        HAHU_API_SECRET="dummy_hahu_secret_token",
        HAHU_DEVICE_ID="00000000-0000-0000-0000-000000000000",
        HAHU_API_URL="https://hahu.io/api/send/sms"
    )
    def test_notification_service_resolves_hahu_provider(self):
        # Reset cached provider
        NotificationService.set_sms_provider(None)
        with patch("sys.argv", ["manage.py", "runserver"]):
            provider = NotificationService.get_sms_provider()
            self.assertIsInstance(provider, HahuSMSProvider)
            
            info = NotificationService.get_active_provider_info()
            self.assertEqual(info["provider_class"], "HahuSMSProvider")
            self.assertEqual(info["provider_name"], "Hahu.io Android SMS Gateway")
            self.assertTrue(info["is_hahu_gateway"])
            self.assertTrue(info["is_live"])
            self.assertTrue(info["is_business_campaign"])
