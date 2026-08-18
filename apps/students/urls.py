from django.urls import path
from . import views
from . import views_admission

app_name = 'students'

urlpatterns = [
    path('admissions/', views.admissions_dashboard, name='admissions'),
    path('admissions/<int:application_id>/review/', views.review_application, name='review_application'),
    path('apply/', views_admission.public_admission_form_view, name='public_admission'),
    path('apply/status/', views_admission.application_status_view, name='admission_status'),
    path('bulk-import/', views.bulk_import_students, name='bulk_import'),
    path('bulk-import/template/', views.bulk_import_template, name='bulk_import_template'),
    path('lifecycle/', views.lifecycle_dashboard, name='lifecycle'),
    path('at-risk/', views.at_risk_students, name='at_risk'),
    path('<uuid:student_id>/profile/', views.student_profile_admin_view, name='admin_profile'),
    path('profile/<uuid:student_id>/', views.student_profile_admin_view),
]


