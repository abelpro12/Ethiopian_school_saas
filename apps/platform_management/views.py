import datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum

from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import User, UserRole
from apps.subscriptions.models import SubscriptionPlan, SchoolSubscription, SubscriptionStatus, SubscriptionPayment
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.students.models import StudentProfile
from apps.finance.models import Payment, PaymentStatus

from .decorators import super_admin_required

@super_admin_required
def dashboard(request):
    """
    Platform Super Admin Dashboard with school provisioning, metrics, subscription management,
    system health, SMS usage, platform revenue, and audit logs.
    """
    schools = School.objects.all().order_by('-created_at')
    total_schools = schools.count()
    active_schools = schools.filter(status=SchoolStatus.ACTIVE).count()
    trial_schools = schools.filter(status=SchoolStatus.TRIAL).count()
    suspended_schools = schools.filter(status=SchoolStatus.SUSPENDED).count()
    archived_schools = schools.filter(status=SchoolStatus.ARCHIVED).count()

    total_platform_students = StudentProfile.objects.count()
    total_platform_teachers = User.objects.filter(role=UserRole.TEACHER).count()
    
    total_platform_revenue = Payment.objects.filter(status=PaymentStatus.SUCCESS).aggregate(sum=Sum('amount_paid'))['sum'] or Decimal('0.00')

    # Mock ARR/MRR for demonstration
    mrr = total_platform_revenue / Decimal('12.0') if total_platform_revenue > 0 else Decimal('0.00')
    arr = total_platform_revenue

    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:15]

    return render(request, 'portals/super_admin.html', {
        'schools': schools,
        'total_schools': total_schools,
        'active_schools': active_schools,
        'trial_schools': trial_schools,
        'suspended_schools': suspended_schools,
        'archived_schools': archived_schools,
        'total_students': total_platform_students,
        'total_teachers': total_platform_teachers,
        'total_revenue': total_platform_revenue,
        'mrr': mrr,
        'arr': arr,
        'audit_logs': audit_logs,
    })

@super_admin_required
def provision_school(request):
    if request.method == 'POST':
        name = request.POST.get('name') or request.POST.get('school_name')
        subdomain = request.POST.get('subdomain') or request.POST.get('school_subdomain')
        code = request.POST.get('code') or request.POST.get('school_code')
        admin_email = request.POST.get('admin_email', '')
        region = request.POST.get('region', 'Addis Ababa')
        woreda = request.POST.get('woreda', '')
        calendar_pref = request.POST.get('calendar_preference', 'ETHIOPIAN')
        phone = request.POST.get('phone', '') or request.POST.get('admin_phone', '')

        if School.objects.filter(code=code).exists() or School.objects.filter(subdomain=subdomain).exists():
            messages.error(request, f"School with code '{code}' or subdomain '{subdomain}' already exists.")
            return redirect('platform:dashboard')

        school = School.objects.create(
            name=name,
            subdomain=subdomain,
            code=code,
            region=region,
            woreda=woreda,
            calendar_preference=calendar_pref,
            phone=phone,
            email=admin_email,
            status=SchoolStatus.ACTIVE,
            is_active=True,
        )

        import secrets
        temp_admin_pwd = secrets.token_urlsafe(10)
        admin_user = User.objects.create_user(
            username=f"admin_{subdomain}",
            email=admin_email,
            school=school,
            role=UserRole.SCHOOL_ADMIN,
            first_name="School",
            last_name="Admin",
            must_change_password=True,
        )
        admin_user.set_password(temp_admin_pwd)
        admin_user.save()

        plan_id = request.POST.get('plan_id')
        if plan_id:
            plan = SubscriptionPlan.objects.filter(id=plan_id).first()
        else:
            plan = SubscriptionPlan.objects.filter(tier='STANDARD').first()
            
        if plan:
            SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                end_date=datetime.date.today() + datetime.timedelta(days=365)
            )

        AuditService.log_action(
            school=school,
            user=request.user,
            action='SCHOOL_PROVISIONED',
            after_val={'details': f"New tenant school '{name}' ({code}) provisioned by super admin."}
        )
        messages.success(request, f"School '{name}' provisioned! Admin login: admin_{subdomain} / Temp Pass: {temp_admin_pwd} (User will be forced to set a new password on first login).")
        
    return redirect('platform:dashboard')

@super_admin_required
def school_list(request):
    schools = School.objects.all().order_by('-created_at')
    return render(request, 'platform_management/school_list.html', {'schools': schools})

@super_admin_required
def school_detail(request, school_id):
    school = get_object_or_404(School, id=school_id)
    subscription = SchoolSubscription.objects.filter(school=school, status=SubscriptionStatus.ACTIVE).first()
    
    student_count = StudentProfile.objects.filter(school=school).count()
    teacher_count = User.objects.filter(school=school, role=UserRole.TEACHER).count()
    parent_count = User.objects.filter(school=school, role=UserRole.PARENT).count()
    active_users = User.objects.filter(school=school, is_active=True).count()
    
    audit_logs = AuditLog.objects.filter(school=school).order_by('-timestamp')[:20]
    
    context = {
        'school': school,
        'subscription': subscription,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'parent_count': parent_count,
        'active_users': active_users,
        'audit_logs': audit_logs,
    }
    return render(request, 'platform_management/school_detail.html', context)




