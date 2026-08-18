from django.urls import path
from .views_admission import public_admission_form_view, application_status_view

urlpatterns = [
    path('apply/', public_admission_form_view, name='public_admission'),
    path('apply/status/', application_status_view, name='admission_status'),
]
