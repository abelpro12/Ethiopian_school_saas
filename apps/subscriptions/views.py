import datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.accounts.models import UserRole, User
from apps.students.models import StudentProfile
from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus, SubscriptionPlan, SubscriptionPayment, PlanTier
from apps.subscriptions.services import SubscriptionPaymentService
from apps.platform_management.decorators import super_admin_required
from apps.tenants.models import School

@login_required
def subscription_billing_view(request):
    """
    Seat-Based Subscription Billing Portal (Price = Students Rate + Staff Rate + Base Fee).
    """
    school = getattr(request, 'school', None) or getattr(request, 'active_school', None)
    if not school:
        messages.error(request, "No active school context found.")
        if request.user.role == 'SUPER_ADMIN':
            return redirect('platform:school_list')
        return redirect('admin_dashboard')

    subscription = getattr(school, 'subscription', None)
    if not subscription:
        subscription = SchoolSubscription.objects.create(
            school=school,
            status=SubscriptionStatus.TRIAL,
            end_date=datetime.date.today() + datetime.timedelta(days=14),
            price_per_student_etb=Decimal('50.00'),
            price_per_staff_etb=Decimal('100.00'),
            base_fee_etb=Decimal('2000.00'),
            max_students_limit=500,
            max_staff_limit=50,
        )
    else:
        subscription.sync_status()

    payments = SubscriptionPayment.objects.filter(school=school).order_by('-created_at')

    # ActiveCounts
    student_count = StudentProfile.objects.filter(school=school).count()
    staff_count = User.objects.filter(
        school=school,
        role__in=[UserRole.TEACHER, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.LIBRARIAN]
    ).count()

    max_students = subscription.max_students_limit or 500
    max_staff = subscription.max_staff_limit or 50

    student_pct = min(100, int((student_count / max_students) * 100)) if max_students > 0 else 0
    staff_pct = min(100, int((staff_count / max_staff) * 100)) if max_staff > 0 else 0

    breakdown = subscription.pricing_breakdown

    context = {
        'subscription': subscription,
        'payments': payments,
        'school': school,
        'student_count': student_count,
        'staff_count': staff_count,
        'student_pct': student_pct,
        'staff_pct': staff_pct,
        'breakdown': breakdown,
    }
    return render(request, 'subscriptions/billing.html', context)


@login_required
@require_POST
def initiate_subscription_payment_view(request):
    """Handles seat-based payment initiation and instant test simulation."""
    school = getattr(request, 'school', None) or getattr(request, 'active_school', None)
    if not school:
        messages.error(request, "No active school context found.")
        return redirect('subscriptions:billing')

    sub = getattr(school, 'subscription', None)
    if not sub:
        sub = SchoolSubscription.objects.create(
            school=school,
            status=SubscriptionStatus.TRIAL,
            end_date=datetime.date.today() + datetime.timedelta(days=14)
        )

    amount_to_pay = sub.pricing_breakdown['total_annual_price']

    res = SubscriptionPaymentService.initialize_subscription_payment(school, request.user, amount=amount_to_pay)
    tx_ref = res['tx_ref']

    # Handle instant simulation for manual testing
    if request.POST.get('simulate') == '1' or request.POST.get('action') == 'renew_now':
        payment = SubscriptionPaymentService.process_subscription_webhook(tx_ref, 'SUCCESS')
        sub.status = SubscriptionStatus.ACTIVE
        sub.end_date = max(datetime.date.today(), sub.end_date or datetime.date.today()) + datetime.timedelta(days=365)
        sub.grace_period_end_date = None
        sub.save()

        messages.success(request, f"Subscription successfully renewed for 1 full year at {amount_to_pay:,.2f} ETB! (Ref: {tx_ref})")
        return redirect('subscriptions:billing')

    checkout_url = res['checkout_url']
    return redirect(checkout_url)


