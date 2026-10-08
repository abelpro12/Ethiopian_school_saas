import logging
import datetime
from decimal import Decimal
from django.utils import timezone
from apps.communication.models import (
    SMSTemplate,
    SMSTemplateType,
    NotificationLog,
    NotificationChannel,
    ParentMeetingRequest,
    ParentMeetingStatus,
    PaymentReminderLog,
    PaymentReminderStage,
)
from apps.notifications.services import NotificationService
from apps.parents.models import GuardianRelationship, ParentProfile

logger = logging.getLogger(__name__)

# Default templates in English and Amharic
DEFAULT_SMS_TEMPLATES = {
    SMSTemplateType.STUDENT_ABSENCE: {
        'name': 'Daily Student Absence Alert',
        'body_en': "Dear Parent, {student_name} was marked ABSENT from {school_name} on {date}. Reason: {reason}. Contact the school for questions.",
        'body_am': "ክቡር ወላጅ፣ {student_name} በ {date} ከ {school_name} ቀርተዋል:: ምክንያት: {reason}:: ጥያቄ ካለዎት እባክዎን ት/ቤቱን ያነጋግሩ::",
    },
    SMSTemplateType.PARENT_MEETING: {
        'name': 'Parent Meeting Invitation',
        'body_en': "Dear Parent, you are cordially invited to {school_name} for a {category} discussion regarding {student_name} on {meeting_date} at {meeting_time}. Location: {location}. Contact: {contact_person} ({contact_phone}).",
        'body_am': "ክቡር ወላጅ፣ ስለ {student_name} የ {category} ውይይት ለማድረግ በ {meeting_date} በ {meeting_time} ወደ {school_name} እንዲመጡ ተጋብዘዋል:: ቦታ: {location}:: አነጋጋሪ: {contact_person} ({contact_phone})::",
    },
    SMSTemplateType.PAYMENT_REMINDER: {
        'name': 'Invoice Due-Date Warning',
        'body_en': "Dear Parent, invoice #{invoice_number} for {student_name} ({amount} ETB) is due on {due_date}. Please settle timely. {school_name}.",
        'body_am': "ክቡር ወላጅ፣ የ {student_name} ደረሰኝ #{invoice_number} የ {amount} ብር ክፍያ የመጨረሻ ቀን {due_date} ነው:: እባክዎን በወቅቱ ይክፈሉ:: {school_name}::",
    },
    SMSTemplateType.PAYMENT_OVERDUE: {
        'name': 'Invoice Overdue Notice',
        'body_en': "URGENT: Invoice #{invoice_number} for {student_name} ({amount} ETB) is OVERDUE (due was {due_date}). Please settle immediately. {school_name}.",
        'body_am': "አስቸኳይ: የ {student_name} ደረሰኝ #{invoice_number} የ {amount} ብር ክፍያ ጊዜው አልፏል (የመጨረሻ ቀን {due_date} ነበር):: እባክዎን በአስቸኳይ ይክፈሉ:: {school_name}::",
    },
    SMSTemplateType.BELOW_AVERAGE_ALERT: {
        'name': 'Academic Support Alert',
        'body_en': "Notice: {student_name} has achieved {score}% in {subject_name} at {school_name}. An academic support intervention has been initiated.",
        'body_am': "ማስታወቂያ: {student_name} በ {subject_name} ትምህርት {score}% አስመዝግቧል:: የትምህርት ማሻሻያ ድጋፍ ተዘጋጅቷል:: {school_name}::",
    },
}


def ensure_default_sms_templates(school):
    """
    Ensures the school tenant has default SMS templates initialized for all core types.
    """
    for template_type, config in DEFAULT_SMS_TEMPLATES.items():
        SMSTemplate.objects.get_or_create(
            school=school,
            template_type=template_type,
            defaults={
                'name': config['name'],
                'body_en': config['body_en'],
                'body_am': config['body_am'],
                'is_active': True,
            }
        )


def render_sms_template(school, template_type, context, lang='am'):
    """
    Renders an active SMS template for the tenant with context variables.
    Falls back to default text if custom template is missing.
    """
    template = SMSTemplate.objects.filter(school=school, template_type=template_type, is_active=True).first()
    
    if not template:
        # Fallback to in-memory defaults
        defaults = DEFAULT_SMS_TEMPLATES.get(template_type)
        if not defaults:
            return ""
        raw_text = defaults.get('body_am' if lang == 'am' else 'body_en') or defaults['body_en']
    else:
        raw_text = template.body_am if lang == 'am' and template.body_am else template.body_en

    # Safe placeholder formatting
    for key, val in context.items():
        raw_text = raw_text.replace(f"{{{key}}}", str(val))
    return raw_text


