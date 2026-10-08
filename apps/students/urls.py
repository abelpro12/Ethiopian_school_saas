from django.urls import path
from . import views
from . import views_admission
from . import views_clearance

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
    path('clearance/', views_clearance.clearance_dashboard_view, name='clearance_dashboard'),
    path('clearance/initiate/', views_clearance.clearance_initiate_view, name='clearance_initiate'),
    path('clearance/<int:clearance_id>/', views_clearance.clearance_detail_view, name='clearance_detail'),
    path('clearance/<int:clearance_id>/sign/', views_clearance.clearance_sign_department_view, name='clearance_sign'),
    path('clearance/<int:clearance_id>/finalize/', views_clearance.clearance_finalize_view, name='clearance_finalize'),
    path('clearance/<int:clearance_id>/certificate/', views_clearance.clearance_certificate_view, name='clearance_certificate'),
    path('<uuid:student_id>/profile/', views.student_profile_admin_view, name='admin_profile'),
    path('profile/<uuid:student_id>/', views.student_profile_admin_view),
]


