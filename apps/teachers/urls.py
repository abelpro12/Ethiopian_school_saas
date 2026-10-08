from django.urls import path
from . import views
from . import views_workload

app_name = 'teachers'

urlpatterns = [
    path('management/', views.management_dashboard, name='management'),
    path('assignments/', views.teacher_assignments_view, name='assignments'),
    path('homeroom/', views.homeroom_portal, name='homeroom'),
    path('subjects/', views.my_subjects, name='subjects'),
    path('assessments/<int:assignment_id>/', views.manage_marks, name='assessments'),
    # Workload & Capacity Management
    path('workload/', views_workload.workload_dashboard, name='workload_dashboard'),
    path('workload/capacity/', views_workload.update_teacher_capacity, name='update_capacity'),
    path('workload/departments/', views_workload.manage_departments, name='manage_departments'),
]
