import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus

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

        if user and user.is_authenticated:
            is_super_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', None) == 'SUPER_ADMIN'
            
            if not is_super_admin and school:
                subscription = getattr(school, 'subscription', None)
                if subscription:
                    # Dynamically check & update status if date has expired
                    subscription.sync_status()

                    # Check if subscription is unusable (expired / suspended / cancelled)
                    if not subscription.is_usable():
                        path = request.path
                        # List of allowed paths for users to log out or view static assets
                        allowed_admin_paths = [
                            '/logout/',
                            '/login/',
                            '/static/',
                            '/media/',
                            '/academics/switch-calendar/'
                        ]
                        
                        is_allowed = any(path.startswith(p) for p in allowed_admin_paths)

                        if not is_allowed:
                            user_role = getattr(user, 'role', None)
                            is_admin_or_principal = user_role in ['SCHOOL_ADMIN', 'PRINCIPAL']
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
