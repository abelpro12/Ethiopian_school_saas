import re


def generate_unique_username(first_name, last_name=None, school=None, prefix=""):
    """
    Generates a clean, unique, lowercase username based on the person's first name.
    Examples:
      - First name 'Abel' -> 'abel'
      - If 'abel' is taken and last_name is 'Dereje' -> 'abel.dereje'
      - If 'abel.dereje' is taken -> 'abel1', 'abel2', etc.
    """
    from apps.accounts.models import User

    if not first_name:
        first_name = "user"

    # Clean string: keep only letters and numbers
    clean_first = re.sub(r'[^a-zA-Z0-9]', '', str(first_name).strip().lower()) or "user"
    clean_last = re.sub(r'[^a-zA-Z0-9]', '', str(last_name).strip().lower()) if last_name else ""

    base = f"{prefix}{clean_first}"

    # 1. Try first name directly: e.g. "abel"
    if not User.objects.filter(username__iexact=base).exists():
        return base

    # 2. Try first_name.last_name: e.g. "abel.dereje"
    if clean_last:
        with_last = f"{prefix}{clean_first}.{clean_last}"
        if not User.objects.filter(username__iexact=with_last).exists():
            return with_last

    # 3. Try appending sequential number: "abel1", "abel2", "abel3"...
    counter = 1
    while True:
        candidate = f"{base}{counter}"
        if not User.objects.filter(username__iexact=candidate).exists():
            return candidate
        counter += 1


def get_default_role_password(role=None):
    """
    Returns cryptographically secure initial temporary password.
    The user is flagged with must_change_password=True so they set a strong password on first login.
    """
    import secrets
    return secrets.token_urlsafe(12)


def generate_account_setup_url(request, user, invalidate_previous=False):
    """
    Generates a cryptographically signed, single-use, expiring account password setup URL.
    Does not require database schema modifications or raw credential storage.

    If invalidate_previous is True and the user is an eligible unactivated account,
    rotates the password hash to an unusable password to revoke previously issued setup tokens.
    """
    if invalidate_previous and getattr(user, 'is_activation_pending', not user.has_usable_password()):
        user.set_unusable_password()
        user.save(update_fields=['password'])

    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.contrib.auth.tokens import default_token_generator
    from django.urls import reverse

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse('setup_account_password', kwargs={'uidb64': uidb64, 'token': token})
    if request:
        return request.build_absolute_uri(path)
    return path

