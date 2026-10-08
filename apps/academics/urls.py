from django.urls import path
from . import views
from . import views_lifecycle

app_name = 'academics'

urlpatterns = [
    path('config/', views.academics_config_view, name='config'),
    path('timetable/', views.timetable_config_view, name='timetable'),
    path('switch-year/', views.switch_academic_year_view, name='switch_year'),
    path('switch-calendar/', views.switch_calendar_preference_view, name='switch_calendar'),

    # Term & Semester Lifecycle Management
    path('lifecycle/', views_lifecycle.semester_lifecycle_dashboard, name='semester_lifecycle'),
    path('lifecycle/set-active/<int:period_id>/', views_lifecycle.set_active_semester_view, name='set_active_semester'),
    path('lifecycle/lock/<int:period_id>/', views_lifecycle.lock_semester_view, name='lock_semester'),
    path('lifecycle/reopen/<int:period_id>/', views_lifecycle.reopen_semester_view, name='reopen_semester'),
    path('lifecycle/close/<int:period_id>/', views_lifecycle.close_and_archive_semester_view, name='close_and_archive_semester'),
    path('lifecycle/rollover/', views_lifecycle.rollover_semester_view, name='rollover_semester'),
    path('lifecycle/supplementary/<int:period_id>/', views_lifecycle.schedule_supplementary_view, name='schedule_supplementary'),
    path('lifecycle/archive/<int:archive_id>/json/', views_lifecycle.archive_detail_json_view, name='archive_detail_json'),
]
