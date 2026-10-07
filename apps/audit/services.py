from .models import AuditLog, LoginAuditLog


class AuditLogMiddleware:
    """
    Middleware to log user request IP address and session activities.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        request.client_ip = ip

        response = self.get_response(request)
        return response


class AuditService:
    @staticmethod
    def get_client_ip(request):
        """Extracts client IP address from HttpRequest."""
        if not request:
            return None
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @staticmethod
    def log_action(school, user, action: str, object_type: str = None, object_id: str = None, before_val: dict = None, after_val: dict = None, ip_address: str = None):
        """
        Creates an immutable audit log record for sensitive operations.
        """
        if not school and user and getattr(user, 'school', None):
            school = user.school

        if not school:
            return None

        try:
            return AuditLog.objects.create(
                school=school,
                user=user if getattr(user, 'is_authenticated', False) else None,
                action=action,
                object_type=object_type or '',
                object_id=str(object_id) if object_id else '',
                before_value=before_val or {},
                after_value=after_val or {},
                ip_address=ip_address
            )
        except Exception:
            return None

    @staticmethod
    def log_login(school, username_attempted: str, user=None, status: str = 'SUCCESS', ip_address: str = None, user_agent: str = None, failure_reason: str = None):
        """
        Logs an authentication attempt (success, failure, suspicious, blocked).
        """
        if not school and user and getattr(user, 'school', None):
            school = user.school

        if not school:
            from apps.tenants.models import School
            # Fallback to Seattle Academy or first active school if not resolved
            school = School.objects.filter(is_active=True).first()

        if not school:
            return None

        try:
            return LoginAuditLog.objects.create(
                school=school,
                username_attempted=username_attempted or 'Anonymous',
                user=user if getattr(user, 'is_authenticated', False) else None,
                status=status,
                ip_address=ip_address,
                user_agent=user_agent or '',
                failure_reason=failure_reason or ''
            )
        except Exception:
            return None
