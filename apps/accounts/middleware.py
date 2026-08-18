"""
Force Password Change Middleware for EthioSchool SaaS.

When a user's `must_change_password` flag is True, they are redirected to
the password change page after every request until they update their password.

Security rationale:
  - Prevents students/parents from logging in with default auto-generated
    temporary passwords permanently.
  - Applies to ALL authenticated users; admins who create accounts must also
    change their own passwords if flagged.
  - Does NOT apply to:
    - Unauthenticated requests (handled by @login_required elsewhere).
    - The password change URL itself (would cause infinite redirect loop).
    - The logout URL (user must be able to log out).
    - The Django admin (admins manage their own passwords there).
    - Static / media files.
    - API endpoints (JWT-authenticated endpoints should handle this separately).
"""

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


# URLs that are always allowed regardless of must_change_password status.
EXEMPT_URL_PREFIXES = (
    '/accounts/change-password/',
    '/accounts/logout/',
    '/logout/',
    '/admin/',
    '/api/',
    '/static/',
    '/media/',
    '/__debug__/',
)


class ForcePasswordChangeMiddleware:
    """
    Redirects authenticated users with `must_change_password=True` to the
    password change page before they can access any other page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'must_change_password', False)
            and not any(request.path.startswith(prefix) for prefix in EXEMPT_URL_PREFIXES)
        ):
            return redirect('/accounts/change-password/')

        return self.get_response(request)
