from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from apps.accounts.models import UserRole

def super_admin_required(view_func):
    """
    Decorator for views that checks that the user is a super admin,
    redirecting to the log-in page if necessary. Raises 403 if they are logged in but not authorized.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        
        # Check explicit roles
        is_platform_admin = request.user.role == UserRole.SUPER_ADMIN or request.user.is_superuser
        
        if not is_platform_admin:
            raise PermissionDenied("You do not have permission to access the platform management portal.")
            
        return view_func(request, *args, **kwargs)
        
    return _wrapped_view

def school_context_required(view_func):
    """
    Decorator for school operational views.
    Ensures that if the user is a SUPER_ADMIN, they have explicitly entered an Active School Context.
    Returns 403 Forbidden otherwise.
    Normal school users pass through unaffected (they are validated by other means like @login_required).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
            
        if request.user.role == UserRole.SUPER_ADMIN:
            # Check if they have an active school context
            if not getattr(request, 'active_school', None):
                raise PermissionDenied("You must enter a School Context to access this operational module.")
                
        return view_func(request, *args, **kwargs)
        
    return _wrapped_view
