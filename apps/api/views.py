from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.accounts.models import User
from apps.tenants.models import School
from apps.academics.models import AcademicYear, Grade, Section
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark
from apps.finance.models import StudentInvoice
from .permissions import IsPasswordChangeCompleted
from .serializers import (
    SchoolSerializer, AcademicYearSerializer, GradeSerializer, SectionSerializer,
    StudentProfileSerializer, AttendanceRecordSerializer, StudentMarkSerializer, StudentInvoiceSerializer
)


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Base ViewSet enforcing tenant isolation and password rotation on DRF API endpoints."""
    permission_classes = [permissions.IsAuthenticated, IsPasswordChangeCompleted]

    def get_queryset(self):
        school = getattr(self.request, 'school', None)
        if not school:
            return self.queryset.none()
        return self.queryset.filter(school=school)


class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [permissions.IsAuthenticated, IsPasswordChangeCompleted]

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
        if getattr(user, 'must_change_password', False):
            redirect_url = '/accounts/change-password/'

        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'school': user.school.name if user.school else None,
                'must_change_password': user.must_change_password,
            },
            'redirect_url': redirect_url,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_200_OK)

    return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

api_login_view.cls.allow_password_change_pending = True


@api_view(['POST'])
@throttle_classes([ScopedRateThrottle])
@permission_classes([permissions.IsAuthenticated])
def api_change_password_view(request):
    """
    Dedicated API Password Change Endpoint.
    Allows authenticated users (including those with must_change_password=True)
    to safely update their credentials, clearing the must_change_password flag.
    Protected by auth_sensitive rate limiting (5 requests/minute).
    """
    current_password = request.data.get('current_password') or request.data.get('old_password')
    new_password = request.data.get('new_password') or request.data.get('new_password1')
    confirm_password = request.data.get('confirm_password') or request.data.get('new_password2')

    if not current_password or not new_password or not confirm_password:
        return Response({
            'detail': 'Current password, new password, and confirmation are required.',
            'code': 'MISSING_FIELDS'
        }, status=status.HTTP_400_BAD_REQUEST)

    if not request.user.check_password(current_password):
        return Response({
            'detail': 'Current password is incorrect.',
            'code': 'INVALID_CURRENT_PASSWORD'
        }, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({
            'detail': 'New password and confirmation do not match.',
            'code': 'PASSWORD_MISMATCH'
        }, status=status.HTTP_400_BAD_REQUEST)

    if current_password == new_password:
        return Response({
            'detail': 'New password cannot be the same as the current password.',
            'code': 'PASSWORD_IDENTICAL'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user=request.user)
    except DjangoValidationError as exc:
        return Response({
            'detail': list(exc.messages),
            'code': 'PASSWORD_VALIDATION_FAILED'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Set new password using standard PBKDF2 hasher and clear must_change_password flag
    request.user.set_password(new_password)
    request.user.must_change_password = False
    request.user.save(update_fields=['password', 'must_change_password'])

    # Preserve session if session-authenticated
    update_session_auth_hash(request, request.user)

    # Deliberately issue fresh tokens for the authenticated user
    refresh = RefreshToken.for_user(request.user)

    return Response({
        'success': True,
        'detail': 'Password changed successfully. You may now access all features.',
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    }, status=status.HTTP_200_OK)

api_change_password_view.cls.allow_password_change_pending = True
api_change_password_view.cls.throttle_scope = 'auth_sensitive'


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['must_change_password'] = user.must_change_password
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['must_change_password'] = self.user.must_change_password
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    allow_password_change_pending = True


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM, None)
        if user_id:
            user = User.objects.filter(**{jwt_settings.USER_ID_FIELD: user_id}).first()
            if user and getattr(jwt_settings, 'CHECK_REVOKE_TOKEN', False):
                current_hash = get_md5_hash_password(user.password)
                token_hash = refresh.payload.get(jwt_settings.REVOKE_TOKEN_CLAIM)
                if token_hash != current_hash:
                    raise AuthenticationFailed(
                        {
                            'detail': _("The user's password has been changed."),
                            'code': 'password_changed',
                        },
                        code="password_changed",
                    )

        data = super().validate(attrs)
        if user_id:
            try:
                user = User.objects.filter(id=user_id).first()
                if user:
                    data['must_change_password'] = user.must_change_password
            except Exception:
                pass
        return data


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer
    allow_password_change_pending = True
