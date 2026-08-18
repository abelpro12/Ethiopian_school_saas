from .models import AuditLog


class AuditLogMiddleware:
    """
    Middleware to log user request IP address and session activities.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        request.client_ip = ip

        response = self.get_response(request)
        return response


class AuditService:
    @staticmethod
    def log_action(school, user, action: str, object_type: str = None, object_id: str = None, before_val: dict = None, after_val: dict = None, ip_address: str = None):
        """
        Creates an immutable audit log record for sensitive operations.
        """
        if not school:
            return None

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
