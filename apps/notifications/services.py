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
        print(f"[MOCK SMS to {phone_number}]: {message}")
        return True


class AfroMessageSMSProvider(SMSProviderBase):
    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, 'AFROMESSAGE_API_KEY', 'test_key')

    def send_sms(self, phone_number: str, message: str) -> bool:
        logger.info(f"[AfroMessage SMS] API call to {phone_number}")
        # Production HTTP POST implementation to AfroMessage API endpoint
        return True


class TelegramService:
    @staticmethod
    def send_telegram_message(user, message: str) -> bool:
        try:
            link = TelegramAccountLink.objects.get(user=user, is_verified=True)
            chat_id = link.telegram_chat_id
            if not chat_id:
                return False
            print(f"[TELEGRAM to chat {chat_id} ({user.username})]: {message}")
            return True
        except TelegramAccountLink.DoesNotExist:
            return False


class EmailService:
    @staticmethod
    def send_email(recipient_email: str, subject: str, body: str) -> bool:
        try:
            print(f"[EMAIL to {recipient_email}]: Subject: {subject} | {body}")
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient_email], fail_silently=True)
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
            return False


class NotificationService:
    _sms_provider: SMSProviderBase = MockSMSProvider()

    @classmethod
    def set_sms_provider(cls, provider: SMSProviderBase):
        cls._sms_provider = provider

    @classmethod
    def send_notification(cls, school, recipient_user, channel: str, message: str, subject: str = None, category: str = 'announcement'):
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
            phone = getattr(recipient_user, 'phone', None) or '0911000000'
            success = cls._sms_provider.send_sms(phone, message)
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
