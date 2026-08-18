from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

def verify_tenant_ownership(request, obj):
    """
    Enforces object-level multi-tenant security.
    Validates that the object belongs to the same school as the requesting user.
    Raises PermissionDenied (HTTP 403) if the tenant ID does not match.
    """
    if not hasattr(request, 'school') or not request.school:
        raise PermissionDenied("Tenant context is missing from the request.")
    
    if not hasattr(obj, 'school'):
        raise PermissionDenied("The requested object is not tenant-aware.")
    
    if obj.school_id != request.school.id:
        raise PermissionDenied("Access denied. This object belongs to a different tenant.")
    
    return True
