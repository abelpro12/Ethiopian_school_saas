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
    ExamResultSMSLog,
    ReportCardSMSLog,
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
        'body_en': "Notice: {student_name} has achieved {score}% in {subject_name} at {school_name}. An academic support intervention ({intervention_type}) has been initiated. Scheduled: {date}.",
        'body_am': "ማስታወቂያ: {student_name} በ {subject_name} ትምህርት {score}% አስመዝግቧል:: የትምህርት ማሻሻያ ድጋፍ ({intervention_type}) ቀን: {date} ተዘጋጅቷል:: {school_name}::",
    },
    SMSTemplateType.EXAM_RESULT: {
        'name': 'Exam / Test Result Alert',
        'body_en': "Dear Parent, {student_name} scored {score}/{max_score} ({percentage}%) in {subject_name} ({test_name}) at {school_name}. Grade: {grade_letter}. Thank you.",
        'body_am': "ክቡር ወላጅ፣ {student_name} በ {subject_name} ({test_name}) ፈተና {score}/{max_score} ({percentage}%) በ {school_name} አስመዝግቧል/ለች:: ደረጃ: {grade_letter}:: እናመሰግናለን::",
    },
    SMSTemplateType.REPORT_CARD: {
        'name': 'Report Card Summary Alert',
        'body_en': "Dear Parent, {student_name}'s {period_name} Report Card at {school_name}:\nSubjects: {subjects_summary}\nTotal: {total_score} | Average: {average}% | Rank: {rank} | Grade: {grade} | Conduct: {conduct} | Status: {status}. Thank you.",
        'body_am': "ክቡር ወላጅ፣ የተማሪ {student_name} የ{period_name} የውጤት ካርድ በ{school_name}፡\nውጤቶች: {subjects_summary}\nድምር: {total_score} | አማካይ: {average}% | ደረጃ: {rank} | ውጤት: {grade} | ምግባር: {conduct} | ሁኔታ: {status}:: እናመሰግናለን::",
    },
}


def ensure_default_sms_templates(school):
    """
    Ensures the school tenant has default SMS templates initialized for all core types.
    """
    for template_type, config in DEFAULT_SMS_TEMPLATES.items():
        tpl, created = SMSTemplate.objects.get_or_create(
            school=school,
            template_type=template_type,
            defaults={
                'name': config['name'],
                'body_en': config['body_en'],
                'body_am': config['body_am'],
                'is_active': True,
            }
        )
        if not created and template_type == SMSTemplateType.REPORT_CARD:
            # Upgrade existing templates to include subjects_summary and grade
            if '{subjects_summary}' not in (tpl.body_en or '') or '{grade}' not in (tpl.body_en or ''):
                tpl.body_en = config['body_en']
                tpl.body_am = config['body_am']
                tpl.save(update_fields=['body_en', 'body_am'])
        if not created and template_type == SMSTemplateType.BELOW_AVERAGE_ALERT:
            # Upgrade existing templates to include intervention_type and date
            if '{intervention_type}' not in (tpl.body_en or ''):
                tpl.body_en = config['body_en']
                tpl.body_am = config['body_am']
                tpl.save(update_fields=['body_en', 'body_am'])


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


