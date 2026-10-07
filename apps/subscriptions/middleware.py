import datetime
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus, SubscriptionPlan

class SubscriptionMiddleware:
    """
    Middleware that enforces active subscription status for tenant schools.
    Automatically synchronizes subscription expiration states and restricts operational feature access
    when a school's subscription is EXPIRED, CANCELLED, or SUSPENDED.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        school = getattr(request, 'school', None) or getattr(request, 'active_school', None)

        # Fallback to user's school if not set on request
        if not school and user and user.is_authenticated:
            school = getattr(user, 'school', None)

        if user and user.is_authenticated:
            is_super_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', None) == 'SUPER_ADMIN'
            
            if not is_super_admin and school:
                subscription = getattr(school, 'subscription', None)
                if not subscription:
                    # Auto-provision a default 14-day trial if missing
                    plan = SubscriptionPlan.objects.filter(is_active=True).first()
                    subscription = SchoolSubscription.objects.create(
                        school=school,
                        plan=plan,
                        status=SubscriptionStatus.TRIAL,
                        end_date=datetime.date.today() + datetime.timedelta(days=14),
                        price_per_student_etb=Decimal('50.00'),
                        price_per_staff_etb=Decimal('100.00'),
                        base_fee_etb=Decimal('2000.00'),
                        max_students_limit=500,
                        max_staff_limit=50,
                    )

                # Dynamically check & update status if date has expired
                subscription.sync_status()

                # Check if subscription is unusable (expired / suspended / cancelled)
                if not subscription.is_usable():
                    path = request.path
                    user_role = getattr(user, 'role', None)
                    is_admin_or_principal = user_role in ['SCHOOL_ADMIN', 'PRINCIPAL']

                    # Allowed paths for school admin/principal to renew subscription
                    allowed_admin_paths = [
                        '/logout/',
                        '/login/',
                        '/static/',
                        '/media/',
                        '/subscriptions/',
                        '/payments/',
                        '/academics/switch-calendar/'
                    ]
                    # Allowed paths for standard users (students, parents, teachers, staff)
                    allowed_user_paths = [
                        '/logout/',
                        '/login/',
                        '/static/',
                        '/media/',
                    ]

                    allowed_paths = allowed_admin_paths if is_admin_or_principal else allowed_user_paths
                    is_allowed = any(path.startswith(p) for p in allowed_paths)

                    if not is_allowed:
                        if path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                            return JsonResponse({
                                'error': 'Subscription Expired',
                                'detail': 'Your school subscription has expired. Please contact administration to renew access.'
                            }, status=403)

                        pricing_breakdown = subscription.pricing_breakdown if hasattr(subscription, 'pricing_breakdown') else {}
                        
                        return render(
                            request,
                            'auth/subscription_expired.html',
                            {
                                'school': school,
                                'subscription': subscription,
                                'is_admin_or_principal': is_admin_or_principal,
                                'pricing_breakdown': pricing_breakdown,
                            },
                            status=403
                        )

        response = self.get_response(request)
        return response