def send_student_absence_alert(school, student, date, reason=None, recorded_by=None):
    """
    Sends automated SMS alert to parents when a student is marked ABSENT.
    Includes deduplication guard to prevent sending multiple SMS for the same student on the same date.
    """
    if isinstance(date, str):
        date = datetime.date.fromisoformat(date)
    date_str = date.strftime('%Y-%m-%d')

    # Guard: Deduplication token per student per date
    dedup_subject = f"ABSENCE_ALERT:{student.id}:{date_str}"
    already_sent = NotificationLog.objects.filter(
        school=school,
        subject=dedup_subject,
        channel=NotificationChannel.SMS,
        status='SENT'
    ).exists()
    if already_sent:
        logger.info(f"Absence SMS alert already sent for student {student.student_id} on {date_str}.")
        return False

    guardianships = GuardianRelationship.objects.filter(
        school=school,
        student=student
    ).select_related('parent__user')

    if not guardianships.exists():
        logger.warning(f"No registered guardians found for student {student.student_id} for absence SMS.")
        return False

    school_name = getattr(school, 'name', 'School')
    clean_reason = reason.strip() if reason and str(reason).strip() else "No reason provided"
    
    dispatched_count = 0
    for g in guardianships:
        parent = g.parent
        recipient_user = parent.user
        phone = parent.phone or getattr(recipient_user, 'phone', None)
        if not phone:
            continue

        lang = getattr(parent, 'preferred_language', 'am')
        context = {
            'student_name': student.full_name,
            'date': date_str,
            'school_name': school_name,
            'reason': clean_reason,
        }
        message_body = render_sms_template(school, SMSTemplateType.STUDENT_ABSENCE, context, lang=lang)

        # Dispatch via unified NotificationService
        sent = NotificationService.send_notification(
            school=school,
            recipient_user=recipient_user,
            channel=NotificationChannel.SMS,
            message=message_body,
            subject=dedup_subject,
            category='attendance'
        )
        if sent:
            dispatched_count += 1

    return dispatched_count > 0


def dispatch_parent_meeting_sms(meeting_request):
    """
    Dispatches automated SMS invitation to parent for a scheduled ParentMeetingRequest.
    """
    school = meeting_request.school
    student = meeting_request.student
    parent = meeting_request.parent

    if not parent:
        # Attempt to link primary parent
        primary_rel = GuardianRelationship.objects.filter(
            school=school, student=student, is_primary=True
        ).select_related('parent__user').first()
        if primary_rel:
            parent = primary_rel.parent
            meeting_request.parent = parent
            meeting_request.save(update_fields=['parent'])

    if not parent or not (parent.phone or getattr(parent.user, 'phone', None)):
        logger.warning(f"Cannot dispatch meeting SMS: Parent or phone missing for meeting {meeting_request.id}")
        return False

    phone = parent.phone or getattr(parent.user, 'phone', '')
    lang = getattr(parent, 'preferred_language', 'am')
    school_name = getattr(school, 'name', 'School')

    # Format date safely
    m_date = meeting_request.meeting_date
    if isinstance(m_date, str):
        try:
            m_date = datetime.date.fromisoformat(m_date)
        except Exception:
            pass
    date_str = m_date.strftime('%b %d, %Y') if hasattr(m_date, 'strftime') else str(m_date)

    # Format time safely
    m_time = meeting_request.meeting_time
    if isinstance(m_time, str):
        try:
            m_time = datetime.time.fromisoformat(m_time)
        except Exception:
            pass
    time_str = m_time.strftime('%I:%M %p') if hasattr(m_time, 'strftime') else str(m_time)

    context = {
        'student_name': student.full_name,
        'school_name': school_name,
        'category': meeting_request.get_category_display(),
        'meeting_date': date_str,
        'meeting_time': time_str,
        'location': meeting_request.location,
        'contact_person': meeting_request.contact_person,
        'contact_phone': meeting_request.contact_phone or phone,
    }

    message_body = render_sms_template(school, SMSTemplateType.PARENT_MEETING, context, lang=lang)

    sent = NotificationService.send_notification(
        school=school,
        recipient_user=parent.user,
        channel=NotificationChannel.SMS,
        message=message_body,
        subject=f"PARENT_MEETING:{meeting_request.id}",
        category='announcement'
    )

    if sent:
        meeting_request.sms_sent = True
        meeting_request.save(update_fields=['sms_sent'])
        return True

    return False


