from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied


class PasswordChangeRequiredException(PermissionDenied):
    status_code = 403
    default_detail = "Password change required before accessing API."
    default_code = "PASSWORD_CHANGE_REQUIRED"


class IsPasswordChangeCompleted(BasePermission):
    """
    Blocks authenticated users with `must_change_password=True` from accessing
    protected API business endpoints.
    """
    message = "Password change required before accessing API."
    code = "PASSWORD_CHANGE_REQUIRED"

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'must_change_password', False):
            # Check if view is exempt (e.g. password change endpoint)
            if (
                getattr(view, 'allow_password_change_pending', False) or
                getattr(getattr(view, 'cls', None), 'allow_password_change_pending', False)
            ):
                return True

            raise PermissionDenied(
                detail={
                    'detail': self.message,
                    'code': self.code
                },
                code=self.code
            )
        return True
