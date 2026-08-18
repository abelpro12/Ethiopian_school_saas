import re
from django.core.exceptions import ValidationError

def validate_ethiopian_phone(value: str):
    """
    Validates Ethiopian phone numbers (+2519... or 09...).
    """
    pattern = r'^(\+2519|\+2517|09|07)\d{8}$'
    if not re.match(pattern, value):
        raise ValidationError("Invalid Ethiopian phone number. Must start with +2519, +2517, 09, or 07 followed by 8 digits.")
