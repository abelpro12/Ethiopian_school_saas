from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.schools.views import health_check_view, readiness_check_view
from apps.accounts.views import force_change_password, update_my_credentials

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check_view, name='health_check'),
    path('ready/', readiness_check_view, name='readiness_check'),

    # Accounts — accessible before TenantMiddleware blocks
    path('accounts/change-password/', force_change_password, name='force_change_password'),
    path('accounts/update-credentials/', update_my_credentials, name='update_my_credentials'),

    path('verify/<str:token>/', include('apps.reports.urls_verify')),
    path('reports/', include('apps.reports.urls_reports')),
    path('payments/', include('apps.payments.urls')),
    path('api/v1/', include('apps.api.urls')),
    path('academics/', include('apps.academics.urls')),
    path('students/', include('apps.students.urls', namespace='students')),
    path('teachers/', include('apps.teachers.urls', namespace='teachers')),
    path('parents/', include('apps.parents.urls', namespace='parents')),
    path('finance/', include('apps.finance.urls', namespace='finance')),
    path('enrollment/', include('apps.enrollment.urls', namespace='enrollment')),
    path('super-admin/', include('apps.platform_management.urls', namespace='platform')),
    path('subscriptions/', include('apps.subscriptions.urls', namespace='subscriptions')),
    path('', include('apps.schools.urls')),
    path('messaging/', include('apps.messaging.urls', namespace='messaging')),
    path('homework/', include('apps.homework.urls', namespace='homework')),
    path('discipline/', include('apps.discipline.urls', namespace='discipline')),
    path('library/', include('apps.library.urls', namespace='library')),
    path('calendar/', include('apps.academics.urls_calendar')),
    path('admission/', include('apps.students.urls_admission')),
    path('assessments/', include('apps.assessments.urls', namespace='assessments')),
    path('attendance/', include('apps.attendance.urls', namespace='attendance')),
    path('hr/', include('apps.hr.urls', namespace='hr')),
    path('timetable/', include('apps.timetable.urls', namespace='timetable')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
