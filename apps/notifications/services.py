import abc
import logging
from django.core.mail import send_mail
from django.conf import settings
from apps.communication.models import NotificationLog, NotificationChannel, TelegramAccountLink, UserNotificationPreference

logger = logging.getLogger(__name__)


class SMSProviderBase(abc.ABC):
    @abc.abstractmethod
    def send_sms(self, phone_number: str, message: str) -> bool:
        pass


class MockSMSProvider(SMSProviderBase):
    def send_sms(self, phone_number: str, message: str) -> bool:
        logger.info(f"[MOCK SMS] Sent to {phone_number}: {message}")
        print(f"[SIMULATION SMS to {phone_number}]: {message}")
        print("  --> To deliver real SMS to physical phones, configure AFROMESSAGE_API_KEY in .env")
        return True


class AfroMessageSMSProvider(SMSProviderBase):
    """
    Production SMS provider for Ethiopia using the AfroMessage API.
    Supports Ethio Telecom and Safaricom Ethiopia networks.
    """
    def __init__(self, api_key: str = None, sender_name: str = None, identifier_id: str = None):
        import os
        self.api_key = (
            api_key
            or getattr(settings, 'AFROMESSAGE_API_KEY', None)
            or os.environ.get('AFROMESSAGE_API_KEY')
            or os.environ.get('SMS_API_KEY')
        )
        self.sender_name = sender_name or getattr(settings, 'AFROMESSAGE_SENDER_NAME', None) or os.environ.get('AFROMESSAGE_SENDER_NAME')
        self.identifier_id = identifier_id or getattr(settings, 'AFROMESSAGE_IDENTIFIER_ID', None) or os.environ.get('AFROMESSAGE_IDENTIFIER_ID')

    def normalize_ethiopian_phone(self, phone: str) -> str:
        cleaned = "".join(ch for ch in str(phone).strip() if ch.isdigit() or ch == '+')
        if cleaned.startswith("+251"):
            return cleaned
        if cleaned.startswith("251"):
            return "+" + cleaned
        if cleaned.startswith("09") or cleaned.startswith("07"):
            return "+251" + cleaned[1:]
        if cleaned.startswith("9") or cleaned.startswith("7"):
            return "+251" + cleaned
        return cleaned

    def send_sms(self, phone_number: str, message: str) -> bool:
        if not self.api_key or self.api_key in ('test_key', 'your_key_here'):
            logger.warning("[AfroMessage] No live API key configured. Simulating dispatch.")
            print(f"[AfroMessage SIMULATION to {phone_number}]: {message}")
            return True

        import requests
        phone = self.normalize_ethiopian_phone(phone_number)
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'to': phone,
            'message': message,
        }
        if self.sender_name:
            payload['sender'] = self.sender_name
        if self.identifier_id:
            payload['from'] = self.identifier_id

        try:
            res = requests.post("https://api.afromessage.com/api/send", json=payload, headers=headers, timeout=10)
            if res.status_code in (200, 201):
                logger.info(f"[AfroMessage SMS SUCCESS] To: {phone} | HTTP {res.status_code}")
                return True
            else:
                logger.error(f"[AfroMessage SMS FAILED] HTTP {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.error(f"[AfroMessage SMS EXCEPTION] {e}")
            return False


class SMSEthiopiaProvider(SMSProviderBase):
    """
    Live SMS Provider for Ethiopia using smsethiopia.com API.
    Endpoint: https://smsethiopia.com/api/sms/send
    Header: KEY: <API_KEY>
    Body: {"msisdn": "2519...", "text": "..."}
    """
    def __init__(self, api_key: str = None):
        import os
        self.api_key = (
            api_key
            or getattr(settings, 'SMSETHIOPIA_API_KEY', None)
            or os.environ.get('SMSETHIOPIA_API_KEY')
            or os.environ.get('SMS_API_KEY')
        )

    def normalize_msisdn(self, phone: str) -> str:
        cleaned = "".join(ch for ch in str(phone).strip() if ch.isdigit())
        if cleaned.startswith("251"):
            return cleaned
        if cleaned.startswith("09") or cleaned.startswith("07"):
            return "251" + cleaned[1:]
        if cleaned.startswith("9") or cleaned.startswith("7"):
            return "251" + cleaned
        return cleaned

    def send_sms(self, phone_number: str, message: str) -> bool:
        if not self.api_key or self.api_key in ('test_key', 'your_key_here'):
            logger.warning("[SMSEthiopia] No live API key configured. Simulating dispatch.")
            print(f"[SMSEthiopia SIMULATION to {phone_number}]: {message}")
            return True

        import requests
        msisdn = self.normalize_msisdn(phone_number)
        headers = {
            'KEY': self.api_key,
            'Content-Type': 'application/json'
        }
        payload = {
            'msisdn': msisdn,
            'text': message
        }

        try:
            res = requests.post("https://smsethiopia.com/api/sms/send", json=payload, headers=headers, timeout=12)
            if res.status_code in (200, 201):
                logger.info(f"[SMSEthiopia SMS SUCCESS] Dispatched to {msisdn} | HTTP {res.status_code}")
                print(f"[SMSEthiopia SMS SUCCESS] Dispatched to {msisdn}: {res.text}")
                return True
            else:
                logger.error(f"[SMSEthiopia SMS FAILED] To: {msisdn} | HTTP {res.status_code}: {res.text}")
                print(f"[SMSEthiopia SMS FAILED] To {msisdn} HTTP {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.error(f"[SMSEthiopia SMS EXCEPTION] {e}")
            print(f"[SMSEthiopia SMS EXCEPTION] {e}")
            return False


class NotificationService:
    _sms_provider: SMSProviderBase = None

    @classmethod
    def get_sms_provider(cls) -> SMSProviderBase:
        if cls._sms_provider is not None:
            return cls._sms_provider

        if getattr(settings, 'TESTING', False):
            return MockSMSProvider()
        # 1. Check SMSEthiopia API key
        smsethiopia_key = (
            getattr(settings, 'SMSETHIOPIA_API_KEY', None)
            or os.environ.get('SMSETHIOPIA_API_KEY')
        )
        if smsethiopia_key and smsethiopia_key not in ('test_key', 'your_key_here'):
            return SMSEthiopiaProvider(api_key=smsethiopia_key)

        # 2. Check AfroMessage API key
        afromessage_key = (
            getattr(settings, 'AFROMESSAGE_API_KEY', None)
            or os.environ.get('AFROMESSAGE_API_KEY')
        )
        if afromessage_key and afromessage_key not in ('test_key', 'your_key_here'):
            return AfroMessageSMSProvider(api_key=afromessage_key)

        # 3. Check generic SMS_API_KEY
        generic_key = os.environ.get('SMS_API_KEY')
        if generic_key and generic_key not in ('test_key', 'your_key_here'):
            return SMSEthiopiaProvider(api_key=generic_key)

        return MockSMSProvider()

    @classmethod
    def set_sms_provider(cls, provider: SMSProviderBase):
        cls._sms_provider = provider

    @classmethod
    def send_notification(cls, school, recipient_user, channel: str, message: str, subject: str = None, category: str = 'announcement', phone_number: str = None):
        """
        Unified method to send notifications respecting user preferences.
        categories: 'attendance', 'payment', 'announcement', 'marketing'
        """
        prefs, _ = UserNotificationPreference.objects.get_or_create(user=recipient_user)

        # Check preferences
        if category == 'attendance' and not prefs.attendance_alerts:
            return False
        if category == 'payment' and not prefs.payment_alerts:
            return False
        if category == 'announcement' and not prefs.announcement_alerts:
            return False
        if category == 'marketing' and not prefs.marketing_alerts:
            return False

        success = False
        failure_reason = None

        if channel == NotificationChannel.SMS:
            phone = phone_number or getattr(recipient_user, 'phone', None)
            if not phone and hasattr(recipient_user, 'parent_profile'):
                phone = getattr(recipient_user.parent_profile, 'phone', None)
            provider = cls.get_sms_provider()
            success = provider.send_sms(phone, message)
            if not success:
                failure_reason = "SMS Gateway unreachable"

        elif channel == NotificationChannel.TELEGRAM:
            success = TelegramService.send_telegram_message(recipient_user, message)
            if not success:
                failure_reason = "User Telegram account not linked or unverified"

        elif channel == NotificationChannel.EMAIL:
            email = recipient_user.email
            if email:
                success = EmailService.send_email(email, subject or "School Notification", message)
            else:
                failure_reason = "User email address missing"

        elif channel == NotificationChannel.IN_APP:
            success = True

        status = 'SENT' if success else 'FAILED'

        NotificationLog.objects.create(
            school=school,
            recipient=recipient_user,
            channel=channel,
            subject=subject,
            message=message,
            status=status,
            failure_reason=failure_reason
        )

        return success
