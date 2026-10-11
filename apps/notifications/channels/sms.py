import os
import requests


class SMSNotificationChannel:
    @staticmethod
    def send_sms(to_phone: str, message_text: str) -> bool:
        """
        Dispatches SMS via active Ethiopian SMS gateway provider (Hahu.io / SMSEthiopia / AfroMessage).
        """
        from apps.notifications.services import NotificationService
        provider = NotificationService.get_sms_provider()
        return provider.send_sms(to_phone, message_text)
