import datetime
from apps.schools.models import SchoolSetting
from apps.finance.models import StudentInvoice, InvoiceStatus

def get_school_financial_setting(school, key, default=False):
    setting = SchoolSetting.objects.filter(school=school, key=key).first()
    if setting:
        return setting.value.lower() in ['true', '1', 'yes']
    return default

def check_financial_access_allowed(student, access_type='REPORT_CARD'):
    """
    Checks if student has overdue invoices and if the school restricts access for that specific type.
    access_type choices:
    - 'REPORT_CARD': Restrict report card view
    - 'EXAM_RESULT': Restrict exam result view
    - 'CERTIFICATE': Restrict certificate download
    - 'REGISTRATION': Restrict online registration
    """
    school = student.school
    
    setting_key_map = {
        'REPORT_CARD': 'restrict_report_card_for_unpaid',
        'EXAM_RESULT': 'restrict_exam_result_for_unpaid',
        'CERTIFICATE': 'restrict_certificate_download_for_unpaid',
        'REGISTRATION': 'restrict_online_registration_for_unpaid',
    }
    
    setting_key = setting_key_map.get(access_type, 'restrict_report_card_for_unpaid')
    is_restriction_enabled = get_school_financial_setting(school, setting_key, default=False)
    
    if not is_restriction_enabled:
        return True, "Access granted (restriction disabled by school)"

    has_overdue = StudentInvoice.objects.filter(
        school=school,
        student=student,
        status__in=[InvoiceStatus.UNPAID, InvoiceStatus.OVERDUE, InvoiceStatus.PARTIALLY_PAID],
        due_date__lt=datetime.date.today()
    ).exists()

    if has_overdue:
        return False, f"Access restricted due to overdue financial invoice for {access_type.replace('_', ' ').lower()}."

    return True, "Access granted"