class ExamResultSMSService:
    """
    Engine to preview, format, and dispatch exam/test results to parents via SMS.
    Supports individual or bulk dispatch for any AssessmentComponent (e.g., Test 1, Midterm Exam).
    """

    @classmethod
    def get_component_results_for_dispatch(cls, school, component, section=None, student_ids=None):
        """
        Prepares recipient list, marks, parent contacts, delivery status, and rendered messages.
        """
        from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
        from apps.assessments.models import StudentMark

        ensure_default_sms_templates(school)
        school_name = getattr(school, 'name', 'School')
        max_m = float(component.max_marks or 100.0) if component else 100.0
        subject_name = component.subject.name if (component and component.subject) else "Subject"
        test_name = component.name if component else "Test"

        # 1. Determine target enrollments
        enrollments_qs = StudentEnrollment.objects.filter(school=school)
        if section:
            enrollments_qs = enrollments_qs.filter(section=section)
        elif component and component.subject and component.subject.grade:
            enrollments_qs = enrollments_qs.filter(grade=component.subject.grade)

        if student_ids:
            enrollments_qs = enrollments_qs.filter(student_id__in=student_ids)

        enrollments = enrollments_qs.exclude(
            status__in=[EnrollmentStatus.WITHDRAWN, EnrollmentStatus.TRANSFERRED]
        ).select_related('student__user', 'section__grade').order_by(
            'student__user__first_name', 'student__user__last_name'
        )

        # 2. Pre-fetch marks for this component
        marks = StudentMark.objects.filter(
            school=school,
            assessment_component=component,
            enrollment__in=enrollments
        ).select_related('enrollment')
        mark_by_enrollment = {m.enrollment_id: m for m in marks}

        # 3. Pre-fetch logs to indicate already-sent status
        sent_logs = ExamResultSMSLog.objects.filter(
            school=school,
            assessment_component=component,
            status='SENT'
        ).values('student_id', 'sent_at')
        sent_dict = {str(item['student_id']): item['sent_at'] for item in sent_logs}

        recipients = []
        for enr in enrollments:
            student = enr.student
            mark = mark_by_enrollment.get(enr.id)
            has_mark = mark is not None and mark.mark_value is not None

            score_val = float(mark.mark_value) if has_mark else 0.0
            pct = round((score_val / max_m * 100.0), 1) if max_m > 0 else 0.0
            letter = mark.letter_grade if (mark and mark.letter_grade) else (
                'A+' if pct >= 90 else ('A' if pct >= 83 else ('B' if pct >= 75 else ('C' if pct >= 65 else ('D' if pct >= 50 else 'F'))))
            )

            # Resolve Parent / Guardian
            guardian_rel = GuardianRelationship.objects.filter(
                school=school, student=student, is_primary=True
            ).select_related('parent__user').first()
            if not guardian_rel:
                guardian_rel = GuardianRelationship.objects.filter(
                    school=school, student=student
                ).select_related('parent__user').first()

            parent = guardian_rel.parent if guardian_rel else None
            parent_user = parent.user if parent else None

            phone = (parent.phone if parent else '') or (getattr(parent_user, 'phone', '') if parent_user else '') or (student.phone or '') or (student.emergency_contact or '')
            phone = str(phone).strip()

            lang = getattr(parent, 'preferred_language', 'am') if parent else 'am'

            context = {
                'student_name': student.full_name,
                'subject_name': subject_name,
                'test_name': test_name,
                'score': f"{score_val:g}",
                'max_score': f"{max_m:g}",
                'percentage': f"{pct:.1f}",
                'grade_letter': letter,
                'school_name': school_name,
            }

            rendered_en = render_sms_template(school, SMSTemplateType.EXAM_RESULT, context, lang='en')
            rendered_am = render_sms_template(school, SMSTemplateType.EXAM_RESULT, context, lang='am')

            student_id_str = str(student.id)
            already_sent = student_id_str in sent_dict
            last_sent_at = sent_dict[student_id_str].strftime('%b %d, %Y %H:%M') if already_sent else None

            recipients.append({
                'enrollment_id': enr.id,
                'student_id': student_id_str,
                'student_code': student.student_id,
                'student_name': student.full_name,
                'amharic_name': student.amharic_name or '',
                'section_name': enr.section.name if enr.section else '',
                'has_mark': has_mark,
                'score': score_val,
                'max_score': max_m,
                'percentage': pct,
                'letter_grade': letter,
                'parent_name': parent.user.get_full_name() or parent.user.username if (parent and parent.user) else 'No Guardian Linked',
                'parent_relationship': parent.relationship if parent else 'Guardian',
                'parent_phone': phone,
                'has_phone': bool(phone),
                'preferred_lang': lang,
                'rendered_sms_en': rendered_en,
                'rendered_sms_am': rendered_am,
                'already_sent': already_sent,
                'last_sent_at': last_sent_at,
                'mark_id': mark.id if mark else None,
            })

        return recipients

    @classmethod
    def dispatch_single_result_sms(cls, school, component, student, score_val, max_score, percentage, letter_grade, parent=None, parent_phone=None, custom_message=None, lang_override=None, sender_user=None, channels=None):
        """
        Dispatches exam result via SMS, Telegram, and/or Email to parents and creates ExamResultSMSLog.
        """
        school_name = getattr(school, 'name', 'School')
        phone = parent_phone or (parent.phone if parent else '') or (getattr(parent.user, 'phone', '') if parent and parent.user else '') or student.phone or student.emergency_contact or ''
        phone = str(phone).strip()

        active_channels = [str(c).upper().strip() for c in (channels or ['SMS']) if str(c).strip()]
        if not active_channels:
            active_channels = ['SMS']

        # Determine language & message
        lang = lang_override or getattr(parent, 'preferred_language', 'am') or 'am'
        subject_name = component.subject.name if (component and component.subject) else "Subject"
        test_name = component.name if component else "Test"

        if custom_message and str(custom_message).strip():
            context = {
                'student_name': student.full_name,
                'subject_name': subject_name,
                'test_name': test_name,
                'score': f"{score_val:g}",
                'max_score': f"{max_score:g}",
                'percentage': f"{percentage:.1f}",
                'grade_letter': letter_grade,
                'school_name': school_name,
            }
            body = str(custom_message)
            for k, v in context.items():
                body = body.replace(f"{{{k}}}", str(v))
        else:
            context = {
                'student_name': student.full_name,
                'subject_name': subject_name,
                'test_name': test_name,
                'score': f"{score_val:g}",
                'max_score': f"{max_score:g}",
                'percentage': f"{percentage:.1f}",
                'grade_letter': letter_grade,
                'school_name': school_name,
            }
            body = render_sms_template(school, SMSTemplateType.EXAM_RESULT, context, lang=lang)

        recipient_user = parent.user if parent else getattr(student, 'user', None)

        sms_sent = False
        telegram_sent = False
        email_sent = False
        failure_reason = None
        log = None

        # 1. SMS Dispatch
        if 'SMS' in active_channels:
            if not phone:
                if len(active_channels) == 1:
                    ExamResultSMSLog.objects.create(
                        school=school,
                        assessment_component=component,
                        student=student,
                        parent=parent,
                        recipient_phone='',
                        score=Decimal(str(score_val)),
                        max_score=Decimal(str(max_score)),
                        percentage=Decimal(str(percentage)),
                        letter_grade=letter_grade,
                        message="[SKIPPED: No registered parent phone number]",
                        status='NO_PHONE',
                        sent_by=sender_user
                    )
                    return {'success': False, 'status': 'NO_PHONE', 'error': 'No registered phone number for parent', 'sms_sent': False, 'telegram_sent': False, 'email_sent': False}
            else:
                sms_sent = NotificationService.send_notification(
                    school=school,
                    recipient_user=recipient_user,
                    channel=NotificationChannel.SMS,
                    message=body,
                    subject=f"EXAM_RESULT:{component.id}:{student.id}",
                    category='announcement',
                    phone_number=phone
                )
                if not sms_sent:
                    failure_reason = NotificationService.get_last_failure_reason()

                status_str = 'SENT' if sms_sent else 'FAILED'
                log_message = body if sms_sent else f"[{failure_reason or 'FAILED'}] {body}"
                log = ExamResultSMSLog.objects.create(
                    school=school,
                    assessment_component=component,
                    student=student,
                    parent=parent,
                    recipient_phone=phone,
                    score=Decimal(str(score_val)),
                    max_score=Decimal(str(max_score)),
                    percentage=Decimal(str(percentage)),
                    letter_grade=letter_grade,
                    message=log_message,
                    status=status_str,
                    sent_by=sender_user
                )

        # 2. Telegram Bot Dispatch (100% Free)
        if 'TELEGRAM' in active_channels:
            tg_body = (
                f"📊 <b>{school_name} — Exam Result Alert</b>\n\n"
                f"👤 <b>Student:</b> {student.full_name}\n"
                f"📚 <b>Subject:</b> {subject_name}\n"
                f"📝 <b>Assessment:</b> {test_name}\n"
                f"🎯 <b>Score:</b> {score_val:g} / {max_score:g} ({percentage:.1f}%)\n"
                f"🏆 <b>Grade:</b> {letter_grade}\n\n"
                f"<i>Thank you, {school_name}</i>"
            )
            telegram_sent = NotificationService.send_notification(
                school=school,
                recipient_user=recipient_user,
                channel=NotificationChannel.TELEGRAM,
                message=tg_body,
                subject=f"EXAM_RESULT_TG:{component.id}:{student.id}",
                category='announcement'
            )

        # 3. Email Dispatch (100% Free)
        if 'EMAIL' in active_channels:
            email_addr = (
                getattr(parent, 'email', None)
                or (getattr(parent.user, 'email', None) if parent and parent.user else None)
                or (getattr(student, 'email', None) if hasattr(student, 'email') else None)
                or (getattr(student.user, 'email', None) if student and student.user else None)
            )
            email_subj = f"[{school_name}] Exam Result: {student.full_name} - {subject_name} ({test_name})"
            email_body = (
                f"Dear Parent/Guardian,\n\n"
                f"Here is the assessment result for {student.full_name} at {school_name}:\n\n"
                f"  • Student: {student.full_name}\n"
                f"  • Subject: {subject_name}\n"
                f"  • Assessment: {test_name}\n"
                f"  • Score: {score_val:g} / {max_score:g} ({percentage:.1f}%)\n"
                f"  • Grade: {letter_grade}\n\n"
                f"Best regards,\n"
                f"{school_name}\n"
            )
            email_sent = NotificationService.send_notification(
                school=school,
                recipient_user=recipient_user,
                channel=NotificationChannel.EMAIL,
                message=email_body,
                subject=email_subj,
                category='announcement',
                email_address=email_addr
            )

        any_sent = sms_sent or telegram_sent or email_sent
        overall_status = 'SENT' if any_sent else ('NO_PHONE' if ('SMS' in active_channels and not phone and not any_sent) else 'FAILED')

        return {
            'success': any_sent,
            'status': overall_status,
            'phone': phone,
            'message': body,
            'log_id': log.id if log else None,
            'error': failure_reason,
            'sms_sent': sms_sent,
            'telegram_sent': telegram_sent,
            'email_sent': email_sent,
            'channels': active_channels
        }

    @classmethod
    def bulk_dispatch_results(cls, school, component, section=None, student_ids=None, custom_message=None, lang_override=None, sender_user=None, channels=None):
        """
        Bulk dispatches exam results to parents of students in a class/section via selected channels.
        """
        recipients = cls.get_component_results_for_dispatch(
            school=school,
            component=component,
            section=section,
            student_ids=student_ids
        )

        from apps.students.models import StudentProfile
        from apps.parents.models import ParentProfile

        summary = {
            'total_students': len(recipients),
            'dispatched': 0,
            'sms_dispatched': 0,
            'telegram_dispatched': 0,
            'email_dispatched': 0,
            'skipped_no_mark': 0,
            'skipped_no_phone': 0,
            'failed': 0,
            'failure_reasons': [],
            'details': []
        }

        for r in recipients:
            if not r['has_mark']:
                summary['skipped_no_mark'] += 1
                continue

            student = StudentProfile.objects.filter(id=r['student_id'], school=school).first()
            if not student:
                continue

            guardian_rel = GuardianRelationship.objects.filter(
                school=school, student=student, is_primary=True
            ).select_related('parent').first()
            if not guardian_rel:
                guardian_rel = GuardianRelationship.objects.filter(
                    school=school, student=student
                ).select_related('parent').first()
            parent = guardian_rel.parent if guardian_rel else None

            res = cls.dispatch_single_result_sms(
                school=school,
                component=component,
                student=student,
                score_val=r['score'],
                max_score=r['max_score'],
                percentage=r['percentage'],
                letter_grade=r['letter_grade'],
                parent=parent,
                parent_phone=r['parent_phone'],
                custom_message=custom_message,
                lang_override=lang_override if lang_override != 'pref' else r['preferred_lang'],
                sender_user=sender_user,
                channels=channels
            )

            if res.get('sms_sent'):
                summary['sms_dispatched'] += 1
            if res.get('telegram_sent'):
                summary['telegram_dispatched'] += 1
            if res.get('email_sent'):
                summary['email_dispatched'] += 1

            if res['status'] == 'SENT':
                summary['dispatched'] += 1
            elif res['status'] == 'NO_PHONE':
                summary['skipped_no_phone'] += 1
            else:
                summary['failed'] += 1
                if res.get('error') and res['error'] not in summary['failure_reasons']:
                    summary['failure_reasons'].append(res['error'])

            summary['details'].append({
                'student_name': student.full_name,
                'status': res['status'],
                'phone': res.get('phone', ''),
                'score': r['score'],
                'error': res.get('error'),
                'sms_sent': res.get('sms_sent', False),
                'telegram_sent': res.get('telegram_sent', False),
                'email_sent': res.get('email_sent', False)
            })

        # Audit log
        from apps.audit.services import AuditService
        AuditService.log_action(
            school=school,
            user=sender_user,
            action='EXAM_RESULT_SMS_DISPATCH',
            object_type='AssessmentComponent',
            object_id=str(component.id),
            details={
                'component_name': component.name,
                'subject_name': component.subject.name if component.subject else '',
                'section_id': section.id if section else None,
                'total_students': summary['total_students'],
                'dispatched': summary['dispatched'],
                'skipped_no_phone': summary['skipped_no_phone'],
                'failed': summary['failed']
            }
        )

        return summary


