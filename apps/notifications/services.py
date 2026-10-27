import os
import sys
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


def is_sms_simulation_allowed() -> bool:
    """
    Returns True ONLY if simulation mode is explicitly permitted:
    1. Environment variable SMS_SIMULATION_MODE is explicitly 'true' / '1' / 'yes' -> True
       (If explicitly 'false' / '0' / 'no' -> False)
    2. Django settings SMS_SIMULATION_MODE is explicitly True -> True
       (If explicitly False -> False)
    3. If testing (TESTING=True) or development (DEBUG=True), simulation is permitted.
    
    In production (DEBUG=False, TESTING=False, and no explicit SMS_SIMULATION_MODE),
    simulation is strictly prohibited to prevent false-success reporting.
    """
    import os
    env_mode = os.environ.get('SMS_SIMULATION_MODE', '').strip().lower()
    if env_mode in ('true', '1', 'yes'):
        return True
    if env_mode in ('false', '0', 'no'):
        return False

    explicit_setting = getattr(settings, 'SMS_SIMULATION_MODE', None)
    if explicit_setting is not None:
        return bool(explicit_setting)

    return bool(getattr(settings, 'DEBUG', False) or getattr(settings, 'TESTING', False))


class MockSMSProvider(SMSProviderBase):
    is_live_gateway = False

    def send_sms(self, phone_number: str, message: str) -> bool:
        self.last_error = None
        if not is_sms_simulation_allowed():
            self.last_error = "SMS gateway unconfigured in production: MockSMSProvider cannot dispatch live SMS."
            self.last_details = {'simulated': False, 'error': 'UNCONFIGURED_IN_PRODUCTION'}
            logger.error("[MOCK SMS] Unconfigured provider invoked in production environment. Failing closed.")
            return False

        self.last_details = {'simulated': True}
        logger.info(f"[MOCK SMS] Sent to {phone_number}: {message}")
        _safe_console_print(f"[SIMULATION SMS to {phone_number}]: {message}")
        _safe_console_print("  --> To deliver real SMS to physical phones, configure AFROMESSAGE_API_KEY in .env")
        return True