@super_admin_required
def school_action(request, school_id):
    if request.method == 'POST':
        school = get_object_or_404(School, id=school_id)
        action = request.POST.get('action') or request.POST.get('school_action_type')
        reason = request.POST.get('reason', 'No reason provided')

        if action == 'suspend':
            from .services import SchoolStatusService
            SchoolStatusService.suspend_school(school, request.user, reason)
            messages.success(request, f"School '{school.name}' has been suspended.")
        elif action == 'activate':
            from .services import SchoolStatusService
            SchoolStatusService.activate_school(school, request.user, reason)
            messages.success(request, f"School '{school.name}' has been activated.")
        elif action == 'archive':
            from .services import SchoolStatusService
            SchoolStatusService.archive_school(school, request.user, reason)
            messages.success(request, f"School '{school.name}' has been archived.")
        elif action == 'delete':
            password = request.POST.get('password', '')
            if not request.user.check_password(password):
                messages.error(request, f"Incorrect super admin password. School '{school.name}' was NOT deleted.")
            else:
                school_name = school.name
                school_code = school.code
                from apps.audit.services import AuditService
                AuditService.log_action(
                    school=None,
                    user=request.user,
                    action='SCHOOL_DELETED',
                    after_val={'name': school_name, 'code': school_code}
                )
                school.delete()
                messages.success(request, f"School '{school_name}' ({school_code}) was successfully deleted.")

    referer = request.META.get('HTTP_REFERER')
    if action == 'delete':
        return redirect('platform:school_list')
    if referer:
        return redirect(referer)
    return redirect('platform:dashboard')

@super_admin_required
def enter_school_context(request, school_id):
    if request.method == 'POST':
        school = get_object_or_404(School, id=school_id)
        from .services import SchoolContextService
        SchoolContextService.enter_school_context(request, school)
        messages.success(request, f"Now acting as {school.name} ({school.code})")
        return redirect('admin_dashboard')
    return redirect('platform:dashboard')

@super_admin_required
def exit_school_context(request):
    if request.method == 'POST':
        from .services import SchoolContextService
        SchoolContextService.exit_school_context(request)
        messages.success(request, "Exited school context. Returned to platform.")
    return redirect('platform:dashboard')


@super_admin_required
def manage_school_subscription(request, school_id):
    if request.method == 'POST':
        school = get_object_or_404(School, id=school_id)
        action_type = request.POST.get('action_type', 'custom')
        status = request.POST.get('status', 'ACTIVE')
        days_to_add = int(request.POST.get('days_to_add') or 365)
        amount_paid = Decimal(request.POST.get('amount_paid') or '0.00')
        note = request.POST.get('note', 'Super Admin manual subscription override')

        sub = getattr(school, 'subscription', None)
        if not sub:
            plan = SubscriptionPlan.objects.filter(is_active=True).first()
            if not plan:
                plan = SubscriptionPlan.objects.create(
                    name="EthioSchool SaaS Standard Subscription",
                    price_per_year_etb=Decimal('25000.00')
                )
            sub = SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                status=SubscriptionStatus.TRIAL,
                end_date=datetime.date.today() + datetime.timedelta(days=14)
            )

        if action_type == 'preset_trial_30':
            sub.status = SubscriptionStatus.TRIAL
            sub.end_date = datetime.date.today() + datetime.timedelta(days=30)
            sub.save()
            messages.success(request, f"Assigned 30-Day Free Trial to {school.name}.")
        elif action_type == 'preset_trial_90':
            sub.status = SubscriptionStatus.TRIAL
            sub.end_date = datetime.date.today() + datetime.timedelta(days=90)
            sub.save()
            messages.success(request, f"Assigned 90-Day Free Trial to {school.name}.")
        elif action_type == 'preset_free_1year':
            sub.extend_subscription(days=365)
            sub.save()
            messages.success(request, f"Granted 1-Year Free Subscription to {school.name}.")
        elif action_type == 'preset_lifetime':
            sub.status = SubscriptionStatus.ACTIVE
            sub.end_date = datetime.date.today() + datetime.timedelta(days=36500)
            sub.save()
            messages.success(request, f"Granted Lifetime Free Access to {school.name}.")
        else:
            today = datetime.date.today()
            base_date = sub.end_date if (sub.end_date and sub.end_date >= today) else today
            sub.end_date = base_date + datetime.timedelta(days=days_to_add)
            sub.status = status
            sub.save()

            if amount_paid > Decimal('0.00'):
                import uuid
                SubscriptionPayment.objects.create(
                    school=school,
                    tx_ref=f"MANUAL-{uuid.uuid4().hex[:10].upper()}",
                    amount_paid=amount_paid,
                    payment_method='MANUAL_SUPERADMIN',
                    status='SUCCESS',
                    receipt_no=f"REC-MANUAL-{uuid.uuid4().hex[:8].upper()}"
                )
            messages.success(request, f"Updated subscription for {school.name} ({sub.get_status_display()}, {sub.days_remaining}d remaining).")

        AuditService.log_action(
            school=school,
            user=request.user,
            action='SUPERADMIN_SUBSCRIPTION_OVERRIDE',
            after_val={'details': f"Super Admin modified subscription for {school.name}: Status={sub.status}, EndDate={sub.end_date}, Note={note}"}
        )

    referer = request.META.get('HTTP_REFERER')
    if referer and 'subscriptions' in referer:
        return redirect('platform:subscription_management')
    return redirect('platform:school_list')


