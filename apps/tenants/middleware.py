from .models import School
from apps.platform_management.services import SchoolContextService
class TenantMiddleware:
    """
    Extracts tenant context from request headers, user session, or subdomain.
    Sets request.school to the active School instance or None.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.school = None

        # 1. Header resolution (API calls)
        header_school_id = request.headers.get('X-School-ID')
        if header_school_id:
            try:
                request.school = School.objects.get(id=header_school_id, is_active=True)
            except (School.DoesNotExist, ValueError):
                pass

        # 2. User profile resolution
        if not request.school and hasattr(request, 'user') and request.user.is_authenticated:
            if getattr(request.user, 'role', None) == 'SUPER_ADMIN' or getattr(request.user, 'is_superuser', False):
                active_school = SchoolContextService.get_active_school(request)
                if active_school:
                    request.school = active_school
                    request.active_school = active_school
            elif hasattr(request.user, 'school') and request.user.school:
                request.school = request.user.school

        # 3. Subdomain resolution
        if not request.school:
            host = request.get_host().split(':')[0]
            parts = host.split('.')
            if len(parts) > 2:
                subdomain = parts[0]
                try:
                    request.school = School.objects.get(subdomain=subdomain, is_active=True)
                except School.DoesNotExist:
                    pass

        # 4. School Suspension Guard: Block non-superadmin users if their school is suspended or inactive
        user = getattr(request, 'user', None)
        is_super_admin = user and user.is_authenticated and (getattr(user, 'is_superuser', False) or getattr(user, 'role', None) == 'SUPER_ADMIN')

        if not is_super_admin and request.school:
            if request.school.status == 'SUSPENDED' or not request.school.is_active:
                path = request.path
                allowed_paths = ['/static/', '/media/', '/login/', '/logout/', '/admin/']
                if not any(path.startswith(p) for p in allowed_paths):
                    from django.shortcuts import render
                    return render(request, 'auth/school_suspended.html', {'school': request.school}, status=403)

        response = self.get_response(request)
        return response
