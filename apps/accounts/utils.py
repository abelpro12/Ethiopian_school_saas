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


def get_default_role_password(role):
    """
    Returns standard initial predictable password based on user role.
    The user is flagged with must_change_password=True so they set a strong password on first login.
    """
    role_defaults = {
        'SUPER_ADMIN': 'admin123',
        'SCHOOL_ADMIN': 'admin123',
        'PRINCIPAL': 'principal123',
        'LIBRARIAN': 'librarian123',
        'TEACHER': 'teacher123',
        'STUDENT': 'student123',
        'PARENT': 'parent123',
        'REGISTRAR': 'registrar123',
        'ACCOUNTANT': 'accountant123',
        'HR_MANAGER': 'hr123',
    }
    return role_defaults.get(str(role).upper(), 'student123')

