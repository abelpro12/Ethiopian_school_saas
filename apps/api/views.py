from rest_framework import viewsets, permissions
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Grade, Section
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark
from apps.finance.models import StudentInvoice
from .serializers import (
    SchoolSerializer, AcademicYearSerializer, GradeSerializer, SectionSerializer,
    StudentProfileSerializer, AttendanceRecordSerializer, StudentMarkSerializer, StudentInvoiceSerializer
)


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Base ViewSet enforcing tenant isolation on DRF API endpoints."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        school = getattr(self.request, 'school', None)
        if not school:
            return self.queryset.none()
        return self.queryset.filter(school=school)


class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role == 'SUPER_ADMIN':
            return School.objects.all()
        return School.objects.filter(id=self.request.user.school_id)


class AcademicYearViewSet(TenantScopedViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer


class GradeViewSet(TenantScopedViewSet):
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer


class SectionViewSet(TenantScopedViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer


class StudentProfileViewSet(TenantScopedViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer


class AttendanceRecordViewSet(TenantScopedViewSet):
    queryset = AttendanceRecord.objects.all()
    serializer_class = AttendanceRecordSerializer


class StudentMarkViewSet(TenantScopedViewSet):
    queryset = StudentMark.objects.all()
    serializer_class = StudentMarkSerializer


class StudentInvoiceViewSet(TenantScopedViewSet):
    queryset = StudentInvoice.objects.all()
    serializer_class = StudentInvoiceSerializer


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login_view(request):
    """
    Authentication API Endpoint for Seattle Academy & Ethiopian School SaaS.
    Accepts { "username": "...", "password": "..." }.
    Returns JSON auth status, user details, dashboard redirect path, and JWT tokens.
    """
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({'detail': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(request, username=username, password=password)
    if user is not None:
        if user.role != 'SUPER_ADMIN' and not user.is_superuser:
            if user.school and (user.school.status == 'SUSPENDED' or not user.school.is_active):
                return Response({'detail': 'School account is suspended.'}, status=status.HTTP_403_FORBIDDEN)

        login(request, user)
        refresh = RefreshToken.for_user(user)

        role_redirect_map = {
            'SUPER_ADMIN': '/super-admin/dashboard/',
            'SCHOOL_ADMIN': '/dashboard/',
            'PRINCIPAL': '/dashboard/',
            'REGISTRAR': '/dashboard/',
            'ACCOUNTANT': '/dashboard/',
            'LIBRARIAN': '/library/dashboard/',
            'TEACHER': '/teacher/',
            'PARENT': '/parent/',
            'STUDENT': '/student/',
        }
        redirect_url = role_redirect_map.get(user.role, '/dashboard/')

        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'school': user.school.name if user.school else None,
            },
            'redirect_url': redirect_url,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)

    return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
