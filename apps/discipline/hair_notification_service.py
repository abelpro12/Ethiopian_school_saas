import os
import logging
import datetime
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from apps.parents.models import GuardianRelationship
from apps.communication.models import TelegramAccountLink
from apps.notifications.telegram_bot import TelegramBotHandler, normalize_phone
from apps.notifications.channels.sms import SMSNotificationChannel
from apps.discipline.models import (
    HairCheckRecord, HairCheckStatus, DisciplinaryIncident, DisciplinaryAction,
    IncidentCategory, IncidentSeverity, IncidentStatus, DisciplinaryActionType
)
from apps.discipline.hair_ai_service import HairCheckAIService
from apps.audit.services import AuditService


logger = logging.getLogger(__name__)


class HairNotificationService:
    """
    Dispatches hair inspection notices (violations and approvals) to parents across:
    1. Telegram Bot (100% Free, instant, photo attached with clear, persuasive HTML caption)
    2. SMS (Direct GSM / Hahu.io / SmsEthiopia text message with clear persuasive reason)
    3. Email (100% Free, full persuasive educational letter with photo)
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

            # Check Telegram Link (by user or by phone variations)
            tg_link = None
            if user:
                tg_link = TelegramAccountLink.objects.filter(
                    user=user,
                    telegram_chat_id__isnull=False
                ).exclude(telegram_chat_id='').first()
            if not tg_link and phone:
                phone_vars = normalize_phone(phone)
                tg_link = TelegramAccountLink.objects.filter(
                    user__phone__in=phone_vars,
                    telegram_chat_id__isnull=False
                ).exclude(telegram_chat_id='').first()

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
        Supports both PROHIBITED violation notices and ALLOWED commendation notices.
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

        is_prohibited = (hair_record.status == HairCheckStatus.PROHIBITED)
        violations_en = hair_record.violations or (["Grooming policy violation"] if is_prohibited else [])
        violations_list_text = "\n".join([f"• {v}" for v in violations_en]) if violations_en else "• No violations detected (Compliant standard length)"
        violations_summary = violations_en[0] if violations_en else "Haircut non-compliance"

        # Determine clear & persuasive reason
        reason_en = (hair_record.reason or '').strip()
        reason_am = (hair_record.reason_am or '').strip()
        if not reason_en or not reason_am:
            is_fade = any('fade' in str(v).lower() for v in violations_en)
            is_too_long = any('long' in str(v).lower() or 'bushy' in str(v).lower() for v in violations_en)
            if not reason_en:
                reason_en = HairCheckAIService._build_persuasive_reason(
                    status=hair_record.status,
                    is_fade=is_fade,
                    is_too_long=is_too_long,
                    student_name=student.full_name,
                    lang='en'
                )
            if not reason_am:
                reason_am = HairCheckAIService._build_persuasive_reason(
                    status=hair_record.status,
                    is_fade=is_fade,
                    is_too_long=is_too_long,
                    student_name=student.full_name,
                    lang='am'
                )

        recommendation_text = hair_record.recommendation or (
            "Trim sides and top evenly to standard school length (Grade 1 or 2 cut)."
            if is_prohibited else "Haircut conforms to standards; no action needed."
        )

        # Get Section and Grade title
        grade_sec_title = "School Class"
        from apps.enrollment.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(student=student, school=school).select_related('grade', 'section').first()
        if enrollment:
            grade_name = f"Grade {enrollment.grade.level}" if enrollment.grade else ""
            sec_name = f"Sec {enrollment.section.name}" if enrollment.section else ""
            grade_sec_title = f"{grade_name} {sec_name}".strip()

        # Build Messages
        if is_prohibited:
            # 1. Telegram Photo Caption for PROHIBITED (HTML) - Strictly < 850 chars for Telegram sendPhoto limit
            tg_photo_caption = (
                f"🚨 <b>የፀጉር አቆራረጥ ማስጠንቀቂያ | Hair Grooming Policy Notice</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👨‍🎓 <b>ተማሪ / Student:</b> {student.full_name}\n"
                f"🏫 <b>ክፍል / Class:</b> {grade_sec_title}\n"
                f"📅 <b>ቀን / Date:</b> {today_str}\n\n"
                f"⚠️ <b>የተገኘው ግድፈት / Issue(s) Detected:</b>\n"
                f"{violations_list_text}\n\n"
                f"✂️ <b>ለፀጉር አስተካካይ የሚሰጥ መመሪያ / Action for Barber:</b>\n"
                f"{recommendation_text}\n\n"
                f"⏳ <b>የማስተካከያ የመጨረሻ ቀን / Rectification Deadline:</b>\n"
                f"<b>{deadline_str}</b>\n\n"
                f"— <b>{school.name}</b>"
            )

            # 2. Telegram Companion Educational Rationale Letter
            tg_detail_message = (
                f"📋 <b>ግልጽ ምክንያትና ማብራሪያ | Policy Rationale & Details</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>ተማሪ / Student:</b> {student.full_name}\n\n"
                f"<b>በአማርኛ / Amharic:</b>\n"
                f"{reason_am}\n\n"
                f"<b>In English:</b>\n"
                f"<i>{reason_en}</i>\n\n"
            )
            if custom_note:
                tg_detail_message += f"📝 <b>ተጨማሪ ማስታወሻ / Note:</b> {custom_note}\n\n"

            tg_detail_message += (
                f"<i>የትምህርት ቤታችን ወጥ የፀጉር አቆራረጥ ደንብ በተማሪዎች መካከል እኩልነትን፣ ዲሲፕሊንን እና የትምህርት ትኩረትን "
                f"ለማስፈን ያለመ ነው። ስለ ትብብርዎ ከልብ እናመሰግናለን።</i>\n\n"
                f"— <b>{school.name} Administration</b>"
            )

            # Combined caption for fallback/display
            tg_caption = f"{tg_photo_caption}\n\n{tg_detail_message}"

            # 3. SMS for PROHIBITED (Clear, persuasive, within reasonable GSM length)
            sms_body = (
                f"Notice from {school.name}: {student.first_name}'s haircut violates school code ({violations_summary}). "
                f"Our policy requires an even, uniform cut to ensure equality & focus. "
                f"Please have a barber trim it evenly (Grade 1/2) by {deadline_str}. Thank you!"
            )

            # 4. Email Subject & HTML for PROHIBITED
            email_subject = f"[{school.name}] Hair Grooming Policy Notice: {student.full_name}"
            email_html = (
                f"<div style='font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif;line-height:1.6;color:#1e293b;max-width:620px;margin:auto;padding:24px;border:1px solid #e2e8f0;border-radius:16px;background:#ffffff;'>"
                f"<div style='border-bottom:2px solid #fee2e2;padding-bottom:14px;margin-bottom:18px;'>"
                f"<span style='background:#fee2e2;color:#991b1b;font-size:11px;font-weight:bold;padding:4px 10px;border-radius:20px;text-transform:uppercase;'>Grooming Policy Notice</span>"
                f"<h2 style='color:#b91c1c;margin:10px 0 4px;'>Haircut Inspection Notice</h2>"
                f"<p style='color:#64748b;font-size:13px;margin:0;'>{school.name} &bull; Date: {today_str}</p>"
                f"</div>"
                f"<p style='font-size:14px;'>Dear Parent / Guardian of <b>{student.full_name}</b> ({grade_sec_title}),</p>"
                f"<p style='font-size:13px;color:#334155;'>During our routine grooming and discipline inspection, your child's haircut was evaluated as non-compliant with Ethiopian school dress code standards.</p>"
                f"<div style='background:#fef2f2;border-left:4px solid #ef4444;padding:14px;margin:16px 0;border-radius:8px;'>"
                f"<strong style='color:#991b1b;font-size:13px;'>Detected Violation:</strong><br>"
                f"<span style='font-size:13px;color:#450a0a;'>{violations_list_text.replace(chr(10), '<br>')}</span>"
                f"</div>"
                f"<div style='background:#f8fafc;border:1px solid #e2e8f0;padding:14px;margin:16px 0;border-radius:8px;'>"
                f"<strong style='color:#1e293b;font-size:13px;'>Why This Rule Is Enforced (Persuasive Rationale):</strong>"
                f"<p style='font-size:12px;color:#475569;margin:6px 0 0;line-height:1.5;'>{reason_en.replace(chr(10), '<br>')}</p>"
                f"</div>"
                f"<div style='background:#eff6ff;border-left:4px solid #3b82f6;padding:14px;margin:16px 0;border-radius:8px;'>"
                f"<strong style='color:#1e40af;font-size:13px;'>Instructions for the Barber & Parent:</strong>"
                f"<p style='font-size:13px;color:#1e3a8a;margin:6px 0 0;'>{recommendation_text}</p>"
                f"<p style='font-size:13px;color:#b91c1c;margin:8px 0 0;'><strong>Rectification Deadline:</strong> {deadline_str}</p>"
                f"</div>"
                f"<p style='font-size:12px;color:#64748b;margin-top:20px;border-top:1px solid #f1f5f9;padding-top:12px;'>"
                f"We greatly value your partnership in instilling discipline, self-respect, and academic focus in our students.<br>"
                f"— <b>{school.name} Administration</b>"
                f"</p>"
                f"</div>"
            )

        else:
            # 1. Telegram Photo Caption for ALLOWED (Commendation)
            tg_photo_caption = (
                f"🌟 <b>የፀጉር አቆራረጥ ምርመራ ውጤት | Grooming Inspection Passed</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👨‍🎓 <b>ተማሪ / Student:</b> {student.full_name}\n"
                f"🏫 <b>ክፍል / Class:</b> {grade_sec_title}\n"
                f"📅 <b>ቀን / Date:</b> {today_str}\n\n"
                f"✅ <b>ውሳኔ / Status:</b> <b>ተፈቅዷል / Compliant (Approved)</b>\n\n"
                f"👏 <b>ምስጋና / Commendation:</b>\n"
                f"<i>ልጅዎ የትምህርት ቤቱን የፀጉር አቆራረጥ እና የስነ-ምግባር ደንብ አክብሮ እንዲቀርብ ስላደረጉ ከልብ እናመሰግናለን! "
                f"ይህ መልካም አርአያነት በትምህርታቸውም ላይ እንዲቀጥል እናበረታታለን።</i>\n\n"
                f"— <b>{school.name}</b>"
            )

            tg_detail_message = (
                f"📋 <b>የምርመራ ማጠቃለያ | Evaluation Finding:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>ተማሪ / Student:</b> {student.full_name}\n\n"
                f"{reason_am}\n\n"
                f"<i>{reason_en}</i>\n\n"
                f"— <b>{school.name} Administration</b>"
            )

            tg_caption = f"{tg_photo_caption}\n\n{tg_detail_message}"

            # 2. SMS for ALLOWED
            sms_body = (
                f"{school.name}: {student.first_name}'s haircut was inspected today and complies with school grooming standards. "
                f"Thank you for supporting our discipline and uniform guidelines!"
            )

            # 3. Email Subject & HTML for ALLOWED
            email_subject = f"[{school.name}] Grooming Inspection Passed: {student.full_name}"
            email_html = (
                f"<div style='font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif;line-height:1.6;color:#1e293b;max-width:620px;margin:auto;padding:24px;border:1px solid #e2e8f0;border-radius:16px;background:#ffffff;'>"
                f"<div style='border-bottom:2px solid #dcfce7;padding-bottom:14px;margin-bottom:18px;'>"
                f"<span style='background:#dcfce7;color:#166534;font-size:11px;font-weight:bold;padding:4px 10px;border-radius:20px;text-transform:uppercase;'>Inspection Passed</span>"
                f"<h2 style='color:#15803d;margin:10px 0 4px;'>Grooming Code Commendation</h2>"
                f"<p style='color:#64748b;font-size:13px;margin:0;'>{school.name} &bull; Date: {today_str}</p>"
                f"</div>"
                f"<p style='font-size:14px;'>Dear Parent / Guardian of <b>{student.full_name}</b> ({grade_sec_title}),</p>"
                f"<p style='font-size:13px;color:#334155;'>We are pleased to inform you that your child's haircut was inspected today and fully satisfies our school grooming and discipline standards.</p>"
                f"<div style='background:#f0fdf4;border-left:4px solid #22c55e;padding:14px;margin:16px 0;border-radius:8px;'>"
                f"<strong style='color:#166534;font-size:13px;'>Evaluation Finding:</strong>"
                f"<p style='font-size:12px;color:#14532d;margin:6px 0 0;line-height:1.5;'>{reason_en.replace(chr(10), '<br>')}</p>"
                f"</div>"
                f"<p style='font-size:13px;color:#334155;'>Thank you for partnering with us to maintain a disciplined, respectful, and equal learning environment for every child.</p>"
                f"<p style='font-size:12px;color:#64748b;margin-top:20px;border-top:1px solid #f1f5f9;padding-top:12px;'>"
                f"— <b>{school.name} Administration</b>"
                f"</p>"
                f"</div>"
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
                            caption=tg_photo_caption
                        )
                        if tg_ok and (reason_am or reason_en):
                            # Companion educational policy message
                            TelegramBotHandler.send_message(
                                chat_id=r['telegram_chat_id'],
                                text=tg_detail_message
                            )
                    if not tg_ok:
                        full_msg = f"{tg_photo_caption}\n\n{tg_detail_message}"
                        tg_ok = TelegramBotHandler.send_message(
                            chat_id=r['telegram_chat_id'],
                            text=full_msg
                        )
                    if tg_ok:
                        results['telegram_sent'] += 1
                        channels_sent_set.add('TELEGRAM')
                    else:
                        results['errors'].append(f"Telegram bot failed to deliver to {r['name']} ({r.get('telegram_chat_id')})")
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
                    results['sms_sent'] += 1
                    channels_sent_set.add('SMS')

            # 3. EMAIL
            if 'EMAIL' in channels and r.get('email'):
                try:
                    email_msg = EmailMultiAlternatives(
                        subject=email_subject,
                        body=f"{tg_caption.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')}",
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@school.edu.et'),
                        to=[r['email']]
                    )
                    email_msg.attach_alternative(email_html, "text/html")
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, 'rb') as f:
                            email_msg.attach(f"hair_inspection_{student.id}.jpg", f.read(), 'image/jpeg')
                    email_msg.send(fail_silently=True)
                    results['email_sent'] += 1
                    channels_sent_set.add('EMAIL')
                except Exception as e:
                    logger.warning(f"[HairNotice Email Warning] {e}")

        # Update HairCheckRecord
        hair_record.parent_notified = bool(channels_sent_set)
        hair_record.notification_channels = ",".join(channels_sent_set)
        hair_record.parent_notification_date = timezone.now() if channels_sent_set else None
        hair_record.reason = reason_en
        hair_record.reason_am = reason_am
        hair_record.notification_details = {
            'telegram_sent': results['telegram_sent'],
            'sms_sent': results['sms_sent'],
            'email_sent': results['email_sent'],
            'timestamp': timezone.now().isoformat()
        }
        hair_record.save(update_fields=['parent_notified', 'notification_channels', 'parent_notification_date', 'reason', 'reason_am', 'notification_details'])

        # Auto-create or link DisciplinaryIncident if prohibited
        if is_prohibited and channels_sent_set:
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
                        f"Reason: {reason_en}\n"
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
                    'status': hair_record.status,
                    'channels': list(channels_sent_set),
                    'telegram_sent': results['telegram_sent'],
                    'sms_sent': results['sms_sent'],
                    'email_sent': results['email_sent']
                }
            )

        results['success'] = bool(channels_sent_set or results['recipients_count'] > 0)
        return results
