from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SchoolViewSet, AcademicYearViewSet, GradeViewSet, SectionViewSet,
    StudentProfileViewSet, AttendanceRecordViewSet, StudentMarkViewSet, StudentInvoiceViewSet,
    api_login_view
)

router = DefaultRouter()
router.register(r'schools', SchoolViewSet, basename='api-school')
router.register(r'academic-years', AcademicYearViewSet, basename='api-academicyear')
router.register(r'grades', GradeViewSet, basename='api-grade')
router.register(r'sections', SectionViewSet, basename='api-section')
router.register(r'students', StudentProfileViewSet, basename='api-student')
router.register(r'attendance', AttendanceRecordViewSet, basename='api-attendance')
router.register(r'marks', StudentMarkViewSet, basename='api-mark')
router.register(r'invoices', StudentInvoiceViewSet, basename='api-invoice')

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # OpenAPI 3.0 Schema & Interactive Documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui-alias'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Authentication Endpoints
    path('auth/login/', api_login_view, name='api_login'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # Router Endpoints
    path('', include(router.urls)),
]
