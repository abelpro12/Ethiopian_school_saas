import re
from django.core.exceptions import ValidationError
from utils.file_security import validate_file_upload

def validate_ethiopian_phone(phone_str: str) -> bool:
    """
    Validates Ethiopian phone format (+2519..., 09..., 07...).
    """
    if not phone_str:
        return True
    pattern = r'^(\+251|0)[97]\d{8}$'
    if not re.match(pattern, phone_str.strip()):
        raise ValidationError("Invalid Ethiopian phone number. Must start with 09, 07 or +251.")
    return True

__all__ = ['validate_file_upload', 'validate_ethiopian_phone']
