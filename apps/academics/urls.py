from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('config/', views.academics_config_view, name='config'),
    path('timetable/', views.timetable_config_view, name='timetable'),
    path('switch-year/', views.switch_academic_year_view, name='switch_year'),
    path('switch-calendar/', views.switch_calendar_preference_view, name='switch_calendar'),
]
