from django.urls import path
from . import views

app_name = 'discipline'

urlpatterns = [
    path('', views.incident_log_view, name='list'),
    path('log/', views.log_incident_view, name='log'),
    path('<int:incident_id>/', views.incident_detail_view, name='detail'),
]