@super_admin_required
def platform_subscription_management(request):
    """
    Dedicated Super Admin dashboard for managing all platform tenant subscriptions,
    free trials, trial countdowns, revenue metrics, and custom overrides.
    """
    status_filter = request.GET.get('status', 'ALL').upper()

    subscriptions = SchoolSubscription.objects.select_related('school', 'plan').all()

    # Metrics
    total_subs = subscriptions.count()
    active_subs_count = subscriptions.filter(status=SubscriptionStatus.ACTIVE).count()
    trial_subs_count = subscriptions.filter(status=SubscriptionStatus.TRIAL).count()
    expired_subs_count = subscriptions.filter(status__in=[SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED]).count()

    total_revenue_etb = SubscriptionPayment.objects.filter(status='SUCCESS').aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    # Status filtering
    if status_filter == 'TRIAL':
        subscriptions = subscriptions.filter(status=SubscriptionStatus.TRIAL)
    elif status_filter == 'ACTIVE':
        subscriptions = subscriptions.filter(status=SubscriptionStatus.ACTIVE)
    elif status_filter == 'EXPIRED':
        subscriptions = subscriptions.filter(status__in=[SubscriptionStatus.EXPIRED, SubscriptionStatus.SUSPENDED])

    context = {
        'subscriptions': subscriptions,
        'status_filter': status_filter,
        'total_subs': total_subs,
        'active_subs_count': active_subs_count,
        'trial_subs_count': trial_subs_count,
        'expired_subs_count': expired_subs_count,
        'total_revenue_etb': total_revenue_etb,
    }
    return render(request, 'platform_management/subscription_management.html', context)



from .models import PlatformFeatureFlag

@super_admin_required
def subscription_plan_list(request):
    plans = SubscriptionPlan.objects.all().order_by('price_per_year_etb')
    return render(request, 'platform_management/subscription_plan_list.html', {'plans': plans})

@super_admin_required
def save_subscription_plan(request):
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        name = request.POST.get('name')
        tier = request.POST.get('tier')
        max_students = request.POST.get('max_students')
        max_teachers = request.POST.get('max_teachers')
        max_sms_per_month = request.POST.get('max_sms_per_month')
        max_storage_mb = request.POST.get('max_storage_mb')
        price_per_year_etb = request.POST.get('price_per_year_etb')
        billing_cycle = request.POST.get('billing_cycle')

        if plan_id:
            plan = get_object_or_404(SubscriptionPlan, id=plan_id)
            plan.name = name
            plan.tier = tier
            plan.max_students = max_students
            plan.max_teachers = max_teachers
            plan.max_sms_per_month = max_sms_per_month
            plan.max_storage_mb = max_storage_mb
            plan.price_per_year_etb = price_per_year_etb
            plan.billing_cycle = billing_cycle
            plan.save()
            
            AuditService.log_action(
                school=None,
                user=request.user,
                action='SUBSCRIPTION_PLAN_UPDATED',
                after_val={'details': f"Subscription plan '{name}' updated."}
            )
            messages.success(request, f"Plan '{name}' updated successfully.")
        else:
            plan = SubscriptionPlan.objects.create(
                name=name,
                tier=tier,
                max_students=max_students,
                max_teachers=max_teachers,
                max_sms_per_month=max_sms_per_month,
                max_storage_mb=max_storage_mb,
                price_per_year_etb=price_per_year_etb,
                billing_cycle=billing_cycle
            )
            AuditService.log_action(
                school=None,
                user=request.user,
                action='SUBSCRIPTION_PLAN_CREATED',
                after_val={'details': f"New subscription plan '{name}' created."}
            )
            messages.success(request, f"Plan '{name}' created successfully.")
            
    return redirect('platform:subscription_plan_list')

@super_admin_required
def toggle_subscription_plan(request, plan_id):
    if request.method == 'POST':
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        plan.is_active = not plan.is_active
        plan.save()
        status = "activated" if plan.is_active else "deactivated"
        
        AuditService.log_action(
            school=None,
            user=request.user,
            action='SUBSCRIPTION_PLAN_TOGGLED',
            after_val={'details': f"Subscription plan '{plan.name}' {status}."}
        )
        messages.success(request, f"Plan '{plan.name}' {status}.")
    return redirect('platform:subscription_plan_list')
