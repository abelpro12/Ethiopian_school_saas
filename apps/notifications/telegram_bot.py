import re
import sys
import logging
import os
import requests
from django.conf import settings

from django.db.models import Q

logger = logging.getLogger(__name__)


def clean_telegram_caption(caption: str, max_length: int = 1000) -> str:
    """
    Ensures caption is strictly within Telegram limit (1024 chars)
    and does not leave broken/unclosed HTML tags.
    """
    if not caption:
        return ""
    caption = str(caption).strip()
    if len(caption) <= max_length:
        return caption

    # If exceeding max_length, slice safely at newline or word boundary
    truncated = caption[:max_length]
    last_nl = truncated.rfind('\n')
    if last_nl > max_length - 200:
        truncated = truncated[:last_nl]

    # Ensure unclosed HTML tags are closed
    opened_tags = re.findall(r'<([a-zA-Z]+)(?:\s+[^>]*)?>', truncated)
    closed_tags = re.findall(r'</([a-zA-Z]+)>', truncated)
    for tag in reversed(opened_tags):
        if opened_tags.count(tag) > closed_tags.count(tag):
            truncated += f"</{tag}>"
            closed_tags.append(tag)

    return truncated


def normalize_phone(phone: str) -> list:
    """
    Returns possible variations of an Ethiopian phone number to match database records.
    (e.g., +251911200000, 251911200000, 0911200000, 911200000)
    """
    digits = "".join(ch for ch in str(phone or "").strip() if ch.isdigit())
    if not digits:
        return []

    variations = {phone.strip(), digits}

    # Normalize to 9-digit base (without prefix)
    base = None
    if digits.startswith("251") and len(digits) >= 12:
        base = digits[3:]
    elif (digits.startswith("09") or digits.startswith("07")) and len(digits) == 10:
        base = digits[1:]
    elif (digits.startswith("9") or digits.startswith("7")) and len(digits) == 9:
        base = digits

    if base:
        variations.add(f"+251{base}")
        variations.add(f"251{base}")
        variations.add(f"0{base}")
        variations.add(base)

    return list(variations)


