from rest_framework import permissions

class IsTenantScoped(permissions.BasePermission):
    """
    Enforces that request user belongs to the active tenant school.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == 'SUPER_ADMIN':
            return True
        school = getattr(request, 'school', None)
        return request.user.school_id == school.id if school else False
