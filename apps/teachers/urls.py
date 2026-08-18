from django.urls import path
from . import views

app_name = 'teachers'

urlpatterns = [
    path('management/', views.management_dashboard, name='management'),
    path('assignments/', views.teacher_assignments_view, name='assignments'),
    path('homeroom/', views.homeroom_portal, name='homeroom'),
    path('subjects/', views.my_subjects, name='subjects'),
    path('assessments/<int:assignment_id>/', views.manage_marks, name='assessments'),
]
