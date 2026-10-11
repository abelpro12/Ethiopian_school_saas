import os
import requests
from django.conf import settings


class TelegramNotificationChannel:
    @staticmethod
    def send_telegram(chat_id: str, message_text: str) -> bool:
        """
        Dispatches Telegram bot message notification to parent/teacher.
        Supports HTML formatting with automatic fallback to plain text if parsing fails.
        """
        bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None) or os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            print(f"[TELEGRAM SIMULATION] ChatID: {chat_id} | Msg: {message_text}")
            return True

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': str(chat_id),
            'text': message_text,
            'parse_mode': 'HTML'
        }
        try:
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                return True

            # If HTML parsing failed (400 Bad Request: can't parse entities), retry as plain text
            if res.status_code == 400 and 'can\'t parse entities' in res.text:
                plain_payload = {
                    'chat_id': str(chat_id),
                    'text': message_text
                }
                retry_res = requests.post(url, json=plain_payload, timeout=8)
                return retry_res.status_code == 200

            print(f"[Telegram Bot HTTP {res.status_code} Error]: {res.text}")
            return False
        except Exception as e:
            print(f"Telegram Dispatch Error: {e}")
            return False
