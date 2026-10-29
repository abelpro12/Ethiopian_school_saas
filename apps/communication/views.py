import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from apps.platform_management.decorators import school_context_required
from apps.accounts.models import User, UserRole
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.finance.models import StudentInvoice, InvoiceStatus
from apps.communication.models import (
    SMSTemplate,
    SMSTemplateType,
    ParentMeetingRequest,
    ParentMeetingCategory,
    ParentMeetingStatus,
    PaymentReminderLog,
    PaymentReminderStage,
    NotificationLog,
)
from apps.communication.services import (
    ensure_default_sms_templates,
    dispatch_parent_meeting_sms,
    PaymentReminderService,
)


def get_school(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)


@login_required
def parent_meetings_list(request):
    """
    Dashboard for all parent meeting requests across the school.
    Supports filtering by category, status, date range, and student search.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('/')

    # Check permissions (teachers, admins, principals, registrar, hr)
    allowed_roles = [
        UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL,
        UserRole.TEACHER, UserRole.REGISTRAR, UserRole.HR_MANAGER
    ]
    if request.user.role not in allowed_roles and not request.user.is_superuser:
        messages.error(request, "Access restricted to school staff and administration.")
        return redirect('/')

    category_filter = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    meetings_qs = ParentMeetingRequest.objects.filter(school=school).select_related(
        'student', 'parent__user', 'requested_by'
    )

    if category_filter:
        meetings_qs = meetings_qs.filter(category=category_filter)
    if status_filter:
        meetings_qs = meetings_qs.filter(status=status_filter)
    if search_query:
        meetings_qs = meetings_qs.filter(
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__student_id__icontains=search_query) |
            Q(contact_person__icontains=search_query) |
            Q(reason__icontains=search_query)
        )
    if date_from:
        meetings_qs = meetings_qs.filter(meeting_date__gte=date_from)
    if date_to:
        meetings_qs = meetings_qs.filter(meeting_date__lte=date_to)

    total_count = ParentMeetingRequest.objects.filter(school=school).count()
    scheduled_count = ParentMeetingRequest.objects.filter(school=school, status=ParentMeetingStatus.SCHEDULED).count()
    completed_count = ParentMeetingRequest.objects.filter(school=school, status=ParentMeetingStatus.COMPLETED).count()
    cancelled_count = ParentMeetingRequest.objects.filter(school=school, status=ParentMeetingStatus.CANCELLED).count()

    # Preload active students for the Quick Schedule modal
    students = StudentProfile.objects.filter(school=school).order_by('first_name', 'last_name')[:150]

    context = {
        'meetings': meetings_qs,
        'total_count': total_count,
        'scheduled_count': scheduled_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
        'category_choices': ParentMeetingCategory.choices,
        'status_choices': ParentMeetingStatus.choices,
        'selected_category': category_filter,
        'selected_status': status_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'students': students,
    }
    return render(request, 'communication/parent_meetings.html', context)


@login_required
def create_parent_meeting(request):
    """
    Schedules a new parent meeting and dispatches SMS if requested.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('/')

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        category = request.POST.get('category', ParentMeetingCategory.ACADEMIC)
        reason = request.POST.get('reason', '').strip()
        meeting_date = request.POST.get('meeting_date')
        meeting_time = request.POST.get('meeting_time')
        location = request.POST.get('location', 'Principal Office / Staff Room').strip()
        contact_person = request.POST.get('contact_person', request.user.get_full_name() or request.user.username).strip()
        contact_phone = request.POST.get('contact_phone', getattr(request.user, 'phone', '')).strip()
        send_sms = request.POST.get('send_sms') == 'on'

        if not student_id or not reason or not meeting_date or not meeting_time:
            messages.error(request, "All required fields (Student, Reason, Date, Time) must be provided.")
            return redirect('communication:parent_meetings')

        student = get_object_or_404(StudentProfile, id=student_id, school=school)
        primary_guardian = GuardianRelationship.objects.filter(
            school=school, student=student, is_primary=True
        ).select_related('parent').first()
        parent = primary_guardian.parent if primary_guardian else None

        meeting = ParentMeetingRequest.objects.create(
            school=school,
            student=student,
            parent=parent,
            category=category,
            reason=reason,
            meeting_date=meeting_date,
            meeting_time=meeting_time,
            location=location or "Principal Office",
            contact_person=contact_person,
            contact_phone=contact_phone,
            status=ParentMeetingStatus.SCHEDULED,
            requested_by=request.user,
        )

        sms_dispatched = False
        if send_sms:
            sms_dispatched = dispatch_parent_meeting_sms(meeting)

        from apps.audit.services import AuditService
        AuditService.log_action(
            school=school,
            user=request.user,
            action='PARENT_MEETING_SCHEDULE',
            object_type='ParentMeetingRequest',
            object_id=str(meeting.id),
            details={
                'student_name': student.full_name,
                'category': category,
                'meeting_date': str(meeting_date),
                'meeting_time': str(meeting_time),
                'sms_sent': sms_dispatched
            },
            ip_address=AuditService.get_client_ip(request)
        )

        if sms_dispatched:
            messages.success(request, f"Meeting scheduled for {student.full_name} and SMS invitation dispatched to parent!")
        else:
            messages.success(request, f"Meeting scheduled for {student.full_name} on {meeting_date}.")

        return redirect('communication:parent_meetings')

    return redirect('communication:parent_meetings')


