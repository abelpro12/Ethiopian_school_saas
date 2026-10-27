import re
import logging
import hashlib
import ipaddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import render, redirect
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache

from apps.accounts.models import User

logger = logging.getLogger(__name__)


def _is_ip_in_trusted_proxies(ip_str, trusted_proxies):
    """Check if an IP string matches any exact IP or CIDR network in trusted_proxies."""
    if not ip_str or not trusted_proxies:
        return False
    if ip_str in trusted_proxies:
        return True
    try:
        addr = ipaddress.ip_address(ip_str)
        for entry in trusted_proxies:
            if '/' in entry:
                try:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                except ValueError:
                    continue
    except ValueError:
        return False
    return False


def get_trusted_client_ip(request):
    """
    Defensively extract and validate client IP address.
    
    Trusted Proxy Boundary & Header Sanitization:
    - Untrusted clients can spoof HTTP_X_REAL_IP and HTTP_X_FORWARDED_FOR if Gunicorn is
      reached directly or if the reverse proxy does not strip/overwrite incoming headers.
    - Only when REMOTE_ADDR matches a verified trusted proxy (SECURE_PROXY_IPS) do we
      inspect forwarded headers.
    - If REMOTE_ADDR is in SECURE_PROXY_IPS:
      If HTTP_X_REAL_IP is provided, use it (sanitized by Nginx via proxy_set_header X-Real-IP $remote_addr;).
      Otherwise, traverse HTTP_X_FORWARDED_FOR from right to left, discarding trusted proxy addresses
      until reaching the first untrusted upstream IP.
    - If REMOTE_ADDR is not in SECURE_PROXY_IPS, forwarded headers are completely ignored,
      and REMOTE_ADDR is treated as the direct client IP.
    - The resulting IP is validated against standard IPv4/IPv6 syntax.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '127.0.0.1').strip()
    trusted_proxies = getattr(settings, 'SECURE_PROXY_IPS', {'127.0.0.1', '::1'})

    client_ip = remote_addr
    if _is_ip_in_trusted_proxies(remote_addr, trusted_proxies):
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            client_ip = x_real_ip.strip()
        elif request.META.get('HTTP_X_FORWARDED_FOR'):
            entries = [x.strip() for x in request.META['HTTP_X_FORWARDED_FOR'].split(',') if x.strip()]
            for entry in reversed(entries):
                if not _is_ip_in_trusted_proxies(entry, trusted_proxies):
                    client_ip = entry
                    break

    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        client_ip = remote_addr if remote_addr else '127.0.0.1'

    return client_ip


def atomic_rate_limit_increment(cache_backend, key, timeout=900):
    """
    Atomically increment counter with timeout across both Redis and LocMemCache backends.
    Guarantees that new keys are initialized with timeout and existing keys are incremented atomically.
    Propagates backend exceptions to allow fail-closed handling.
    """
    try:
        return cache_backend.incr(key)
    except ValueError:
        if cache_backend.add(key, 1, timeout=timeout):
            return 1
        return cache_backend.incr(key)


@login_required
def force_change_password(request):
    """
    Handles the first-login password change requirement.
    Users with `must_change_password=True` are redirected here by the
    ForcePasswordChangeMiddleware until they set a new password.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
            # Keep the session alive so the user is not logged out
            update_session_auth_hash(request, user)
            messages.success(
                request,
                'Your password has been updated successfully. Welcome!'
            )
            return redirect('/')
    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'accounts/force_change_password.html', {'form': form})


