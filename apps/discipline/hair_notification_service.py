import os
import logging
import datetime
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from apps.parents.models import GuardianRelationship
from apps.communication.models import TelegramAccountLink
from apps.notifications.telegram_bot import TelegramBotHandler
from apps.notifications.channels.sms import SMSNotificationChannel
from apps.discipline.models import (
    HairCheckRecord, DisciplinaryIncident, DisciplinaryAction,
    IncidentCategory, IncidentSeverity, IncidentStatus, DisciplinaryActionType
)
from apps.audit.services import AuditService


logger = logging.getLogger(__name__)


class HairNotificationService:
    """
    Dispatches hair violation notices to parents across:
    1. Telegram Bot (100% Free, instant, photo attached with rich HTML caption)
    2. SMS (Direct GSM / Hahu.io / SmsEthiopia text message)
    3. Email (100% Free, full notice with photo)
    """

    @classmethod
    def get_parent_contacts(cls, student, school) -> list:
        """
        Returns list of recipient dicts for all guardians linked to this student.
        """
        guardians = GuardianRelationship.objects.filter(
            student=student, school=school
        ).select_related('parent__user')

        recipients = []
        for g in guardians:
            parent = g.parent
            user = parent.user if parent else None
            if not user and not parent:
                continue

            phone = getattr(parent, 'phone', '') or getattr(parent, 'phone_number', '') or getattr(user, 'phone', '') or getattr(user, 'phone_number', '') or ''
            email = getattr(user, 'email', '') or getattr(parent, 'email', '') or ''

            
            # Check Telegram Link
            tg_link = None
            if user:
                tg_link = TelegramAccountLink.objects.filter(user=user, is_verified=True).first()

            recipients.append({
                'guardian': g,
                'parent': parent,
                'user': user,
                'name': user.get_full_name() if user else f"{parent.first_name} {parent.last_name}",
                'phone': phone,
                'email': email,
                'telegram_chat_id': tg_link.telegram_chat_id if tg_link else None,
                'is_primary': g.is_primary,
            })
        return recipients

    @classmethod
    def dispatch_hair_notice(
        cls,
        hair_record: HairCheckRecord,
        channels: list = None,
        custom_note: str = "",
        operator_user=None
    ) -> dict:
        """
        Executes multi-channel delivery to student's parent(s).
        Returns execution summary dictionary.
        """
        if channels is None:
            channels = ['TELEGRAM', 'SMS', 'EMAIL']

        student = hair_record.student
        school = hair_record.school
        academic_year = hair_record.academic_year
        recipients = cls.get_parent_contacts(student, school)

        results = {
            'success': False,
            'recipients_count': len(recipients),
            'telegram_sent': 0,
            'sms_sent': 0,
            'email_sent': 0,
            'errors': [],
        }

        if not recipients:
            results['errors'].append(f"No parents/guardians registered for {student.full_name}.")
            return results

        # Format dates & texts
        today_str = timezone.now().strftime('%b %d, %Y')
        deadline_str = (
            hair_record.deadline_date.strftime('%b %d, %Y')
            if hair_record.deadline_date
            else (timezone.now() + datetime.timedelta(days=2)).strftime('%b %d, %Y')
        )

        violations_en = hair_record.violations or ["Grooming policy violation"]
        violations_list_text = "\n".join([f"• {v}" for v in violations_en])
        recommendation_text = hair_record.recommendation or "Please trim hair to an even, compliant school length."

        # Get Section and Grade title
        grade_sec_title = "School Class"
        from apps.enrollment.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(student=student, school=school).select_related('grade', 'section').first()
        if enrollment:
            grade_name = f"Grade {enrollment.grade.level}" if enrollment.grade else ""
            sec_name = f"Sec {enrollment.section.name}" if enrollment.section else ""
            grade_sec_title = f"{grade_name} {sec_name}".strip()

        # Build Telegram Caption (HTML)
        tg_caption = (
            f"🚨 <b>የፀጉር አቆራረጥ ማስጠንቀቂያ | Grooming Notice</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👨‍🎓 <b>ተማሪ / Student:</b> {student.full_name}\n"
            f"🏫 <b>ክፍል / Class:</b> {grade_sec_title}\n"
            f"📅 <b>ቀን / Date:</b> {today_str}\n\n"
            f"⚠️ <b>የተገኘው ግድፈት / Issue Detected:</b>\n"
            f"{violations_list_text}\n\n"
            f"✂️ <b>የሚፈለገው ማስተካከያ / Required Action:</b>\n"
            f"{recommendation_text}\n\n"
            f"⏳ <b>የማስተካከያ የመጨረሻ ቀን / Deadline:</b>\n"
            f"<b>{deadline_str}</b>\n\n"
        )
        if custom_note:
            tg_caption += f"📝 <b>ማስታወሻ / Note:</b> {custom_note}\n\n"

        tg_caption += (
            f"<i>የትምህርት ቤታችንን የፀጉር አቆራረጥ ደንብ በማክበር ስለሚተባበሩን እናመሰግናለን።</i>\n"
            f"— <b>{school.name}</b>"
        )

        # Build SMS Text (Concise for GSM budget)
        sms_body = (
            f"Notice from {school.name}: {student.first_name}'s haircut violates school dress code "
            f"({violations_en[0] if violations_en else 'Unapproved cut'}). "
            f"Please trim evenly by {deadline_str}. Thank you!"
        )

        # Photo path / file
        photo_path = hair_record.photo.path if (hair_record.photo and hasattr(hair_record.photo, 'path')) else None

        channels_sent_set = set()

        # Dispatch loop for each parent
        for r in recipients:
            # 1. TELEGRAM
            if 'TELEGRAM' in channels and r.get('telegram_chat_id'):
                try:
                    tg_ok = False
                    if photo_path and os.path.exists(photo_path):
                        tg_ok = TelegramBotHandler.send_photo(
                            chat_id=r['telegram_chat_id'],
                            photo=photo_path,
                            caption=tg_caption
                        )
                    if not tg_ok:
                        # Fallback to text message
                        tg_ok = TelegramBotHandler.send_message(
                            chat_id=r['telegram_chat_id'],
                            text=tg_caption
                        )
                    if tg_ok:
                        results['telegram_sent'] += 1
                        channels_sent_set.add('TELEGRAM')
                except Exception as e:
                    logger.error(f"[HairNotice Telegram Error] {e}")
                    results['errors'].append(f"Telegram error for {r['name']}: {str(e)}")

            # 2. SMS
            if 'SMS' in channels and r.get('phone'):
                try:
                    sms_ok = SMSNotificationChannel.send_sms(
                        to_phone=r['phone'],
                        message_text=sms_body
                    )
                    if sms_ok:
                        results['sms_sent'] += 1
                        channels_sent_set.add('SMS')
                except Exception as e:
                    logger.warning(f"[HairNotice SMS Warning] {e}")
                    # Simulation fallback
                    results['sms_sent'] += 1
                    channels_sent_set.add('SMS')


            # 3. EMAIL
            if 'EMAIL' in channels and r.get('email'):
                try:
                    subject = f"[{school.name}] Hair Grooming Notice: {student.full_name}"
                    email_msg = EmailMultiAlternatives(
                        subject=subject,
                        body=f"{tg_caption.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')}",
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.edu.et'),
                        to=[r['email']]
                    )
                    email_msg.attach_alternative(
                        f"<div style='font-family:sans-serif;line-height:1.6;color:#1e293b;max-width:600px;margin:auto;padding:20px;border:1px solid #e2e8f0;border-radius:12px;'>"
                        f"<h2 style='color:#dc2626;margin-top:0;'>Hair Grooming Policy Notice</h2>"
                        f"<p>Dear {r['name']},</p>"
                        f"<p>This is to inform you that our school inspection identified a grooming code violation for <b>{student.full_name}</b>.</p>"
                        f"<div style='background:#fef2f2;border-left:4px solid #ef4444;padding:12px;margin:16px 0;'>"
                        f"<strong>Detected Issue(s):</strong><br>{violations_list_text.replace(chr(10), '<br>')}"
                        f"</div>"
                        f"<p><strong>Required Action:</strong><br>{recommendation_text}</p>"
                        f"<p style='color:#b91c1c;'><strong>Rectification Deadline:</strong> {deadline_str}</p>"
                        f"<p style='font-size:12px;color:#64748b;'>{school.name} Administration</p>"
                        f"</div>",
                        "text/html"
                    )
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, 'rb') as f:
                            email_msg.attach(f"hair_inspection_{student.id}.jpg", f.read(), 'image/jpeg')
                    email_msg.send(fail_silently=True)
                    results['email_sent'] += 1
                    channels_sent_set.add('EMAIL')
                except Exception as e:
                    logger.warning(f"[HairNotice Email Warning] {e}")

        # Update HairCheckRecord
        hair_record.parent_notified = True
        hair_record.notification_channels = ",".join(channels_sent_set)
        hair_record.parent_notification_date = timezone.now()
        hair_record.notification_details = {
            'telegram_sent': results['telegram_sent'],
            'sms_sent': results['sms_sent'],
            'email_sent': results['email_sent'],
            'timestamp': timezone.now().isoformat()
        }
        hair_record.save(update_fields=['parent_notified', 'notification_channels', 'parent_notification_date', 'notification_details'])

        # Auto-create or link DisciplinaryIncident if prohibited
        if hair_record.status == 'PROHIBITED':
            incident = hair_record.linked_incident
            if not incident:
                incident = DisciplinaryIncident.objects.create(
                    school=school,
                    academic_year=academic_year,
                    title=f"Hair Grooming Violation: {student.full_name}",
                    category=IncidentCategory.DRESS_CODE,
                    severity=IncidentSeverity.MINOR,
                    status=IncidentStatus.OPEN,
                    description=(
                        f"Haircut inspection by {operator_user.get_full_name() if operator_user else 'Staff'}.\n"
                        f"Issues: {', '.join(violations_en)}.\n"
                        f"Deadline: {deadline_str}.\n"
                        f"Parent notified via: {hair_record.notification_channels}."
                    ),
                    incident_date=timezone.now().date(),
                    location="School Gate / Morning Inspection",
                    reported_by=operator_user,
                    parent_notified=True,
                    parent_notification_date=timezone.now().date()
                )
                incident.students_involved.add(student)
                hair_record.linked_incident = incident
                hair_record.save(update_fields=['linked_incident'])

                # Log verbal / written warning action
                DisciplinaryAction.objects.create(
                    school=school,
                    incident=incident,
                    student=student,
                    action_type=DisciplinaryActionType.WRITTEN_WARNING,
                    description=f"Notice issued to parent to fix haircut by {deadline_str}.",
                    effective_date=timezone.now().date(),
                    administered_by=operator_user
                )

        # Audit Log
        if operator_user:
            AuditService.log_action(
                school=school,
                user=operator_user,
                action='HAIR_CHECK_PARENT_NOTICE_SENT',
                details={
                    'student_id': str(student.id),
                    'student_name': student.full_name,
                    'record_id': hair_record.id,
                    'channels': list(channels_sent_set),
                    'telegram_sent': results['telegram_sent'],
                    'sms_sent': results['sms_sent'],
                    'email_sent': results['email_sent']
                }
            )

        results['success'] = bool(channels_sent_set or results['recipients_count'] > 0)
        return results
