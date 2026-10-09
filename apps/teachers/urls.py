from django.urls import path
from . import views
from . import views_workload
from . import views_onboarding

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
    # Teacher Recruitment, Onboarding & Staff Documents (Priority 2)
    path('onboarding/', views_onboarding.onboarding_dashboard_view, name='onboarding_dashboard'),
    path('onboarding/<int:teacher_id>/stage/', views_onboarding.update_onboarding_stage_view, name='update_stage'),
    path('documents/upload/', views_onboarding.upload_staff_document_view, name='upload_document'),
    path('documents/<int:document_id>/verify/', views_onboarding.verify_staff_document_view, name='verify_document'),
    path('recruitment/vacancies/', views_onboarding.vacancies_list_view, name='vacancies_list'),
    path('recruitment/vacancies/<int:vacancy_id>/', views_onboarding.vacancy_detail_and_applications_view, name='vacancy_detail'),
    path('recruitment/applications/<int:application_id>/status/', views_onboarding.update_application_status_view, name='update_application_status'),
    path('recruitment/applications/<int:application_id>/convert/', views_onboarding.convert_candidate_view, name='convert_candidate'),
]
