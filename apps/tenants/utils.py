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


def get_school(request):
    """
    Resolves the active tenant/school from the request, user context, or session.
    Falls back to active school or default 'SEA' school.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None) or getattr(request, 'active_school', None)
    if not school and hasattr(request, 'session'):
        school_id = request.session.get('school_id')
        if school_id:
            from apps.schools.models import School
            school = School.objects.filter(id=school_id).first()
    if not school:
        from apps.schools.models import School
        school = School.objects.filter(code='SEA').first() or School.objects.first()
    return school