class ReportCardSMSService:
    """
    Dedicated Service for Dispatching Semester and Annual Report Card Summaries to Parents via SMS.
    Features:
    - Resolves AcademicPeriodResult or real-time grade calculations
    - Bilingual message template rendering with dynamic placeholders:
      {student_name}, {period_name}, {average}, {total_score}, {rank}, {conduct}, {status}, {school_name}
    - Resolves primary guardian phone number with student emergency contact fallback
    - Supports bulk section dispatch or individual student dispatch
    - Complete audit trail logged in ReportCardSMSLog
    """
    @classmethod
    def get_section_report_cards_for_dispatch(cls, school, section, period=None, is_annual=False):
        from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
        from apps.assessments.models import AcademicPeriodResult
        from apps.reports.views import extract_marks_for_enrollment

        ensure_default_sms_templates(school)
        school_name = getattr(school, 'name', 'School')
        period_name = "Annual Cumulative" if is_annual else (period.name if period else "Current Semester")

        # Get active enrollments in the section
        enrollments = StudentEnrollment.objects.filter(
            school=school,
            section=section,
            status=EnrollmentStatus.ACTIVE
        ).select_related('student', 'student__user', 'grade', 'section').order_by('student__first_name', 'student__last_name')

        # Academic year resolution
        ay = getattr(section, 'academic_year', None) or getattr(school, 'active_academic_year', None)
        if not ay:
            from apps.academics.models import AcademicYear
            ay = AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).first()

        # Get existing ReportCardSMSLog to identify already sent
        query_logs = ReportCardSMSLog.objects.filter(
            school=school,
            is_annual=is_annual,
            status='SENT'
        )
        if not is_annual and period:
            query_logs = query_logs.filter(period=period)
        elif is_annual and ay:
            query_logs = query_logs.filter(academic_year=ay)

        sent_dict = {str(l.student_id): l.sent_at for l in query_logs}

        # Fetch precomputed period results if available
        period_results_map = {}
        if not is_annual and period:
            p_res = AcademicPeriodResult.objects.filter(
                school=school,
                period=period,
                enrollment__section=section
            ).select_related('enrollment__student')
            for pr in p_res:
                period_results_map[pr.enrollment_id] = pr

        from apps.assessments.grading_service import GradingService
        from apps.assessments.models import StudentMark

        # Build list of raw results first so we can rank if not pre-ranked
        temp_list = []
        for enr in enrollments:
            student = enr.student
            pr = period_results_map.get(enr.id)

            subj_list = []
            scores = []

            if pr:
                avg_score = float(pr.average_score or 0)
                tot_score = float(pr.total_score or 0)
                rank = pr.section_rank
                conduct = pr.conduct_grade or 'A'
                is_published = pr.is_published

                # Extract formatted subject results from precomputed period result
                for item in (pr.formatted_results or []):
                    s_name = item.get('name', 'Subject')
                    s_disp = str(s_name).title() if str(s_name).isupper() else str(s_name)
                    s_mark = item.get('raw_score', item.get('normalized', 0))
                    try:
                        s_mark_f = float(s_mark)
                        s_str = f"{s_mark_f:g}"
                        scores.append(s_mark_f)
                    except (ValueError, TypeError):
                        s_str = str(s_mark)
                    subj_list.append(f"{s_disp}: {s_str}")
            else:
                # Calculate from extract_marks_for_enrollment
                enr_marks = extract_marks_for_enrollment(school, enr)
                for s_name, s_data in enr_marks.items():
                    s_disp = str(s_name).title() if str(s_name).isupper() else str(s_name)
                    if is_annual:
                        v = s_data.get('avg')
                    else:
                        v = s_data.get('sem1') if (period and '1' in str(period.name)) else s_data.get('sem2')
                        if v is None:
                            v = s_data.get('avg')
                    if v is not None and v != '-':
                        try:
                            vf = float(v)
                            scores.append(vf)
                            subj_list.append(f"{s_disp}: {vf:g}")
                        except (ValueError, TypeError):
                            pass

                # If still empty, check StudentMark directly
                if not subj_list:
                    marks_qs = StudentMark.objects.filter(
                        school=school, enrollment=enr
                    ).exclude(status='REVOKED').select_related('assessment_component__subject')
                    if not is_annual and period:
                        marks_qs = marks_qs.filter(assessment_component__period=period)
                    by_subj = {}
                    for m in marks_qs:
                        if m.assessment_component and m.assessment_component.subject:
                            sn = m.assessment_component.subject.name
                            by_subj.setdefault(sn, 0.0)
                            by_subj[sn] += float(m.mark_value or 0.0)
                    for sn, score_val in by_subj.items():
                        s_disp = str(sn).title() if str(sn).isupper() else str(sn)
                        scores.append(score_val)
                        subj_list.append(f"{s_disp}: {score_val:g}")

                tot_score = sum(scores)
                avg_score = round(tot_score / len(scores), 2) if scores else 0.0
                rank = None
                conduct = 'A'
                is_published = bool(scores)

            subjects_summary = ", ".join(subj_list) if subj_list else "All subjects completed"

            grade_eval = GradingService.evaluate_mark(school, avg_score, max_marks=100.0, grade=enr.grade)
            overall_grade = grade_eval.get('letter', 'A' if avg_score >= 80 else ('B' if avg_score >= 70 else ('C' if avg_score >= 60 else ('D' if avg_score >= 50 else 'F'))))

            temp_list.append({
                'enrollment': enr,
                'student': student,
                'avg_score': avg_score,
                'tot_score': tot_score,
                'rank': rank,
                'conduct': conduct,
                'is_published': is_published,
                'has_marks': bool(avg_score > 0 or tot_score > 0 or subj_list),
                'subjects_summary': subjects_summary,
                'subj_list': subj_list,
                'grade': overall_grade,
            })

        # Rank students if rank was not precomputed
        total_students = len(temp_list)
        sorted_by_avg = sorted(temp_list, key=lambda x: x['avg_score'], reverse=True)
        for idx, item in enumerate(sorted_by_avg, start=1):
            if not item['rank'] and item['has_marks']:
                item['rank'] = idx

        # Guardian resolution
        student_ids = [item['student'].id for item in temp_list]
        guardianships = GuardianRelationship.objects.filter(
            school=school,
            student_id__in=student_ids
        ).select_related('parent__user').order_by('-is_primary')

        guardian_map = {}
        for g in guardianships:
            if g.student_id not in guardian_map or g.is_primary:
                guardian_map[g.student_id] = g.parent

        recipients = []
        for item in temp_list:
            student = item['student']
            enr = item['enrollment']
            parent = guardian_map.get(student.id)

            phone = ''
            if parent:
                phone = parent.phone or (getattr(parent.user, 'phone', '') if parent.user else '')
            if not phone:
                phone = student.phone or student.emergency_contact or ''
            phone = str(phone).strip()

            lang = getattr(parent, 'preferred_language', 'am') or 'am'
            avg_val = item['avg_score']
            tot_val = item['tot_score']
            rank_val = f"{item['rank']}/{total_students}" if item['rank'] else f"-/{total_students}"
            conduct_val = item['conduct'] or 'A'
            status_val = "Promoted" if avg_val >= 50.0 else "Retained"
            status_am = "አልፏል" if avg_val >= 50.0 else "አላለፈም"
            overall_grade = item['grade']
            subjects_summary = item['subjects_summary']

            context_en = {
                'student_name': student.full_name,
                'period_name': period_name,
                'subjects_summary': subjects_summary,
                'total_score': f"{tot_val:.1f}",
                'average': f"{avg_val:.1f}",
                'rank': rank_val,
                'grade': overall_grade,
                'grade_letter': overall_grade,
                'conduct': conduct_val,
                'status': status_val,
                'school_name': school_name,
            }
            context_am = {
                'student_name': student.amharic_name or student.full_name,
                'period_name': period_name,
                'subjects_summary': subjects_summary,
                'total_score': f"{tot_val:.1f}",
                'average': f"{avg_val:.1f}",
                'rank': rank_val,
                'grade': overall_grade,
                'grade_letter': overall_grade,
                'conduct': conduct_val,
                'status': status_am,
                'school_name': school_name,
            }

            rendered_en = render_sms_template(school, SMSTemplateType.REPORT_CARD, context_en, lang='en')
            rendered_am = render_sms_template(school, SMSTemplateType.REPORT_CARD, context_am, lang='am')

            student_id_str = str(student.id)
            already_sent = student_id_str in sent_dict
            last_sent_at = sent_dict[student_id_str].strftime('%b %d, %Y %H:%M') if already_sent else None

            recipients.append({
                'enrollment_id': enr.id,
                'student_id': student_id_str,
                'student_code': student.student_id,
                'student_name': student.full_name,
                'amharic_name': student.amharic_name or '',
                'section_name': section.name,
                'average_score': avg_val,
                'total_score': tot_val,
                'rank': item['rank'],
                'rank_display': rank_val,
                'grade': overall_grade,
                'subjects_summary': subjects_summary,
                'subj_list': item['subj_list'],
                'conduct': conduct_val,
                'promotion_status': status_val,
                'promotion_status_am': status_am,
                'has_marks': item['has_marks'],
                'parent_name': parent.user.get_full_name() or parent.user.username if (parent and parent.user) else 'No Guardian Linked',
                'parent_relationship': parent.relationship if parent else 'Guardian',
                'parent_phone': phone,
                'has_phone': bool(phone),
                'preferred_lang': lang,
                'rendered_sms_en': rendered_en,
                'rendered_sms_am': rendered_am,
                'already_sent': already_sent,
                'last_sent_at': last_sent_at,
            })

        return recipients

    @classmethod
    def dispatch_single_report_card_sms(cls, school, student, period=None, is_annual=False, parent=None, parent_phone=None, average=None, total_score=None, rank=None, total_students=None, conduct=None, promotion_status=None, grade=None, subjects_summary=None, custom_message=None, lang_override=None, sender_user=None, channels=None):
        school_name = getattr(school, 'name', 'School')
        period_name = "Annual Cumulative" if is_annual else (period.name if period else "Current Semester")
        phone = parent_phone or (parent.phone if parent else '') or (getattr(parent.user, 'phone', '') if parent and parent.user else '') or student.phone or student.emergency_contact or ''
        phone = str(phone).strip()

        active_channels = [str(c).upper().strip() for c in (channels or ['SMS']) if str(c).strip()]
        if not active_channels:
            active_channels = ['SMS']

        # Academic Year reference
        academic_year = period.academic_year if period else getattr(school, 'active_academic_year', None)
        if not academic_year:
            from apps.academics.models import AcademicYear
            academic_year = AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).first()

        avg_f = float(average or 0.0)
        tot_f = float(total_score or 0.0)

        # Parse section rank integer
        sec_rank_int = None
        if isinstance(rank, int):
            sec_rank_int = rank
        elif isinstance(rank, str):
            try:
                sec_rank_int = int(rank.split('/')[0])
            except (ValueError, IndexError):
                pass

        # If total_students is missing or wrongly set to 1 while rank > 1, resolve from section count
        if (not total_students or total_students <= 1) and sec_rank_int:
            from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
            enr = StudentEnrollment.objects.filter(
                school=school, student=student, status=EnrollmentStatus.ACTIVE
            ).select_related('section').first()
            if enr and enr.section:
                sec_count = StudentEnrollment.objects.filter(
                    school=school, section=enr.section, status=EnrollmentStatus.ACTIVE
                ).count()
                if sec_count > 1:
                    total_students = sec_count

        if isinstance(rank, str) and '/' in rank:
            rank_val = rank
        elif rank and total_students:
            rank_val = f"{rank}/{total_students}"
        elif rank:
            rank_val = str(rank)
        else:
            rank_val = "N/A"

        conduct_val = conduct or 'A'
        status_val = promotion_status or ("Promoted" if avg_f >= 50.0 else "Retained")
        status_am = "አልፏል" if avg_f >= 50.0 else "አላለፈም"
        overall_grade = grade or ('A' if avg_f >= 80 else ('B' if avg_f >= 70 else ('C' if avg_f >= 60 else ('D' if avg_f >= 50 else 'F'))))
        subjs_str = subjects_summary or 'All subjects completed'

        lang = lang_override or getattr(parent, 'preferred_language', 'am') or 'am'

        context = {
            'student_name': student.amharic_name if (lang == 'am' and student.amharic_name) else student.full_name,
            'period_name': period_name,
            'subjects_summary': subjs_str,
            'total_score': f"{tot_f:.1f}",
            'average': f"{avg_f:.1f}",
            'rank': rank_val,
            'grade': overall_grade,
            'grade_letter': overall_grade,
            'conduct': conduct_val,
            'status': status_am if lang == 'am' else status_val,
            'school_name': school_name,
        }

        if custom_message and str(custom_message).strip():
            body = str(custom_message)
            for k, v in context.items():
                body = body.replace(f"{{{k}}}", str(v))
        else:
            body = render_sms_template(school, SMSTemplateType.REPORT_CARD, context, lang=lang)

        recipient_user = parent.user if parent else getattr(student, 'user', None)

        sms_sent = False
        telegram_sent = False
        email_sent = False
        failure_reason = None
        log = None

        # 1. SMS Dispatch
        if 'SMS' in active_channels:
            if not phone:
                if len(active_channels) == 1:
                    ReportCardSMSLog.objects.create(
                        school=school,
                        academic_year=academic_year,
                        period=period if not is_annual else None,
                        is_annual=is_annual,
                        student=student,
                        parent=parent,
                        recipient_phone='',
                        average_score=Decimal(str(avg_f)),
                        total_score=Decimal(str(tot_f)),
                        section_rank=sec_rank_int,
                        total_students=total_students if isinstance(total_students, int) else None,
                        conduct_grade=conduct_val,
                        promotion_status=status_val,
                        message="[SKIPPED: No registered parent phone number]",
                        status='NO_PHONE',
                        sent_by=sender_user
                    )
                    return {'success': False, 'status': 'NO_PHONE', 'error': 'No registered parent phone number', 'sms_sent': False, 'telegram_sent': False, 'email_sent': False}
            else:
                sent = NotificationService.send_notification(
                    school=school,
                    recipient_user=recipient_user,
                    channel=NotificationChannel.SMS,
                    message=body,
                    subject=f"REPORT_CARD:{period.id if period else 'ANNUAL'}:{student.id}",
                    category='announcement',
                    phone_number=phone
                )
                sms_sent = sent
                if not sent:
                    failure_reason = NotificationService.get_last_failure_reason()

                status_str = 'SENT' if sent else 'FAILED'
                log_message = body if sent else f"[{failure_reason or 'FAILED'}] {body}"
                log = ReportCardSMSLog.objects.create(
                    school=school,
                    academic_year=academic_year,
                    period=period if not is_annual else None,
                    is_annual=is_annual,
                    student=student,
                    parent=parent,
                    recipient_phone=phone,
                    average_score=Decimal(str(avg_f)),
                    total_score=Decimal(str(tot_f)),
                    section_rank=sec_rank_int,
                    total_students=total_students if isinstance(total_students, int) else None,
                    conduct_grade=conduct_val,
                    promotion_status=status_val,
                    message=log_message,
                    status=status_str,
                    sent_by=sender_user
                )

        # 2. Telegram Bot Dispatch (100% Free)
        if 'TELEGRAM' in active_channels:
            tg_body = (
                f"📊 <b>{school_name} — {period_name} Report Card</b>\n\n"
                f"👤 <b>Student:</b> {student.full_name}\n"
                f"📅 <b>Academic Year:</b> {academic_year.name if academic_year else ''}\n\n"
                f"📚 <b>Subjects:</b>\n{subjs_str}\n\n"
                f"📈 <b>Summary:</b>\n"
                f" • Total: <b>{tot_f:.1f}</b>\n"
                f" • Average: <b>{avg_f:.1f}%</b>\n"
                f" • Class Rank: <b>{rank_val}</b>\n"
                f" • Grade: <b>{overall_grade}</b>\n"
                f" • Conduct: <b>{conduct_val}</b>\n"
                f" • Status: <b>{status_am if lang == 'am' else status_val}</b>\n\n"
                f"<i>Thank you, {school_name}</i>"
            )
            telegram_sent = NotificationService.send_notification(
                school=school,
                recipient_user=recipient_user,
                channel=NotificationChannel.TELEGRAM,
                message=tg_body,
                subject=f"REPORT_CARD_TG:{period.id if period else 'ANNUAL'}:{student.id}",
                category='announcement'
            )

        # 3. Email Dispatch (100% Free)
        if 'EMAIL' in active_channels:
            email_addr = (
                getattr(parent, 'email', None)
                or (getattr(parent.user, 'email', None) if parent and parent.user else None)
                or (getattr(student, 'email', None) if hasattr(student, 'email') else None)
                or (getattr(student.user, 'email', None) if student and student.user else None)
            )
            email_subj = f"[{school_name}] Official Report Card: {student.full_name} ({period_name})"
            email_body = (
                f"Dear Parent/Guardian,\n\n"
                f"Please find below the {period_name} report card summary for {student.full_name} at {school_name}:\n\n"
                f"Student Name: {student.full_name}\n"
                f"Academic Year / Period: {academic_year.name if academic_year else ''} - {period_name}\n\n"
                f"Subject Breakdown:\n{subjs_str}\n\n"
                f"Performance Summary:\n"
                f"  • Total Score: {tot_f:.1f}\n"
                f"  • Average: {avg_f:.1f}%\n"
                f"  • Section Rank: {rank_val}\n"
                f"  • Overall Grade: {overall_grade}\n"
                f"  • Conduct: {conduct_val}\n"
                f"  • Promotion Status: {status_am if lang == 'am' else status_val}\n\n"
                f"Best regards,\n"
                f"{school_name}\n"
            )
            email_sent = NotificationService.send_notification(
                school=school,
                recipient_user=recipient_user,
                channel=NotificationChannel.EMAIL,
                message=email_body,
                subject=email_subj,
                category='announcement',
                email_address=email_addr
            )

        any_sent = sms_sent or telegram_sent or email_sent
        overall_status = 'SENT' if any_sent else ('NO_PHONE' if ('SMS' in active_channels and not phone and not any_sent) else 'FAILED')

        return {
            'success': any_sent,
            'status': overall_status,
            'phone': phone,
            'message': body,
            'log_id': log.id if log else None,
            'error': failure_reason,
            'sms_sent': sms_sent,
            'telegram_sent': telegram_sent,
            'email_sent': email_sent,
            'channels': active_channels
        }

    @classmethod
    def bulk_dispatch_report_cards(cls, school, section, period=None, is_annual=False, student_ids=None, custom_message=None, lang_override=None, sender_user=None, channels=None):
        all_section_recipients = cls.get_section_report_cards_for_dispatch(
            school=school, section=section, period=period, is_annual=is_annual
        )
        total_section_students = len(all_section_recipients)

        recipients = all_section_recipients
        if student_ids:
            target_ids = {str(sid) for sid in student_ids}
            recipients = [r for r in all_section_recipients if r['student_id'] in target_ids]

        summary = {
            'total_students': len(recipients),
            'dispatched': 0,
            'sms_dispatched': 0,
            'telegram_dispatched': 0,
            'email_dispatched': 0,
            'skipped_no_phone': 0,
            'failed': 0,
            'failure_reasons': [],
            'details': []
        }

        from apps.students.models import StudentProfile
        for r in recipients:
            student = StudentProfile.objects.filter(id=r['student_id'], school=school).first()
            if not student:
                continue

            parent = GuardianRelationship.objects.filter(
                school=school, student=student, is_primary=True
            ).select_related('parent__user').first()
            parent_profile = parent.parent if parent else None

            res = cls.dispatch_single_report_card_sms(
                school=school,
                student=student,
                period=period,
                is_annual=is_annual,
                parent=parent_profile,
                parent_phone=r['parent_phone'],
                average=r['average_score'],
                total_score=r['total_score'],
                rank=r['rank'],
                total_students=total_section_students,
                conduct=r['conduct'],
                promotion_status=r['promotion_status'],
                grade=r.get('grade'),
                subjects_summary=r.get('subjects_summary'),
                custom_message=custom_message,
                lang_override=lang_override if lang_override != 'pref' else r['preferred_lang'],
                sender_user=sender_user,
                channels=channels
            )

            if res.get('sms_sent'):
                summary['sms_dispatched'] += 1
            if res.get('telegram_sent'):
                summary['telegram_dispatched'] += 1
            if res.get('email_sent'):
                summary['email_dispatched'] += 1

            if res['status'] == 'SENT':
                summary['dispatched'] += 1
            elif res['status'] == 'NO_PHONE':
                summary['skipped_no_phone'] += 1
            else:
                summary['failed'] += 1
                if res.get('error') and res['error'] not in summary['failure_reasons']:
                    summary['failure_reasons'].append(res['error'])

            summary['details'].append({
                'student_name': student.full_name,
                'status': res['status'],
                'phone': res.get('phone', ''),
                'average': r['average_score'],
                'error': res.get('error'),
                'sms_sent': res.get('sms_sent', False),
                'telegram_sent': res.get('telegram_sent', False),
                'email_sent': res.get('email_sent', False)
            })

        from apps.audit.services import AuditService
        AuditService.log_action(
            school=school,
            user=sender_user,
            action='REPORT_CARD_SMS_DISPATCH',
            object_type='Section',
            object_id=str(section.id),
            details={
                'section_name': section.name,
                'period_name': "Annual" if is_annual else (period.name if period else "Current"),
                'total_students': summary['total_students'],
                'dispatched': summary['dispatched'],
                'skipped_no_phone': summary['skipped_no_phone'],
                'failed': summary['failed']
            }
        )

        return summary