class PaymentReminderService:
    """
    Engine to identify unpaid/approaching/overdue invoices and dispatch multi-stage SMS alerts:
    - 7_DAYS_BEFORE
    - 3_DAYS_BEFORE
    - DUE_DATE
    - OVERDUE
    """

    @classmethod
    def run_due_date_reminders(cls, school, target_date=None):
        from apps.finance.models import StudentInvoice, InvoiceStatus

        if not target_date:
            target_date = datetime.date.today()
        elif isinstance(target_date, str):
            target_date = datetime.date.fromisoformat(target_date)

        # Unpaid, partially paid, or overdue invoices
        invoices = StudentInvoice.objects.filter(
            school=school
        ).exclude(
            status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED]
        ).select_related('student', 'academic_year')

        results = {
            'target_date': target_date.strftime('%Y-%m-%d'),
            'total_invoices_evaluated': 0,
            'reminders_dispatched': 0,
            'by_stage': {
                PaymentReminderStage.SEVEN_DAYS_BEFORE: 0,
                PaymentReminderStage.THREE_DAYS_BEFORE: 0,
                PaymentReminderStage.DUE_DATE: 0,
                PaymentReminderStage.OVERDUE: 0,
            }
        }

        school_name = getattr(school, 'name', 'School')

        for invoice in invoices:
            rem_balance = invoice.remaining_balance
            if rem_balance <= Decimal('0.00'):
                continue

            results['total_invoices_evaluated'] += 1
            days_diff = (invoice.due_date - target_date).days

            # Determine reminder stage
            stage = None
            if days_diff == 7:
                stage = PaymentReminderStage.SEVEN_DAYS_BEFORE
            elif days_diff == 3:
                stage = PaymentReminderStage.THREE_DAYS_BEFORE
            elif days_diff == 0:
                stage = PaymentReminderStage.DUE_DATE
            elif days_diff < 0:
                stage = PaymentReminderStage.OVERDUE

            if not stage:
                continue

            # Check if reminder for this stage was already logged
            already_sent = PaymentReminderLog.objects.filter(
                school=school,
                invoice=invoice,
                reminder_stage=stage
            ).exists()
            if already_sent:
                continue

            # Find parent/guardian
            guardian_rel = GuardianRelationship.objects.filter(
                school=school, student=invoice.student, is_primary=True
            ).select_related('parent__user').first()

            if not guardian_rel:
                guardian_rel = GuardianRelationship.objects.filter(
                    school=school, student=invoice.student
                ).select_related('parent__user').first()

            if not guardian_rel or not guardian_rel.parent:
                logger.warning(f"No guardian found for invoice {invoice.invoice_number}")
                continue

            parent = guardian_rel.parent
            parent_user = parent.user
            phone = parent.phone or getattr(parent_user, 'phone', '')
            if not phone:
                continue

            lang = getattr(parent, 'preferred_language', 'am')
            context = {
                'student_name': invoice.student.full_name,
                'invoice_number': invoice.invoice_number,
                'amount': f"{rem_balance:,.2f}",
                'due_date': invoice.due_date.strftime('%b %d, %Y'),
                'school_name': school_name,
            }

            template_type = SMSTemplateType.PAYMENT_OVERDUE if stage == PaymentReminderStage.OVERDUE else SMSTemplateType.PAYMENT_REMINDER
            message_body = render_sms_template(school, template_type, context, lang=lang)

            sent = NotificationService.send_notification(
                school=school,
                recipient_user=parent_user,
                channel=NotificationChannel.SMS,
                message=message_body,
                subject=f"PAYMENT_ALERT:{invoice.invoice_number}:{stage}",
                category='payment'
            )

            if sent:
                PaymentReminderLog.objects.create(
                    school=school,
                    invoice=invoice,
                    reminder_stage=stage,
                    recipient_user=parent_user,
                    recipient_phone=phone,
                    message=message_body,
                    status='SENT'
                )
                results['reminders_dispatched'] += 1
                results['by_stage'][stage] += 1

        return results
