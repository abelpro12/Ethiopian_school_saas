import os
import requests


class SMSNotificationChannel:
    @staticmethod
    def send_sms(to_phone: str, message_text: str) -> bool:
        """
        Dispatches SMS via Ethiopian SMS API gateway provider (e.g. Afromessage / Ethio Telecom SMS API).
        """
        api_key = os.environ.get('SMS_API_KEY')
        if not api_key:
            print(f"[SMS SIMULATION] To: {to_phone} | Msg: {message_text}")
            return True

        # Production gateway payload
        payload = {
            'to': to_phone,
            'message': message_text,
            'token': api_key
        }
        try:
            # Example API dispatch
            res = requests.post("https://api.afromessage.com/api/send-by-post", data=payload, timeout=5)
            return res.status_code == 200
        except Exception as e:
            print(f"SMS Dispatch Error: {e}")
            return False
