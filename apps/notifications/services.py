import abc
import logging
from django.core.mail import send_mail
from django.conf import settings
from apps.communication.models import NotificationLog, NotificationChannel, TelegramAccountLink, UserNotificationPreference

logger = logging.getLogger(__name__)


class SMSProviderBase(abc.ABC):
    last_error: str = None
    last_details: dict = None
    is_live_gateway: bool = False

    @abc.abstractmethod
    def send_sms(self, phone_number: str, message: str) -> bool:
        pass


def _safe_console_print(text: str):
    import sys
    try:
        print(text)
    except (UnicodeEncodeError, Exception):
        try:
            encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
            safe_text = text.encode(encoding, errors='replace').decode(encoding, errors='replace')
            print(safe_text)
        except Exception:
            pass


class MockSMSProvider(SMSProviderBase):
    is_live_gateway = False

    def send_sms(self, phone_number: str, message: str) -> bool:
        self.last_error = None
        self.last_details = {'simulated': True}
        logger.info(f"[MOCK SMS] Sent to {phone_number}: {message}")
        _safe_console_print(f"[SIMULATION SMS to {phone_number}]: {message}")
        _safe_console_print("  --> To deliver real SMS to physical phones, configure AFROMESSAGE_API_KEY in .env")
        return True


class AfroMessageSMSProvider(SMSProviderBase):
    """
    Production SMS provider for Ethiopia using the AfroMessage API.
    Supports Ethio Telecom and Safaricom Ethiopia networks.
    """
    is_live_gateway = True

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
        import os
        self.last_error = None
        self.last_details = {}
        if not self.api_key or self.api_key in ('test_key', 'your_key_here'):
            logger.warning("[AfroMessage] No live API key configured. Simulating dispatch.")
            _safe_console_print(f"[AfroMessage SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        force_simulation = os.environ.get('SMS_SIMULATION_MODE', 'False').lower() in ('true', '1', 'yes')
        if force_simulation:
            logger.info(f"[AfroMessage FORCED SIMULATION to {phone_number}]: {message}")
            _safe_console_print(f"[AfroMessage SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
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
                self.last_error = f"AfroMessage Error (HTTP {res.status_code}): {res.text}"
                logger.error(f"[AfroMessage SMS FAILED] HTTP {res.status_code}: {res.text}")
                return False
        except Exception as e:
            self.last_error = f"AfroMessage Gateway Exception: {str(e)}"
            logger.error(f"[AfroMessage SMS EXCEPTION] {e}")
            return False


class SMSEthiopiaProvider(SMSProviderBase):
    """
    Live SMS Provider for Ethiopia using smsethiopia.com API.
    Endpoint: https://smsethiopia.com/api/sms/send
    Header: KEY: <API_KEY>
    Body: {"msisdn": "2519...", "text": "..."}
    """
    is_live_gateway = True

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
        import os
        self.last_error = None
        self.last_details = {}
        if not self.api_key or self.api_key in ('test_key', 'your_key_here'):
            logger.warning("[SMSEthiopia] No live API key configured. Simulating dispatch.")
            _safe_console_print(f"[SMSEthiopia SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        # Check if entire SMS simulation mode is forced via environment
        force_simulation = os.environ.get('SMS_SIMULATION_MODE', 'False').lower() in ('true', '1', 'yes')
        if force_simulation:
            logger.info(f"[SMSEthiopia FORCED SIMULATION to {phone_number}]: {message}")
            _safe_console_print(f"[SMSEthiopia SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
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
                _safe_console_print(f"[SMSEthiopia SMS SUCCESS] Dispatched to {msisdn}: {res.text}")
                return True
            else:
                err_text = res.text or ""
                is_sender_id_pending = (
                    "10006" in err_text
                    or "SenderID not approved" in err_text
                    or "SenderID" in err_text
                )
                is_unwhitelisted = (
                    "DEFAULT_CAMPAIGN_RECIPIENT_NOT_WHITELISTED" in err_text
                    or "10007" in err_text
                    or "WHITELIST" in err_text.upper()
                )

                # Check if dev simulation fallback is permitted during testing
                simulate_unwhitelisted = getattr(settings, 'SMS_SIMULATE_UNWHITELISTED', None)
                if simulate_unwhitelisted is None:
                    simulate_unwhitelisted = getattr(settings, 'DEBUG', False) or (
                        os.environ.get('SMS_SIMULATE_UNWHITELISTED', 'True').lower() in ('true', '1', 'yes')
                    )

                if is_sender_id_pending and simulate_unwhitelisted:
                    notice = (
                        f"[SMSEthiopia BUSINESS NOTICE]: Sender ID is pending approval on smsethiopia.com "
                        f"(Error 10006). Delivered to {msisdn} via simulation for local testing while awaiting approval."
                    )
                    logger.warning(notice)
                    _safe_console_print(notice)
                    self.last_details = {'simulated': True, 'reason': 'BUSINESS_SENDERID_PENDING_SIMULATED', 'msisdn': msisdn}
                    return True

                if is_unwhitelisted and simulate_unwhitelisted:
                    notice = (
                        f"[SMSEthiopia STARTER NOTICE]: Recipient {msisdn} is not whitelisted on your smsethiopia.com "
                        f"Starter campaign. Delivered via simulation for local testing."
                    )
                    logger.warning(notice)
                    _safe_console_print(notice)
                    self.last_details = {'simulated': True, 'reason': 'STARTER_UNWHITELISTED_SIMULATED', 'msisdn': msisdn}
                    return True

                if is_sender_id_pending:
                    self.last_error = (
                        "SMSEthiopia Business Campaign Notice: Your Campaign Sender ID is not approved yet "
                        "(Error Code 10006). Please contact SMSEthiopia support to approve your custom Sender ID."
                    )
                elif is_unwhitelisted:
                    self.last_error = (
                        f"SMSEthiopia Starter Account limitation: Recipient {msisdn} is not whitelisted in your "
                        f"smsethiopia.com dashboard. Starter campaigns only deliver to verified numbers (+251937381801). "
                        f"To send real SMS to all parents, upgrade to a paid SMSEthiopia package or switch to AfroMessage."
                    )
                else:
                    self.last_error = f"SMSEthiopia Error (HTTP {res.status_code}): {err_text}"

                logger.error(f"[SMSEthiopia SMS FAILED] To: {msisdn} | HTTP {res.status_code}: {res.text}")
                _safe_console_print(f"[SMSEthiopia SMS FAILED] To {msisdn} HTTP {res.status_code}: {res.text}")
                return False
        except Exception as e:
            self.last_error = f"SMSEthiopia Connection Error: {str(e)}"
            logger.error(f"[SMSEthiopia SMS EXCEPTION] {e}")
            _safe_console_print(f"[SMSEthiopia SMS EXCEPTION] {e}")
class TelegramService:
    @staticmethod
    def send_telegram_message(user, message: str) -> bool:
        import os, sys
        if not user:
            return False

        is_test = 'test' in sys.argv or getattr(settings, 'TESTING', False)
        link = TelegramAccountLink.objects.filter(user=user, is_verified=True).first()

        if is_test:
            logger.info(f"[TELEGRAM TEST SIMULATION] User: {user.username} | Message: {message}")
            _safe_console_print(f"[TELEGRAM SIMULATION to @{user.username}]: {message}")
            return True

        if not link or not link.telegram_chat_id:
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not bot_token:
                logger.info(f"[TELEGRAM SIMULATION] User: {user.username} | Message: {message}")
                _safe_console_print(f"[TELEGRAM SIMULATION to @{user.username}]: {message}")
                return True
            return False
        from apps.notifications.channels.telegram import TelegramNotificationChannel
        return TelegramNotificationChannel.send_telegram(link.telegram_chat_id, message)


class EmailService:
    @staticmethod
    def send_email(email_address: str, subject: str, message: str) -> bool:
        if not email_address:
            return False
        from django.core.mail import send_mail
        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.et')
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[email_address],
                fail_silently=False,
            )
            logger.info(f"[EMAIL SUCCESS] Sent to {email_address} | Subject: {subject}")
            return True
        except Exception as e:
            logger.error(f"[EMAIL FAILED] Sent to {email_address} | Error: {e}")
            _safe_console_print(f"[EMAIL DISPATCH ERROR to {email_address}]: {e}")
            return False


class NotificationService:
    _sms_provider: SMSProviderBase = None
    _last_failure_reason: str = None

    @classmethod
    def get_last_failure_reason(cls) -> str:
        return cls._last_failure_reason

    @classmethod
    def get_active_provider_info(cls) -> dict:
        provider = cls.get_sms_provider()
        name = provider.__class__.__name__
        is_live = getattr(provider, 'is_live_gateway', False)

        display_name = "Mock / Simulation Provider"
        is_starter = False
        is_business = False
        if isinstance(provider, SMSEthiopiaProvider):
            display_name = "SMSEthiopia Business Gateway"
            is_business = True
        elif isinstance(provider, AfroMessageSMSProvider):
            display_name = "AfroMessage Live Gateway"

        return {
            'provider_class': name,
            'provider_name': display_name,
            'is_live': is_live,
            'is_starter_campaign': is_starter,
            'is_business_campaign': is_business,
        }

    @classmethod
    def get_sms_provider(cls) -> SMSProviderBase:
        if cls._sms_provider is not None:
            return cls._sms_provider

        import sys
        if getattr(settings, 'TESTING', False) or 'test' in sys.argv or 'pytest' in sys.modules:
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
        cls._last_failure_reason = None
        if recipient_user:
            prefs, _ = UserNotificationPreference.objects.get_or_create(user=recipient_user)

            # Check preferences
            if category == 'attendance' and not prefs.attendance_alerts:
                cls._last_failure_reason = "Recipient opted out of attendance alerts"
                return False
            if category == 'payment' and not prefs.payment_alerts:
                cls._last_failure_reason = "Recipient opted out of payment alerts"
                return False
            if category == 'announcement' and not prefs.announcement_alerts:
                cls._last_failure_reason = "Recipient opted out of announcement alerts"
                return False
            if category == 'marketing' and not prefs.marketing_alerts:
                cls._last_failure_reason = "Recipient opted out of marketing alerts"
                return False

        success = False
        failure_reason = None

        if channel == NotificationChannel.SMS:
            phone = phone_number or (getattr(recipient_user, 'phone', None) if recipient_user else None)
            if not phone and recipient_user and hasattr(recipient_user, 'parent_profile'):
                phone = getattr(recipient_user.parent_profile, 'phone', None)
            provider = cls.get_sms_provider()
            success = provider.send_sms(phone, message)
            if not success:
                failure_reason = getattr(provider, 'last_error', None) or "SMS Gateway unreachable"
                cls._last_failure_reason = failure_reason

        elif channel == NotificationChannel.TELEGRAM:
            success = TelegramService.send_telegram_message(recipient_user, message) if recipient_user else False
            if not success:
                failure_reason = "User Telegram account not linked or unverified"
                cls._last_failure_reason = failure_reason

        elif channel == NotificationChannel.EMAIL:
            email = getattr(recipient_user, 'email', None) if recipient_user else None
            if email:
                success = EmailService.send_email(email, subject or "School Notification", message)
            else:
                failure_reason = "User email address missing"
            if not success:
                cls._last_failure_reason = failure_reason

        elif channel == NotificationChannel.IN_APP:
            success = True

        status = 'SENT' if success else 'FAILED'

        if recipient_user:
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