class HahuSMSProvider(SMSProviderBase):
    """
    Production SMS provider for Ethiopia using Hahu.io Android SMS Gateway.
    Sends SMS directly via connected Android device SIM card (Ethio Telecom / Safaricom).
    Endpoint: https://hahu.io/api/send/sms
    Required query parameters:
      - secret: API Secret Key
      - mode: 'devices'
      - device: Android Device ID
      - sim: SIM Slot (1 or 2)
      - priority: 1
      - phone: Recipient phone number (+251... or 09...)
      - message: Text message
    """
    is_live_gateway = True

    def __init__(
        self,
        api_url: str = None,
        api_secret: str = None,
        device_id: str = None,
        sim_slot: int = 1,
        priority: int = 1
    ):
        import os
        self.api_url = (
            api_url
            if api_url is not None
            else (getattr(settings, 'HAHU_API_URL', None) or os.environ.get('HAHU_API_URL') or "https://hahu.io/api/send/sms")
        )
        self.api_secret = (
            api_secret
            if api_secret is not None
            else (getattr(settings, 'HAHU_API_SECRET', None) or os.environ.get('HAHU_API_SECRET'))
        )
        self.device_id = (
            device_id
            if device_id is not None
            else (getattr(settings, 'HAHU_DEVICE_ID', None) or os.environ.get('HAHU_DEVICE_ID'))
        )
        self.sim_slot = sim_slot if sim_slot is not None else getattr(settings, 'HAHU_SIM_SLOT', 1)
        self.priority = priority if priority is not None else getattr(settings, 'HAHU_PRIORITY', 1)

    def normalize_phone(self, phone: str) -> str:
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
        import os, sys, requests
        self.last_error = None
        self.last_details = {}

        if not phone_number:
            self.last_error = "Missing recipient phone number."
            self.last_details = {'error': 'MISSING_PHONE'}
            return False

        has_creds = bool(self.api_secret and self.device_id and self.api_secret not in ('test_key', 'your_key_here'))
        if not has_creds:
            if not is_sms_simulation_allowed():
                self.last_error = "Hahu.io credentials (API secret or Device ID) missing or unconfigured in production environment."
                self.last_details = {'simulated': False, 'error': 'MISSING_CREDENTIALS'}
                logger.error("[HahuSMS] Dispatch aborted: Missing Hahu credentials in production.")
                return False
            logger.warning("[HahuSMS] No live API secret or Device ID configured. Simulating dispatch.")
            _safe_console_print(f"[HahuSMS SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        if is_sms_simulation_allowed() and (
            getattr(settings, 'SMS_SIMULATION_MODE', False) or
            os.environ.get('SMS_SIMULATION_MODE', '').strip().lower() in ('true', '1', 'yes')
        ):
            logger.info(f"[HahuSMS FORCED SIMULATION to {phone_number}]: {message}")
            _safe_console_print(f"[HahuSMS SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        phone = self.normalize_phone(phone_number)
        payload = {
            'secret': self.api_secret,
            'mode': 'devices',
            'device': self.device_id,
            'sim': self.sim_slot,
            'priority': self.priority,
            'phone': phone,
            'message': message,
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        }

        try:
            res = requests.post(self.api_url, params=payload, headers=headers, timeout=15)
            try:
                data = res.json()
            except Exception:
                data = {}

            if res.status_code == 200 and data.get('status') == 200:
                logger.info(f"[HahuSMS SUCCESS] To: {phone} | Queued on device {self.device_id} | Msg: {data.get('message')}")
                _safe_console_print(f"[HahuSMS SUCCESS] Queued to {phone} (Device: {self.device_id}): {data.get('message')}")
                self.last_details = {'status': 200, 'device': self.device_id, 'phone': phone}
                return True
            else:
                err_msg = data.get('message') or res.text or f"HTTP {res.status_code}"
                self.last_error = f"Hahu.io Error: {err_msg}"
                logger.error(f"[HahuSMS FAILED] To: {phone} | HTTP {res.status_code} | {err_msg}")
                _safe_console_print(f"[HahuSMS FAILED] {self.last_error}")
                return False
        except Exception as e:
            self.last_error = f"Hahu.io Exception: {str(e)}"
            logger.error(f"[HahuSMS EXCEPTION] {e}")
            _safe_console_print(f"[HahuSMS EXCEPTION] {e}")
            return False


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

        if not phone_number:
            self.last_error = "Missing recipient phone number."
            self.last_details = {'error': 'MISSING_PHONE'}
            return False

        has_creds = bool(self.api_key and self.api_key not in ('test_key', 'your_key_here'))
        if not has_creds:
            if not is_sms_simulation_allowed():
                self.last_error = "AfroMessage credentials (API key) missing or unconfigured in production environment."
                self.last_details = {'simulated': False, 'error': 'MISSING_CREDENTIALS'}
                logger.error("[AfroMessage] Dispatch aborted: Missing API key in production.")
                return False
            logger.warning("[AfroMessage] No live API key configured. Simulating dispatch.")
            _safe_console_print(f"[AfroMessage SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        if is_sms_simulation_allowed() and (
            getattr(settings, 'SMS_SIMULATION_MODE', False) or
            os.environ.get('SMS_SIMULATION_MODE', '').strip().lower() in ('true', '1', 'yes')
        ):
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
                try:
                    data = res.json()
                except Exception:
                    data = {}
                if data.get('acknowledge') == 'error' or data.get('status') in ('error', 'failed', 'FAIL') or data.get('error'):
                    err_msg = data.get('response', {}).get('message') or data.get('message') or "Unknown provider error"
                    self.last_error = f"AfroMessage Error: {err_msg}"
                    logger.error(f"[AfroMessage SMS FAILED] {err_msg}")
                    return False
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
        self.starter_key = (
            getattr(settings, 'SMSETHIOPIA_STARTER_KEY', None)
            or os.environ.get('SMSETHIOPIA_STARTER_KEY')
            or None
        )
        self.dev_phone = (
            getattr(settings, 'SMS_DEV_PHONE', None)
            or os.environ.get('SMS_DEV_PHONE')
            or None
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
        import os, sys
        self.last_error = None
        self.last_details = {}

        if not phone_number:
            self.last_error = "Missing recipient phone number."
            self.last_details = {'error': 'MISSING_PHONE'}
            return False

        has_creds = bool(self.api_key and self.api_key not in ('test_key', 'your_key_here'))
        if not has_creds:
            if not is_sms_simulation_allowed():
                self.last_error = "SMSEthiopia credentials (API key) missing or unconfigured in production environment."
                self.last_details = {'simulated': False, 'error': 'MISSING_CREDENTIALS'}
                logger.error("[SMSEthiopia] Dispatch aborted: Missing API key in production.")
                return False
            logger.warning("[SMSEthiopia] No live API key configured. Simulating dispatch.")
            _safe_console_print(f"[SMSEthiopia SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        # Check if entire SMS simulation mode is forced via environment or settings
        if is_sms_simulation_allowed() and (
            getattr(settings, 'SMS_SIMULATION_MODE', False) or
            os.environ.get('SMS_SIMULATION_MODE', '').strip().lower() in ('true', '1', 'yes')
        ):
            logger.info(f"[SMSEthiopia FORCED SIMULATION to {phone_number}]: {message}")
            _safe_console_print(f"[SMSEthiopia SIMULATION to {phone_number}]: {message}")
            self.last_details = {'simulated': True}
            return True

        import requests
        msisdn = self.normalize_msisdn(phone_number)
        norm_dev_phone = self.normalize_msisdn(self.dev_phone)
        headers = {
            'KEY': self.api_key,
            'Content-Type': 'application/json'
        }
        payload = {
            'msisdn': msisdn,
            'text': message
        }

        is_test_run = 'test' in sys.argv or getattr(settings, 'TESTING', False)

        try:
            # 1. Primary dispatch attempt with configured API key
            res = requests.post("https://smsethiopia.com/api/sms/send", json=payload, headers=headers, timeout=12)
            
            err_text = ""
            is_error_payload = False
            if res.status_code in (200, 201):
                try:
                    data = res.json()
                except Exception:
                    data = {}

                if isinstance(data, dict):
                    if data.get('error') is True or data.get('status') in ('error', 'failed', 'FAIL'):
                        is_error_payload = True
                        err_text = data.get('error_message') or data.get('message') or data.get('error') or str(data)
                    elif 'error_message' in data or 'error_code' in data:
                        is_error_payload = True
                        err_text = data.get('error_message') or str(data.get('error_code'))
                    elif data.get('success') is False:
                        is_error_payload = True
                        err_text = data.get('message') or "Provider reported dispatch failure"

                if not is_error_payload:
                    logger.info(f"[SMSEthiopia SMS SUCCESS] Dispatched to {msisdn} | HTTP {res.status_code}")
                    _safe_console_print(f"[SMSEthiopia SMS SUCCESS] Dispatched to {msisdn}: {res.text}")
                    self.last_details = {'direct_delivered': True, 'msisdn': msisdn}
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

            # 2. If configured key is blocked by pending custom Sender ID (Error 10006), try fallback starter key
            if is_sender_id_pending and self.starter_key and self.starter_key != self.api_key:
                res_starter = requests.post(
                    "https://smsethiopia.com/api/sms/send",
                    json=payload,
                    headers={'KEY': self.starter_key, 'Content-Type': 'application/json'},
                    timeout=12
                )
                if res_starter.status_code in (200, 201):
                    logger.info(f"[SMSEthiopia STARTER FALLBACK SUCCESS] Dispatched to {msisdn} | HTTP {res_starter.status_code}")
                    _safe_console_print(f"[SMSEthiopia STARTER FALLBACK SUCCESS] Dispatched to {msisdn}: {res_starter.text}")
                    self.last_details = {'direct_delivered': True, 'msisdn': msisdn, 'via': 'starter_fallback'}
                    return True
                
                err_text = res_starter.text or ""
                is_unwhitelisted = (
                    "DEFAULT_CAMPAIGN_RECIPIENT_NOT_WHITELISTED" in err_text
                    or "10007" in err_text
                    or "WHITELIST" in err_text.upper()
                )

            # Check if simulation/dev-mode fallback is allowed
            simulate_unwhitelisted = getattr(settings, 'SMS_SIMULATE_UNWHITELISTED', None)
            if simulate_unwhitelisted is None:
                simulate_unwhitelisted = is_sms_simulation_allowed() and (
                    os.environ.get('SMS_SIMULATE_UNWHITELISTED', 'False').lower() in ('true', '1', 'yes')
                )

            # In development/test simulation mode ONLY or when explicitly enabled via setting:
            if (is_unwhitelisted or is_sender_id_pending) and simulate_unwhitelisted:
                notice = (
                    f"[SMSEthiopia DEV NOTICE]: Recipient {msisdn} simulated locally for development testing (unwhitelisted on Starter campaign)."
                )
                logger.info(notice)
                _safe_console_print(notice)
                self.last_details = {'simulated': True, 'reason': 'DEV_SIMULATED', 'msisdn': msisdn}
                return True

            if is_sender_id_pending:
                self.last_error = (
                    "SMSEthiopia Business Campaign Notice: Your Campaign Sender ID is not approved yet "
                    "(Error Code 10006). Please contact SMSEthiopia support to approve your custom Sender ID."
                )
            elif is_unwhitelisted:
                self.last_error = (
                    f"SMSEthiopia Starter Account limitation: Recipient {msisdn} is not whitelisted in your "
                    f"smsethiopia.com dashboard. Starter campaigns only deliver to verified numbers. "
                    f"To send real SMS to all parents, whitelist their number in smsethiopia.com or upgrade to an approved campaign or switch to AfroMessage."
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
            return False
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

        from apps.notifications.channels.telegram import TelegramNotificationChannel

        if link and link.telegram_chat_id:
            return TelegramNotificationChannel.send_telegram(link.telegram_chat_id, message)

        # STRICT PRIVACY: If this parent has not linked Telegram, DO NOT send to any other parent's chat!
        logger.info(f"[TELEGRAM NOT LINKED] Parent user @{user.username} has not linked @Seattle_Academy_Bot.")
        _safe_console_print(f"[TELEGRAM NOT LINKED] Parent @{user.username} has no active Telegram bot connection.")
        return False


class EmailService:
    @staticmethod
    def send_email(email_address: str, subject: str, message: str) -> bool:
        if not email_address:
            return False
        import os, sys
        from django.core.mail import send_mail

        host_user = getattr(settings, 'EMAIL_HOST_USER', None) or os.environ.get('EMAIL_HOST_USER')
        is_test = 'test' in sys.argv or getattr(settings, 'TESTING', False)

        # Simulation mode when SMTP credentials are not configured or in testing
        if not host_user or is_test:
            logger.info(f"[EMAIL SIMULATION] Sent to {email_address} | Subject: {subject}")
            _safe_console_print(f"[EMAIL SIMULATION to {email_address}]: Subject: '{subject}'")
            _safe_console_print("  --> To deliver live emails to parent inboxes, set EMAIL_HOST_USER & EMAIL_HOST_PASSWORD in .env")
            return True

        # In DEBUG / local dev, if recipient is a dummy domain, simulate locally to avoid leaking across parents
        target_email = email_address
        is_dummy_domain = any(str(email_address).lower().endswith(d) for d in [
            '@student.seattleacademyethiopia.com',
            '@seattleacademyethiopia.com',
            '@school.et',
            '@example.com',
            '@test.com',
            '@localhost'
        ])
        if is_dummy_domain and getattr(settings, 'DEBUG', False):
            logger.info(f"[EMAIL DEV SIMULATION to {email_address}]: Subject: '{subject}'")
            _safe_console_print(f"[EMAIL DEV SIMULATION to {email_address}]: Subject: '{subject}'")
            return True

        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or host_user or 'noreply@school.et'
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[target_email],
                fail_silently=False,
            )
            logger.info(f"[EMAIL SUCCESS] Sent to {target_email} (original: {email_address}) | Subject: {subject}")
            _safe_console_print(f"[EMAIL DISPATCH SUCCESS to {target_email}]: Subject '{subject}'")
            return True
        except Exception as e:
            logger.error(f"[EMAIL FAILED] Sent to {email_address} | Error: {e}")
            _safe_console_print(f"[EMAIL DISPATCH ERROR to {email_address}]: {e}")
            # If live SMTP failed in DEBUG mode, fall back to simulation so user workflow is never blocked
            if getattr(settings, 'DEBUG', False):
                _safe_console_print(f"[EMAIL DEV FALLBACK SIMULATION to {email_address}]: {subject}")
                return True
            return False

    @classmethod
    def send_parent_welcome_and_verification_email(cls, school, parent_user, temp_password: str = None, student = None) -> bool:
        """
        Sends an automated welcome, credentials, and notification verification email
        to a newly registered or verified parent.
        """
        if not parent_user or not getattr(parent_user, 'email', None):
            return False

        import os
        school_name = getattr(school, 'name', 'School')
        bot_username = getattr(settings, 'TELEGRAM_BOT_USERNAME', None) or os.environ.get('TELEGRAM_BOT_USERNAME', 'Seattle_Academy_Bot')
        student_name = student.full_name if student else "your student"
        parent_name = parent_user.get_full_name() or parent_user.first_name or parent_user.username

        subject = f"🎓 [{school_name}] Welcome & Parent Portal Activation"
        body = (
            f"Dear {parent_name},\n\n"
            f"Welcome to {school_name}! Your parent portal account has been successfully registered and linked to {student_name}.\n\n"
            f"🔑 PARENT PORTAL LOGIN CREDENTIALS:\n"
            f"• Username: {parent_user.username}\n"
        )
        if temp_password:
            body += f"• Temporary Password: {temp_password}\n"
        body += (
            f"• Login Link: Access attendance, fee payments, and student progress on the web portal.\n\n"
            f"📲 FREE INSTANT TELEGRAM ALERTS (RECOMMENDED):\n"
            f"To receive instant push notifications and interactive report cards on your mobile device for 100% free:\n"
            f"1. Open Telegram and search for: @{bot_username} (https://t.me/{bot_username})\n"
            f"2. Tap 'START' and tap 'Share Contact' to automatically link your account.\n\n"
            f"✉️ EMAIL NOTIFICATIONS VERIFIED:\n"
            f"This email confirms that your inbox is registered for official semester report cards, exam result releases, and school announcements.\n\n"
            f"Best regards,\n"
            f"{school_name} Administration\n"
            f"Addis Ababa, Ethiopia"
        )

        success = cls.send_email(parent_user.email, subject, body)
        if success:
            # Security: Do not persist temporary passwords in database notification logs.
            # Record credential-free audit metadata for the sent activation email.
            log_message = (
                f"Parent Portal Welcome & Verification email dispatched to {parent_user.email}.\n"
                f"Student: {student_name}\n"
                f"Username: {parent_user.username}\n"
                f"Credentials: [CONFIDENTIAL_CREDENTIAL_ISSUED]"
            )
            NotificationLog.objects.create(
                school=school,
                recipient=parent_user,
                channel='EMAIL',
                subject=subject,
                message=log_message,
                status='SENT'
            )
        return success

    @classmethod
    def send_user_invitation_email(cls, school, user, setup_url: str) -> bool:
        """
        Sends an account setup / invitation link to a newly created Teacher, Staff,
        Student, or Parent. Avoids transmitting raw passwords.
        """
        if not user or not getattr(user, 'email', None):
            return False

        school_name = getattr(school, 'name', 'School')
        user_name = user.get_full_name() or user.first_name or user.username
        role_label = user.get_role_display() if hasattr(user, 'get_role_display') else 'Staff'

        subject = f"🎓 [{school_name}] Activate Your {role_label} Account"
        body = (
            f"Dear {user_name},\n\n"
            f"An account has been created for you at {school_name} with the role of {role_label}.\n\n"
            f"🔑 ACCOUNT ACTIVATION:\n"
            f"• Username: {user.username}\n"
            f"• Setup Link: {setup_url}\n\n"
            f"Please visit the setup link above to configure your personal password. "
            f"This link is single-use and will expire in 3 days for security.\n\n"
            f"Best regards,\n"
            f"{school_name} Administration"
        )
        success = cls.send_email(user.email, subject, body)
        if success:
            log_message = (
                f"Account activation invitation dispatched to {user.email}.\n"
                f"Role: {role_label}\n"
                f"Username: {user.username}\n"
                f"Activation: [ONE_TIME_SETUP_LINK_ISSUED]"
            )
            NotificationLog.objects.create(
                school=school,
                recipient=user,
                channel='EMAIL',
                subject=subject,
                message=log_message,
                status='SENT'
            )
        return success


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
        is_hahu = False
        if isinstance(provider, HahuSMSProvider):
            display_name = "Hahu.io Android SMS Gateway"
            is_business = True
            is_hahu = True
        elif isinstance(provider, SMSEthiopiaProvider):
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
            'is_hahu_gateway': is_hahu,
        }

    @classmethod
    def get_sms_provider(cls) -> SMSProviderBase:
        if cls._sms_provider is not None:
            return cls._sms_provider

        # 1. Check Hahu.io SMS API secret and device ID (primary gateway)
        hahu_secret = (
            getattr(settings, 'HAHU_API_SECRET', None)
            or os.environ.get('HAHU_API_SECRET')
        )
        hahu_device = (
            getattr(settings, 'HAHU_DEVICE_ID', None)
            or os.environ.get('HAHU_DEVICE_ID')
        )
        if hahu_secret and hahu_device and hahu_secret not in ('test_key', 'your_key_here'):
            return HahuSMSProvider(
                api_url=getattr(settings, 'HAHU_API_URL', 'https://hahu.io/api/send/sms'),
                api_secret=hahu_secret,
                device_id=hahu_device,
                sim_slot=getattr(settings, 'HAHU_SIM_SLOT', 1),
                priority=getattr(settings, 'HAHU_PRIORITY', 1),
            )

        # 2. Check SMSEthiopia API key
        smsethiopia_key = (
            getattr(settings, 'SMSETHIOPIA_API_KEY', None)
            or os.environ.get('SMSETHIOPIA_API_KEY')
        )
        if smsethiopia_key and smsethiopia_key not in ('test_key', 'your_key_here'):
            return SMSEthiopiaProvider(api_key=smsethiopia_key)

        # 3. Check AfroMessage API key
        afromessage_key = (
            getattr(settings, 'AFROMESSAGE_API_KEY', None)
            or os.environ.get('AFROMESSAGE_API_KEY')
        )
        if afromessage_key and afromessage_key not in ('test_key', 'your_key_here'):
            return AfroMessageSMSProvider(api_key=afromessage_key)

        # 4. Check generic SMS_API_KEY
        generic_key = os.environ.get('SMS_API_KEY')
        if generic_key and generic_key not in ('test_key', 'your_key_here'):
            return SMSEthiopiaProvider(api_key=generic_key)

        return MockSMSProvider()

    @classmethod
    def set_sms_provider(cls, provider: SMSProviderBase):
        cls._sms_provider = provider

    @classmethod
    def send_sms(cls, phone_number: str, message: str) -> bool:
        """
        Direct SMS dispatch method on NotificationService.
        Dispatches via active configured SMS provider, recording failure reasons if unsuccessful.
        """
        if not phone_number:
            cls._last_failure_reason = "Missing recipient phone number."
            return False
        provider = cls.get_sms_provider()
        success = provider.send_sms(phone_number, message)
        if not success:
            cls._last_failure_reason = getattr(provider, 'last_error', None) or "SMS Gateway unreachable"
        return success

    @classmethod
    def send_notification(cls, school, recipient_user, channel: str, message: str, subject: str = None, category: str = 'announcement', phone_number: str = None, email_address: str = None):
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
            if not phone:
                success = False
                failure_reason = "Missing recipient phone number."
                cls._last_failure_reason = failure_reason
            else:
                success = cls.send_sms(phone, message)
                if not success:
                    failure_reason = cls._last_failure_reason

        elif channel == NotificationChannel.TELEGRAM:
            success = TelegramService.send_telegram_message(recipient_user, message) if recipient_user else False
            if not success:
                failure_reason = "User Telegram account not linked or unverified"
                cls._last_failure_reason = failure_reason

        elif channel == NotificationChannel.EMAIL:
            email = email_address or (getattr(recipient_user, 'email', None) if recipient_user else None)
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