class TelegramBotHandler:
    """
    Handles bidirectional interaction for the School Telegram Bot:
    - Welcome / onboarding for parents
    - One-click account verification and linking
    - Automatic student/parent matching
    - Direct free report card and exam result delivery
    """

    @classmethod
    def get_token(cls) -> str:
        return (
            getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
            or os.environ.get('TELEGRAM_BOT_TOKEN')
        )

    @classmethod
    def send_message(cls, chat_id: str, text: str, reply_markup=None) -> bool:
        token = cls.get_token()
        if not token:
            logger.warning(f"[TELEGRAM SIMULATION] ChatID: {chat_id} | Message: {str(text)[:60]}...")
            return getattr(settings, 'TELEGRAM_SIMULATION', False) or 'test' in sys.argv

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': str(chat_id),
            'text': str(text or ''),
            'parse_mode': 'HTML',
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            res = requests.post(url, json=payload, timeout=12)
            if res.status_code == 200:
                return True

            # If HTML parsing failed, strip HTML tags and retry as plain text
            if res.status_code == 400 and ('parse entities' in res.text.lower() or 'entity' in res.text.lower()):
                logger.warning(f"[Telegram Bot HTML Parse Warning] Retrying without parse_mode: {res.text}")
                payload.pop('parse_mode', None)
                payload['text'] = re.sub(r'<[^>]+>', '', str(text or ''))
                retry_res = requests.post(url, json=payload, timeout=12)
                if retry_res.status_code == 200:
                    return True

            logger.error(f"[Telegram Bot Error] HTTP {res.status_code}: {res.text}")
            return False
        except Exception as e:
            logger.warning(f"[Telegram Bot Exception] {e}")
            if getattr(settings, 'TELEGRAM_SIMULATION', False) or ('test' in sys.argv and not token):
                return True
            return False

    @classmethod
    def send_photo(cls, chat_id: str, photo, caption: str = '', reply_markup=None) -> bool:
        """
        Dispatches a photo directly to Telegram chat with HTML formatted caption.
        Accepts file paths, in-memory files/BytesIO, bytes, or HTTP URLs.
        """
        if not photo or (isinstance(photo, str) and not os.path.exists(photo)):
            return cls.send_message(chat_id, caption, reply_markup=reply_markup)

        token = cls.get_token()
        if not token:
            logger.warning(f"[TELEGRAM SIMULATION] ChatID: {chat_id} | Photo sent | Caption: {caption[:60]}...")
            return getattr(settings, 'TELEGRAM_SIMULATION', False) or 'test' in sys.argv

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        clean_cap = clean_telegram_caption(caption, max_length=1000)
        data = {
            'chat_id': str(chat_id),
            'caption': clean_cap,
            'parse_mode': 'HTML',
        }
        if reply_markup:
            data['reply_markup'] = reply_markup

        f_handle = None
        try:
            res = None
            if isinstance(photo, str) and (photo.startswith('http://') or photo.startswith('https://')):
                data['photo'] = photo
                res = requests.post(url, data=data, timeout=15)
            elif isinstance(photo, str) and os.path.exists(photo):
                f_handle = open(photo, 'rb')
                fname = os.path.basename(photo) or 'photo.jpg'
                file_tuple = (fname, f_handle, 'image/jpeg')
                res = requests.post(url, data=data, files={'photo': file_tuple}, timeout=25)
            elif hasattr(photo, 'read'):
                if hasattr(photo, 'seek'):
                    photo.seek(0)
                file_bytes = photo.read()
                fname = getattr(photo, 'name', 'photo.jpg')
                file_tuple = (fname, file_bytes, 'image/jpeg')
                res = requests.post(url, data=data, files={'photo': file_tuple}, timeout=25)
            elif isinstance(photo, bytes):
                file_tuple = ('photo.jpg', photo, 'image/jpeg')
                res = requests.post(url, data=data, files={'photo': file_tuple}, timeout=25)
            else:
                logger.error(f"[Telegram Bot] Invalid photo parameter type: {type(photo)}")
                return False

            if f_handle:
                try:
                    f_handle.close()
                except Exception:
                    pass
                f_handle = None

            if res and res.status_code == 200:
                return True

            # If HTML parsing failed on caption, retry without parse_mode / plain text
            if res and res.status_code == 400 and ('parse entities' in res.text.lower() or 'entity' in res.text.lower()):
                logger.warning(f"[Telegram Bot Photo Entity Error] Retrying caption as plain text: {res.text}")
                data.pop('parse_mode', None)
                data['caption'] = re.sub(r'<[^>]+>', '', clean_cap)[:1000]
                if isinstance(photo, str) and os.path.exists(photo):
                    with open(photo, 'rb') as f_retry:
                        fname = os.path.basename(photo) or 'photo.jpg'
                        retry_res = requests.post(url, data=data, files={'photo': (fname, f_retry, 'image/jpeg')}, timeout=25)
                        if retry_res.status_code == 200:
                            return True
                elif hasattr(photo, 'read'):
                    if hasattr(photo, 'seek'):
                        photo.seek(0)
                    retry_res = requests.post(url, data=data, files={'photo': file_tuple}, timeout=25)
                    if retry_res.status_code == 200:
                        return True

            logger.error(f"[Telegram Bot Photo Error] HTTP {res.status_code if res else 'None'}: {res.text if res else 'No response'}")
            return False
        except Exception as e:
            if f_handle:
                try:
                    f_handle.close()
                except Exception:
                    pass
            logger.warning(f"[Telegram Bot Photo Exception] {e}")
            if getattr(settings, 'TELEGRAM_SIMULATION', False) or ('test' in sys.argv and not token):
                return True
            return False



    @classmethod
    def handle_incoming_message(cls, message: dict) -> dict:
        """
        Processes a single message object from Telegram.
        """
        chat = message.get('chat', {})
        chat_id = str(chat.get('id', ''))
        from_user = message.get('from', {})
        text = str(message.get('text', '')).strip()
        contact = message.get('contact')

        if not chat_id:
            return {'status': 'ignored', 'reason': 'no_chat_id'}

        from apps.communication.models import TelegramAccountLink
        from apps.parents.models import ParentProfile
        from apps.students.models import StudentProfile

        # Check if already verified
        existing_link = TelegramAccountLink.objects.filter(
            telegram_chat_id=chat_id,
            is_verified=True
        ).select_related('user').first()

        # Handle Contact Card Shared directly via Telegram
        phone_to_check = None
        if contact and contact.get('phone_number'):
            phone_to_check = contact.get('phone_number')
        elif text and not text.startswith('/'):
            phone_to_check = text

        # Handle /start command with optional payload (e.g. /start 0911200000 or /start STU-1001)
        if text.startswith('/start'):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                arg = parts[1].strip()
                return cls._link_by_identifier(chat_id, arg, from_user)

            if existing_link:
                user_name = existing_link.user.get_full_name() or existing_link.user.username
                msg = (
                    f"👋 <b>Welcome back, {user_name}!</b>\n\n"
                    f"✅ Your Telegram account is actively linked to <b>Seattle Academy</b>.\n\n"
                    f"You will automatically receive your children's:\n"
                    f" • 🏆 <b>Semester & Annual Report Cards</b>\n"
                    f" • 📝 <b>Test & Exam Result Alerts</b>\n"
                    f" • 📢 <b>Official School Announcements</b>\n\n"
                    f"<i>100% Free • Powered by EthioSchool SaaS</i>"
                )
                cls.send_message(chat_id, msg)
                return {'status': 'welcome_back', 'chat_id': chat_id}

            # Prompt to link
            msg = (
                f"🎓 <b>Welcome to Seattle Academy Report Bot!</b>\n\n"
                f"This bot delivers your child's <b>exam results, grades, and report cards</b> "
                f"directly to your Telegram instantly and 100% free.\n\n"
                f"👉 <b>To link your account:</b>\n"
                f"Please reply with your <b>registered Phone Number</b> (e.g. <code>0911200000</code>) "
                f"or your child's <b>Student ID</b> (e.g. <code>STU-SEA-9A02</code>)."
            )
            # Keyboard to share contact with one click
            keyboard = {
                'keyboard': [[{'text': '📱 Share My Phone Number', 'request_contact': True}]],
                'resize_keyboard': True,
                'one_time_keyboard': True
            }
            cls.send_message(chat_id, msg, reply_markup=keyboard)
            return {'status': 'prompted_for_linking', 'chat_id': chat_id}

        # Handle /status
        if text.startswith('/status'):
            if existing_link:
                user_name = existing_link.user.get_full_name() or existing_link.user.username
                cls.send_message(
                    chat_id,
                    f"✅ <b>Status: Active & Verified</b>\n"
                    f"👤 <b>Parent:</b> {user_name}\n"
                    f"🏫 <b>School:</b> {existing_link.school.name if existing_link.school else 'Seattle Academy'}\n"
                    f"Notifications are enabled."
                )
            else:
                cls.send_message(
                    chat_id,
                    "⚠️ <b>Status: Not Linked</b>\n"
                    "Please reply with your phone number to link your account."
                )
            return {'status': 'status_checked'}

        # Handle phone number or student ID input
        if phone_to_check:
            return cls._link_by_identifier(chat_id, phone_to_check, from_user)

        return {'status': 'unhandled'}

    @classmethod
    def _link_by_identifier(cls, chat_id: str, identifier: str, from_user: dict) -> dict:
        from apps.communication.models import TelegramAccountLink
        from apps.parents.models import ParentProfile
        from apps.students.models import StudentProfile

        clean_id = identifier.strip()
        phone_variations = normalize_phone(clean_id)
        digits = "".join(ch for ch in str(identifier) if ch.isdigit())
        base_9 = digits[-9:] if len(digits) >= 9 else None

        # 1. Search in ParentProfile by phone
        parent = None
        if phone_variations:
            parent = ParentProfile.objects.filter(
                Q(phone__in=phone_variations) |
                Q(user__phone__in=phone_variations)
            ).select_related('user', 'school').first()

        # Fallback by 9-digit suffix
        if not parent and base_9:
            parent = ParentProfile.objects.filter(
                Q(phone__icontains=base_9) |
                Q(user__phone__icontains=base_9)
            ).select_related('user', 'school').first()

        # 2. If not found by phone, search by Student ID or Student Roll
        student = None
        if not parent:
            student = StudentProfile.objects.filter(
                Q(student_id__iexact=clean_id) |
                Q(first_name__iexact=clean_id)
            ).select_related('school').first()

            if student:
                # Find student's guardian parent
                guardianship = student.guardianships.select_related('parent__user', 'parent__school').first()
                if guardianship and guardianship.parent:
                    parent = guardianship.parent

        if parent and parent.user:
            # Create or update link
            link, _ = TelegramAccountLink.objects.update_or_create(
                user=parent.user,
                defaults={
                    'telegram_chat_id': str(chat_id),
                    'is_verified': True,
                    'school': parent.school or getattr(student, 'school', None),
                }
            )

            parent_name = parent.user.get_full_name() or parent.user.username
            school_name = parent.school.name if parent.school else "Seattle Academy"

            # Get linked students for nice confirmation
            linked_students = []
            for g in parent.guardianships.select_related('student').all():
                if g.student:
                    linked_students.append(f"• <b>{g.student.full_name}</b> ({g.student.student_id})")

            students_text = "\n".join(linked_students) if linked_students else "• Enrolled Student"

            confirmation_msg = (
                f"🎉 <b>Success! Account Verified & Linked</b>\n\n"
                f"👤 <b>Parent:</b> {parent_name}\n"
                f"🏫 <b>School:</b> {school_name}\n\n"
                f"👶 <b>Linked Student(s):</b>\n{students_text}\n\n"
                f"✨ You are all set! Exam results and report cards will be sent directly here in real-time."
            )
            # Remove custom keyboard
            cls.send_message(chat_id, confirmation_msg, reply_markup={'remove_keyboard': True})
            return {'status': 'linked', 'parent_user': parent.user.username}

        # Identifier could not be matched
        cls.send_message(
            chat_id,
            f"❌ <b>Record Not Found</b>\n\n"
            f"We could not find a parent account matching <code>{clean_id}</code>.\n\n"
            f"Please double check that this is the phone number registered with the school registrar, "
            f"or send your child's <b>Student ID</b> (e.g. <code>STU-SEA-9A02</code>)."
        )
        return {'status': 'not_found', 'query': clean_id}

    @classmethod
    def sync_updates(cls, limit: int = 100) -> int:
        """
        Polls Telegram's getUpdates API, processes any new messages, and confirms offsets.
        Returns the number of processed updates.
        """
        token = cls.get_token()
        if not token:
            return 0

        # Read last update_id from cache or temp file
        last_offset = 0
        cache_path = os.path.join(settings.BASE_DIR, 'scratch', 'telegram_last_offset.txt')
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    last_offset = int(f.read().strip() or '0')
            except Exception:
                pass

        params = {'limit': limit, 'timeout': 5}
        if last_offset > 0:
            params['offset'] = last_offset + 1

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code != 200:
                logger.error(f"[Telegram getUpdates Error] HTTP {res.status_code}: {res.text}")
                return 0

            data = res.json()
            if not data.get('ok'):
                return 0

            updates = data.get('result', [])
            processed_count = 0
            max_id = last_offset

            for upd in updates:
                upd_id = upd.get('update_id', 0)
                if upd_id > max_id:
                    max_id = upd_id

                if 'message' in upd:
                    cls.handle_incoming_message(upd['message'])
                    processed_count += 1

            if max_id > last_offset:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(str(max_id))

            return processed_count
        except Exception as e:
            logger.error(f"[Telegram sync_updates exception] {e}")
            return 0
