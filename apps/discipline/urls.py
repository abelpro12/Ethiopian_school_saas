from django.urls import path
from . import views
from . import views_hair

app_name = 'discipline'

urlpatterns = [
    path('', views.incident_log_view, name='list'),
    path('log/', views.log_incident_view, name='log'),
    path('<int:incident_id>/', views.incident_detail_view, name='detail'),

    # AI Hair Check & Grooming System
    path('hair-check/', views_hair.hair_check_scanner_view, name='hair_check_scanner'),
    path('hair-check/analyze/', views_hair.hair_check_analyze_api, name='hair_check_analyze_api'),
    path('hair-check/dispatch/', views_hair.hair_check_dispatch_api, name='hair_check_dispatch_api'),
    path('hair-check/history/', views_hair.hair_check_history_view, name='hair_check_history'),
]

