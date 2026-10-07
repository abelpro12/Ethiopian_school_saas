import csv
import json
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

from apps.accounts.models import User, UserRole
from apps.tenants.models import School
from .models import AuditLog, LoginAuditLog


def is_audit_authorized(user):
    """
    Checks if user is authorized to inspect system activity logs.
    Restricted to School Admins, Principals, Registrars, and Platform Super Admins.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, 'role', '') in [
        UserRole.SUPER_ADMIN,
        UserRole.SCHOOL_ADMIN,
        UserRole.PRINCIPAL,
        UserRole.REGISTRAR,
    ]:
        return True
    return False


@login_required
def activity_log_view(request):
    """
    Main Activity & Audit Log Dashboard.
    Provides filterable, searchable timeline of administrative actions and login attempts.
    """
    if not is_audit_authorized(request.user):
        messages.error(
            request,
            "Access Restricted: Activity and Audit logs are reserved for School Administration, Leadership, and Super Admins."
        )
        return redirect('index')

    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    
    # If superadmin has not selected school, allow picking school or fallback
    all_schools = []
    if request.user.is_superuser or request.user.role == UserRole.SUPER_ADMIN:
        all_schools = School.objects.filter(is_active=True).order_by('name')
        selected_school_id = request.GET.get('school_id')
        if selected_school_id:
            picked_school = School.objects.filter(id=selected_school_id).first()
            if picked_school:
                school = picked_school
        elif not school:
            school = School.objects.filter(code__in=['SEA', 'SEATTLE']).first() or all_schools.first()

    current_tab = request.GET.get('tab', 'activity')
    q = request.GET.get('q', '').strip()
    action_type = request.GET.get('action_type', 'ALL').strip()
    actor_id = request.GET.get('actor_id', '').strip()
    timeframe = request.GET.get('timeframe', 'all').strip()
    login_status = request.GET.get('login_status', 'ALL').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    now = timezone.now()

    # Base QuerySets
    if school:
        activity_qs = AuditLog.objects.filter(school=school).select_related('user', 'school')
        login_qs = LoginAuditLog.objects.filter(school=school).select_related('user', 'school')
    else:
        activity_qs = AuditLog.objects.all().select_related('user', 'school')
        login_qs = LoginAuditLog.objects.all().select_related('user', 'school')

    # Summary Metrics (before specific filters for accurate KPIs)
    total_activities = activity_qs.count()
    total_mark_events = activity_qs.filter(action__icontains='MARK').count()
    total_admission_events = activity_qs.filter(
        Q(action__icontains='STUDENT') | Q(action__icontains='ENROLL') | Q(action__icontains='ADMIT') | Q(action__icontains='PROMOT')
    ).count()
    total_logins = login_qs.count()
    failed_logins = login_qs.filter(status='FAILED').count()
    success_logins = login_qs.filter(status='SUCCESS').count()

    # Timeframe filtering
    def apply_time_filter(qs):
        if timeframe == 'today':
            start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return qs.filter(timestamp__gte=start_today)
        elif timeframe == 'week':
            return qs.filter(timestamp__gte=now - timedelta(days=7))
        elif timeframe == 'month':
            return qs.filter(timestamp__gte=now - timedelta(days=30))
        
        # Custom dates
        if date_from:
            try:
                qs = qs.filter(timestamp__date__gte=date_from)
            except Exception:
                pass
        if date_to:
            try:
                qs = qs.filter(timestamp__date__lte=date_to)
            except Exception:
                pass
        return qs

    activity_qs = apply_time_filter(activity_qs)
    login_qs = apply_time_filter(login_qs)

    # Activity Log Specific Filters
    if q:
        activity_qs = activity_qs.filter(
            Q(action__icontains=q) |
            Q(object_type__icontains=q) |
            Q(object_id__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(ip_address__icontains=q)
        )
        login_qs = login_qs.filter(
            Q(username_attempted__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(ip_address__icontains=q) |
            Q(failure_reason__icontains=q)
        )

    if action_type and action_type != 'ALL':
        if action_type == 'MARKS':
            activity_qs = activity_qs.filter(action__icontains='MARK')
        elif action_type == 'STUDENTS':
            activity_qs = activity_qs.filter(
                Q(action__icontains='STUDENT') | Q(action__icontains='ADMIT')
            )
        elif action_type == 'ENROLLMENT':
            activity_qs = activity_qs.filter(
                Q(action__icontains='ENROLL') | Q(action__icontains='PROMOT') | Q(action__icontains='SECTION')
            )
        elif action_type == 'FINANCE':
            activity_qs = activity_qs.filter(
                Q(action__icontains='INVOICE') | Q(action__icontains='PAYMENT') | Q(action__icontains='FEE')
            )
        elif action_type == 'CONFIG':
            activity_qs = activity_qs.filter(
                Q(action__icontains='CONFIG') | Q(action__icontains='SCHEME') | Q(action__icontains='PROVISION') | Q(action__icontains='LOCK')
            )
        else:
            activity_qs = activity_qs.filter(action__icontains=action_type)

    if actor_id:
        activity_qs = activity_qs.filter(user_id=actor_id)
        login_qs = login_qs.filter(user_id=actor_id)

    if login_status and login_status != 'ALL':
        login_qs = login_qs.filter(status=login_status)

    # Pagination
    page_number = request.GET.get('page', 1)
    
    if current_tab == 'logins':
        paginator = Paginator(login_qs.order_by('-timestamp'), 25)
        try:
            page_obj = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)
        activity_page_obj = None
        login_page_obj = page_obj
    else:
        paginator = Paginator(activity_qs.order_by('-timestamp'), 25)
        try:
            page_obj = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)
        activity_page_obj = page_obj
        login_page_obj = None

    # Available Staff/Actors for filter dropdown
    if school:
        school_actors = User.objects.filter(school=school, is_active=True).order_by('first_name', 'last_name')
    else:
        school_actors = User.objects.filter(is_active=True)[:50]

    context = {
        'school': school,
        'all_schools': all_schools,
        'current_tab': current_tab,
        'page_obj': page_obj,
        'activity_page_obj': activity_page_obj,
        'login_page_obj': login_page_obj,
        'total_activities': total_activities,
        'total_mark_events': total_mark_events,
        'total_admission_events': total_admission_events,
        'total_logins': total_logins,
        'failed_logins': failed_logins,
        'success_logins': success_logins,
        'school_actors': school_actors,
        'q': q,
        'action_type': action_type,
        'actor_id': actor_id,
        'timeframe': timeframe,
        'login_status': login_status,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'audit/activity_log.html', context)


@login_required
def export_activity_log_csv(request):
    """
    Exports filtered AuditLog records as a clean downloadable CSV file for audits/compliance.
    """
    if not is_audit_authorized(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    qs = AuditLog.objects.filter(school=school) if school else AuditLog.objects.all()
    qs = qs.select_related('user', 'school').order_by('-timestamp')

    # Apply search/category filters matching current view
    q = request.GET.get('q', '').strip()
    action_type = request.GET.get('action_type', 'ALL').strip()
    actor_id = request.GET.get('actor_id', '').strip()

    if q:
        qs = qs.filter(
            Q(action__icontains=q) |
            Q(object_type__icontains=q) |
            Q(object_id__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__first_name__icontains=q)
        )
    if action_type and action_type != 'ALL':
        if action_type == 'MARKS':
            qs = qs.filter(action__icontains='MARK')
        elif action_type == 'STUDENTS':
            qs = qs.filter(Q(action__icontains='STUDENT') | Q(action__icontains='ADMIT'))
        elif action_type == 'FINANCE':
            qs = qs.filter(Q(action__icontains='INVOICE') | Q(action__icontains='PAYMENT'))
        else:
            qs = qs.filter(action__icontains=action_type)

    if actor_id:
        qs = qs.filter(user_id=actor_id)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    school_slug = school.code if school else 'platform'
    date_str = timezone.now().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="activity_audit_log_{school_slug}_{date_str}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID',
        'Timestamp (UTC)',
        'School',
        'Actor Username',
        'Actor Full Name',
        'Role',
        'Action',
        'Object Type',
        'Object ID',
        'IP Address',
        'Before Value',
        'After Value'
    ])

    for log in qs[:5000]:
        writer.writerow([
            log.id,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.school.code if log.school else 'Platform',
            log.user.username if log.user else 'System',
            log.user.get_full_name() if log.user else 'System Process',
            getattr(log.user, 'role', 'SYSTEM') if log.user else 'SYSTEM',
            log.action,
            log.object_type,
            log.object_id,
            log.ip_address or '',
            json.dumps(log.before_value) if log.before_value else '',
            json.dumps(log.after_value) if log.after_value else '',
        ])

    return response


@login_required
def export_login_log_csv(request):
    """
    Exports filtered LoginAuditLog records as a clean downloadable CSV file.
    """
    if not is_audit_authorized(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    qs = LoginAuditLog.objects.filter(school=school) if school else LoginAuditLog.objects.all()
    qs = qs.select_related('user', 'school').order_by('-timestamp')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    school_slug = school.code if school else 'platform'
    date_str = timezone.now().strftime('%Y%m%d_%H%M')
    response['Content-Disposition'] = f'attachment; filename="login_audit_log_{school_slug}_{date_str}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'ID',
        'Timestamp (UTC)',
        'School',
        'Attempted Username',
        'Resolved User Account',
        'Status',
        'IP Address',
        'User Agent',
        'Failure Reason'
    ])

    for log in qs[:5000]:
        writer.writerow([
            log.id,
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.school.code if log.school else 'Platform',
            log.username_attempted,
            log.user.username if log.user else '',
            log.status,
            log.ip_address or '',
            log.user_agent or '',
            log.failure_reason or '',
        ])

    return response


@login_required
def audit_detail_json(request, log_id):
    """
    API endpoint returning formatted JSON data of an AuditLog entry for inspect modals.
    """
    if not is_audit_authorized(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if school:
        log = get_object_or_404(AuditLog, id=log_id, school=school)
    else:
        log = get_object_or_404(AuditLog, id=log_id)

    return JsonResponse({
        'id': log.id,
        'action': log.action,
        'object_type': log.object_type,
        'object_id': log.object_id,
        'actor_name': log.user.get_full_name() if log.user else 'System Automation',
        'actor_username': log.user.username if log.user else 'system',
        'actor_role': getattr(log.user, 'role', 'SYSTEM') if log.user else 'SYSTEM',
        'ip_address': log.ip_address or 'Unknown',
        'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'before_value': log.before_value,
        'after_value': log.after_value,
    })
