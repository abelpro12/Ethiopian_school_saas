from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('', views.activity_log_view, name='activity_log'),
    path('export/', views.export_activity_log_csv, name='export_activity_csv'),
    path('export/logins/', views.export_login_log_csv, name='export_login_csv'),
    path('detail/<int:log_id>/', views.audit_detail_json, name='audit_detail_json'),
]
