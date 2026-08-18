import os
import requests


class TelegramNotificationChannel:
    @staticmethod
    def send_telegram(chat_id: str, message_text: str) -> bool:
        """
        Dispatches Telegram bot message notification to parent/teacher.
        """
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            print(f"[TELEGRAM SIMULATION] ChatID: {chat_id} | Msg: {message_text}")
            return True

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message_text,
            'parse_mode': 'HTML'
        }
        try:
            res = requests.post(url, json=payload, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"Telegram Dispatch Error: {e}")
            return False