@login_required
def subscription_payment_callback_view(request):
    tx_ref = request.GET.get('tx_ref') or request.GET.get('trx_ref')
    status = request.GET.get('status', 'success')

    if tx_ref:
        try:
            payment = SubscriptionPaymentService.process_subscription_webhook(tx_ref, status)
            if payment.status == 'SUCCESS':
                messages.success(request, f"Payment verified! Your school subscription has been extended by 365 days. (Receipt: {payment.receipt_no})")
            else:
                messages.error(request, "Subscription payment failed or was cancelled.")
        except Exception as e:
            messages.error(request, f"Error processing payment callback: {str(e)}")

    return redirect('subscriptions:billing')


@super_admin_required
@require_POST
def super_admin_subscription_action(request):
    """Allows Super Admins to set custom pricing rates, seat limits, or override subscription status."""
    school_id = request.POST.get('school_id')
    action = request.POST.get('action')
    school = get_object_or_404(School, id=school_id)
    sub = getattr(school, 'subscription', None)

    if not sub:
        sub = SchoolSubscription.objects.create(
            school=school,
            status=SubscriptionStatus.ACTIVE,
            end_date=datetime.date.today() + datetime.timedelta(days=365)
        )

    if action == 'update_rates':
        try:
            sub.price_per_student_etb = Decimal(request.POST.get('price_per_student', '50.00'))
            sub.price_per_staff_etb = Decimal(request.POST.get('price_per_staff', '100.00'))
            sub.base_fee_etb = Decimal(request.POST.get('base_fee', '2000.00'))

            override_val = request.POST.get('custom_annual_price_override', '').strip()
            if override_val:
                sub.custom_annual_price_override = Decimal(override_val)
            else:
                sub.custom_annual_price_override = None

            sub.save()
            messages.success(request, f"Custom pricing rates updated for '{school.name}'.")
        except Exception as e:
            messages.error(request, f"Error updating rates: {str(e)}")

    elif action == 'set_status':
        new_status = request.POST.get('status')
        days = int(request.POST.get('days', '0'))
        if new_status == 'TRIAL':
            sub.status = SubscriptionStatus.TRIAL
            if days > 0:
                sub.end_date = max(datetime.date.today(), sub.end_date or datetime.date.today()) + datetime.timedelta(days=days)
            sub.save()
            messages.success(request, f"Set Trial status (+{days} days) for '{school.name}'.")
        elif new_status == 'ACTIVE':
            school.is_active = True
            school.save()
            sub.status = SubscriptionStatus.ACTIVE
            if days > 0:
                sub.end_date = max(datetime.date.today(), sub.end_date or datetime.date.today()) + datetime.timedelta(days=days)
            sub.save()
            messages.success(request, f"Set Active status (+{days} days) for '{school.name}'.")
        elif new_status == 'EXPIRED':
            sub.status = SubscriptionStatus.EXPIRED
            sub.end_date = datetime.date.today()
            sub.save()
            messages.warning(request, f"Set subscription status to EXPIRED for '{school.name}'.")
        elif new_status == 'SUSPENDED':
            school.is_active = False
            school.save()
            sub.status = SubscriptionStatus.EXPIRED
            sub.save()
            messages.warning(request, f"Suspended school and subscription for '{school.name}'.")

    elif action == 'extend_30':
        sub.extend_subscription(30)
        messages.success(request, f"Extended {school.name} subscription by 30 days.")
    elif action == 'extend_365':
        sub.extend_subscription(365)
        messages.success(request, f"Extended {school.name} subscription by 1 year (365 days).")
    elif action == 'expire_now':
        sub.end_date = datetime.date.today()
        sub.status = SubscriptionStatus.EXPIRED
        sub.save()
        messages.warning(request, f"Set {school.name} subscription to EXPIRED.")
    elif action == 'reactivate':
        school.is_active = True
        school.save()
        sub.status = SubscriptionStatus.ACTIVE
        sub.end_date = datetime.date.today() + datetime.timedelta(days=365)
        sub.save()
        messages.success(request, f"Reactivated {school.name} subscription for 1 year.")

    redirect_to = request.META.get('HTTP_REFERER') or reverse('platform:dashboard')
    return redirect(redirect_to)