@login_required
def update_parent_meeting_status(request, meeting_id):
    """
    Updates meeting status (COMPLETED, CANCELLED, RESCHEDULED) and records outcome notes.
    """
    school = get_school(request)
    meeting = get_object_or_404(ParentMeetingRequest, id=meeting_id, school=school)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        outcome_notes = request.POST.get('outcome_notes', '').strip()
        new_date = request.POST.get('meeting_date')
        new_time = request.POST.get('meeting_time')

        if new_status in dict(ParentMeetingStatus.choices):
            old_status = meeting.status
            meeting.status = new_status
            if outcome_notes:
                meeting.outcome_notes = outcome_notes
            if new_status == ParentMeetingStatus.RESCHEDULED and new_date and new_time:
                meeting.meeting_date = new_date
                meeting.meeting_time = new_time
                meeting.sms_sent = False
                if request.POST.get('resend_sms') == 'on':
                    dispatch_parent_meeting_sms(meeting)
            meeting.save()

            from apps.audit.services import AuditService
            AuditService.log_action(
                school=school,
                user=request.user,
                action='PARENT_MEETING_STATUS_UPDATE',
                object_type='ParentMeetingRequest',
                object_id=str(meeting.id),
                before_val={'status': old_status},
                after_val={'status': new_status, 'outcome_notes': outcome_notes},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Meeting status updated to {meeting.get_status_display()}.")

    return redirect('communication:parent_meetings')


@login_required
def resend_parent_meeting_sms(request, meeting_id):
    """
    Manual trigger to resend the SMS meeting invitation.
    """
    school = get_school(request)
    meeting = get_object_or_404(ParentMeetingRequest, id=meeting_id, school=school)
    
    sent = dispatch_parent_meeting_sms(meeting)
    if sent:
        messages.success(request, f"SMS meeting invitation sent successfully to parent of {meeting.student.full_name}.")
    else:
        messages.error(request, f"Could not dispatch SMS. Please verify parent phone number.")

    return redirect('communication:parent_meetings')


@login_required
def sms_templates_view(request):
    """
    Tenant configuration interface for bilingual SMS Templates.
    Allows administrators to customize template wording for absence alerts, parent meetings,
    and payment warnings.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('/')

    # Ensure defaults exist
    ensure_default_sms_templates(school)

    if request.method == 'POST':
        template_id = request.POST.get('template_id')
        template = get_object_or_404(SMSTemplate, id=template_id, school=school)

        template.name = request.POST.get('name', template.name).strip()
        template.body_en = request.POST.get('body_en', '').strip()
        template.body_am = request.POST.get('body_am', '').strip()
        template.is_active = request.POST.get('is_active') == 'on'
        template.save()

        from apps.audit.services import AuditService
        AuditService.log_action(
            school=school,
            user=request.user,
            action='SMS_TEMPLATE_UPDATE',
            object_type='SMSTemplate',
            object_id=str(template.id),
            details={'template_type': template.template_type, 'name': template.name, 'is_active': template.is_active},
            ip_address=AuditService.get_client_ip(request)
        )

        messages.success(request, f"SMS template '{template.name}' updated successfully.")
        return redirect('communication:sms_templates')

    templates = SMSTemplate.objects.filter(school=school).order_by('template_type')
    return render(request, 'communication/sms_templates.html', {'templates': templates})


@login_required
def payment_reminders_dashboard(request):
    """
    Dashboard for monitoring invoice due warnings and overdue notices.
    Displays metrics on approaching invoices and history of dispatched reminders.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('/')

    today = datetime.date.today()
    in7days = today + datetime.timedelta(days=7)
    in3days = today + datetime.timedelta(days=3)

    active_invoices = StudentInvoice.objects.filter(
        school=school
    ).exclude(
        status__in=[InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED]
    )

    overdue_invoices = [inv for inv in active_invoices if inv.due_date < today and inv.remaining_balance > 0]
    due_today_invoices = [inv for inv in active_invoices if inv.due_date == today and inv.remaining_balance > 0]
    in3days_invoices = [inv for inv in active_invoices if inv.due_date == in3days and inv.remaining_balance > 0]
    in7days_invoices = [inv for inv in active_invoices if inv.due_date == in7days and inv.remaining_balance > 0]

    # Recent reminder logs
    recent_logs = PaymentReminderLog.objects.filter(school=school).select_related(
        'invoice__student', 'recipient_user'
    ).order_by('-sent_at')[:50]

    context = {
        'today': today,
        'overdue_count': len(overdue_invoices),
        'due_today_count': len(due_today_invoices),
        'in3days_count': len(in3days_invoices),
        'in7days_count': len(in7days_invoices),
        'recent_logs': recent_logs,
        'total_unpaid': active_invoices.count(),
        'stages': PaymentReminderStage.choices,
    }
    return render(request, 'communication/payment_reminders.html', context)


@login_required
def trigger_payment_reminders(request):
    """
    Executes the automated PaymentReminderService to check all unpaid invoices and
    dispatch 7-day, 3-day, due-date, and overdue SMS alerts.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('communication:payment_reminders')

    results = PaymentReminderService.run_due_date_reminders(school)
    sent_count = results['reminders_dispatched']

    from apps.audit.services import AuditService
    AuditService.log_action(
        school=school,
        user=request.user,
        action='PAYMENT_REMINDERS_RUN',
        object_type='School',
        object_id=str(school.id),
        details={
            'total_evaluated': results['total_invoices_evaluated'],
            'reminders_dispatched': sent_count,
            'by_stage': results['by_stage'],
        },
        ip_address=AuditService.get_client_ip(request)
    )

    if sent_count > 0:
        stage_summary = ", ".join([f"{k}: {v}" for k, v in results['by_stage'].items() if v > 0])
        messages.success(
            request,
            f"Successfully evaluated invoices: {sent_count} automated SMS reminders dispatched ({stage_summary})."
        )
    else:
        messages.info(
            request,
            f"Evaluated {results['total_invoices_evaluated']} active invoices. No new SMS reminders were due today."
        )

    return redirect('communication:payment_reminders')


@login_required
def sync_telegram_bot_api(request):
    """
    Triggers Telegram Bot updates sync to register newly linked parents.
    Returns JSON status with count of processed messages and total linked parents.
    """
    from apps.notifications.telegram_bot import TelegramBotHandler
    from apps.communication.models import TelegramAccountLink

    school = get_school(request)
    processed = TelegramBotHandler.sync_updates()
    
    linked_qs = TelegramAccountLink.objects.filter(is_verified=True)
    if school:
        linked_qs = linked_qs.filter(school=school)
    
    return JsonResponse({
        'success': True,
        'processed_updates': processed,
        'linked_parents_count': linked_qs.count(),
        'bot_username': getattr(settings, 'TELEGRAM_BOT_USERNAME', 'Seattle_Academy_Bot')
    })


from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import json
import os
import hmac
from django.http import HttpResponse, HttpResponseForbidden
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def telegram_webhook(request):
    """
    Telegram webhook receiver for real-time parent onboarding and message processing.
    Validates X-Telegram-Bot-Api-Secret-Token when TELEGRAM_BOT_SECRET_TOKEN is configured.
    """
    if request.method == 'POST':
        secret = getattr(settings, 'TELEGRAM_BOT_SECRET_TOKEN', None) or os.environ.get('TELEGRAM_BOT_SECRET_TOKEN')
        if secret:
            token = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
            if not hmac.compare_digest(str(token), str(secret)):
                return HttpResponseForbidden('Forbidden: Invalid Telegram secret token')

        try:
            from apps.notifications.telegram_bot import TelegramBotHandler
            data = json.loads(request.body.decode('utf-8'))
            if 'message' in data:
                TelegramBotHandler.handle_incoming_message(data['message'])
            return HttpResponse('OK')
        except Exception as e:
            return HttpResponse(f'Error: {e}', status=400)
    return HttpResponse('Telegram Webhook Active')

