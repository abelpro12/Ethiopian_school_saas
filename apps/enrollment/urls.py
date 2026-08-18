from django.urls import path
from . import views

app_name = 'enrollment'

urlpatterns = [
    path('rollover/', views.academic_year_rollover_view, name='academic_year_rollover'),
    path('promote/', views.bulk_promote_students_view, name='bulk_promote'),
    path('promote-students/', views.bulk_promote_students_view, name='promote_students'),
    path('period-close/', views.period_close_wizard_view, name='period_close'),
    path('semester-close/', views.period_close_wizard_view, name='semester_close'),
]