@login_required
def update_my_credentials(request):
    """
    Allow logged-in users to update their own username and/or password.
    Self-service username updates are permitted if the requested username is unique.
    """
    user = request.user
    if request.method == 'POST':
        new_username = request.POST.get('username', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        updated = False

        # Username update
        if new_username and new_username != user.username:
            # Validate format: letters, numbers, underscores, hyphens, 3-30 chars
            import re
            if not re.match(r'^[a-zA-Z0-9_.-]{3,30}$', new_username):
                messages.error(request, "Username must be 3-30 characters and contain only letters, numbers, dots, hyphens, and underscores.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)

            if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                messages.error(request, f"Username '{new_username}' is already taken. Please choose another username.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)
            
            old_un = user.username
            user.username = new_username
            user.save(update_fields=['username'])
            updated = True
            messages.success(request, f"Your username was changed from '{old_un}' to '{new_username}'.")

        # Password update
        if new_password:
            if confirm_password and new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)

            try:
                validate_password(new_password, user=user)
            except DjangoValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
                referer = request.META.get('HTTP_REFERER') or '/'
                return redirect(referer)

            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)
            updated = True
            messages.success(request, "Your password was updated successfully.")

        if not updated:
            messages.info(request, "No changes were made to your account.")

    referer = request.META.get('HTTP_REFERER') or '/'
    return redirect(referer)


@never_cache
def setup_account_password(request, uidb64, token):
    """
    Secure, single-use, expiring account password setup view.
    Protected by dual-budget atomic rate limiting (IP burst + UID target limits)
    with strict input validation, attempt reservation, and trusted proxy boundary enforcement.
    """
    # 1. Strict validation of uidb64 to prevent unbounded cache key bloat / injection
    if not uidb64 or len(uidb64) > 64 or not re.fullmatch(r'^[A-Za-z0-9_-]+$', uidb64):
        messages.error(request, "This account setup or password reset link is invalid or malformed.")
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        import uuid
        try:
            uuid.UUID(str(user_id))
        except ValueError:
            if not str(user_id).isdigit():
                raise ValueError("User ID must be numeric or valid UUID")
    except (TypeError, ValueError, OverflowError):
        messages.error(request, "This account setup or password reset link is invalid or malformed.")
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    # 2. Extract client IP using trusted proxy boundary
    client_ip = get_trusted_client_ip(request)

    # 3. Construct bounded cache keys
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]
    uid_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]
    ip_key = f"ratelimit:setup_ip:{ip_hash}"
    target_key = f"ratelimit:setup_uid:{uid_hash}"

    # 4. Atomic IP burst limiter (60 requests / 15 minutes)
    try:
        ip_attempts = atomic_rate_limit_increment(cache, ip_key, timeout=900)
        if ip_attempts > 60:
            messages.error(request, "Too many requests from this network. For security, please wait 15 minutes.")
            resp = redirect('login')
            resp['Referrer-Policy'] = 'no-referrer'
            return resp
    except Exception as exc:
        logger.error(f"Rate limit cache failure on IP budget: {exc}")
        messages.error(request, "Authentication service is temporarily unavailable. Please retry in a few minutes.")
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    # 5. Atomic Target UID Attempt Reservation (5 attempts / 15 minutes)
    try:
        target_attempts = atomic_rate_limit_increment(cache, target_key, timeout=900)
        if target_attempts > 5:
            messages.error(request, "Too many password configuration attempts for this account. For security, please wait 15 minutes.")
            resp = redirect('login')
            resp['Referrer-Policy'] = 'no-referrer'
            return resp
    except Exception as exc:
        logger.error(f"Rate limit cache failure on target budget: {exc}")
        messages.error(request, "Authentication service is temporarily unavailable. Please retry in a few minutes.")
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    # 6. Retrieve User and Validate Token
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        messages.error(
            request,
            "This account setup or password reset link is invalid, expired, or has already been used. "
            "Please contact your school administrator to request a new setup link."
        )
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    if request.method == 'POST':
        new_password = (request.POST.get('new_password') or request.POST.get('password') or '').strip()
        confirm_password = (request.POST.get('confirm_password') or '').strip()

        if not new_password or not confirm_password:
            messages.error(request, "Please enter and confirm your new password.")
            resp = render(request, 'accounts/setup_password.html', {'user_obj': user, 'validlink': True})
            resp['Referrer-Policy'] = 'no-referrer'
            return resp

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            resp = render(request, 'accounts/setup_password.html', {'user_obj': user, 'validlink': True})
            resp['Referrer-Policy'] = 'no-referrer'
            return resp

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            resp = render(request, 'accounts/setup_password.html', {'user_obj': user, 'validlink': True})
            resp['Referrer-Policy'] = 'no-referrer'
            return resp

        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        # On successful configuration, clear the target attempt reservation counter
        try:
            cache.delete(target_key)
        except Exception:
            pass

        messages.success(
            request,
            f"Your password has been successfully configured, {user.first_name or user.username}! You may now log in."
        )
        resp = redirect('login')
        resp['Referrer-Policy'] = 'no-referrer'
        return resp

    resp = render(request, 'accounts/setup_password.html', {'user_obj': user, 'validlink': True})
    resp['Referrer-Policy'] = 'no-referrer'
    return resp
