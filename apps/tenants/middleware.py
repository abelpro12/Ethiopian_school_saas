import uuid
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from .models import School
from apps.platform_management.services import SchoolContextService


class TenantMiddleware:
    """
    Extracts tenant context from request headers, user session, or subdomain.
    Sets request.school to the active School instance or None.
    Guards against header spoofing, malformed input, and cross-tenant access.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.school = None

        user = getattr(request, 'user', None)
        is_authenticated = bool(user and user.is_authenticated)
        is_super_admin = bool(is_authenticated and (getattr(user, 'is_superuser', False) or getattr(user, 'role', None) == 'SUPER_ADMIN'))

        header_school_id = request.headers.get('X-School-ID')
        parsed_header_uuid = None

        if header_school_id is not None:
            cleaned_header = str(header_school_id).strip()
            if cleaned_header:
                try:
                    parsed_header_uuid = uuid.UUID(cleaned_header)
                except (ValueError, AttributeError, TypeError):
                    return JsonResponse(
                        {'detail': 'Malformed X-School-ID header.'},
                        status=400
                    )

        # 1. Authenticated User Resolution
        if is_authenticated:
            if is_super_admin:
                # Super Admin can legitimately switch context via X-School-ID header or session context
                if parsed_header_uuid:
                    try:
                        request.school = School.objects.get(id=parsed_header_uuid, is_active=True)
                    except (School.DoesNotExist, ValueError, ValidationError):
                        pass
                if not request.school:
                    active_school = SchoolContextService.get_active_school(request)
                    if active_school:
                        request.school = active_school
                        request.active_school = active_school
                    elif hasattr(user, 'school') and user.school:
                        request.school = user.school
            else:
                # Standard Tenant User (School Admin, Principal, Registrar, Accountant, Teacher, Student, Parent)
                # MUST ALWAYS be bound strictly to their assigned school.
                # An untrusted X-School-ID header must NEVER override user tenancy.
                if parsed_header_uuid and hasattr(user, 'school_id') and user.school_id:
                    if parsed_header_uuid != user.school_id:
                        return JsonResponse(
                            {'detail': 'Cross-tenant access prohibited.'},
                            status=403
                        )
                if hasattr(user, 'school') and user.school:
                    request.school = user.school

        # 2. Unauthenticated / Anonymous Resolution (e.g. public portal, custom subdomain)
        if not request.school and not is_authenticated:
            # Subdomain resolution
            host = request.get_host().split(':')[0]
            parts = host.split('.')
            if len(parts) > 2:
                subdomain = parts[0]
                try:
                    request.school = School.objects.get(subdomain=subdomain, is_active=True)
                except (School.DoesNotExist, ValueError, ValidationError):
                    pass

            # Optional unauthenticated header resolution for public inquiries
            if not request.school and parsed_header_uuid:
                try:
                    request.school = School.objects.get(id=parsed_header_uuid, is_active=True)
                except (School.DoesNotExist, ValueError, ValidationError):
                    pass

        # 3. School Suspension Guard: Block non-superadmin users if their school is suspended or inactive
        if not is_super_admin and request.school:
            if request.school.status == 'SUSPENDED' or not request.school.is_active:
                path = request.path
                allowed_paths = ['/static/', '/media/', '/login/', '/logout/', '/admin/']
                if not any(path.startswith(p) for p in allowed_paths):
                    if path.startswith('/api/'):
                        return JsonResponse(
                            {'detail': 'School account is suspended.'},
                            status=403
                        )
                    from django.shortcuts import render
                    return render(request, 'auth/school_suspended.html', {'school': request.school}, status=403)

        response = self.get_response(request)
        return response
