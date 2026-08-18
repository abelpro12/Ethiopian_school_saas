from django.urls import path
from .views_calendar import school_calendar_view, calendar_events_json_view

urlpatterns = [
    path('', school_calendar_view, name='school_calendar'),
    path('events/json/', calendar_events_json_view, name='calendar_events_json'),
]
