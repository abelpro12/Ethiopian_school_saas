from django.urls import path
from .views_calendar import (
    school_calendar_view,
    calendar_events_json_view,
    create_calendar_event_ajax,
    update_calendar_event_ajax,
    delete_calendar_event_ajax,
    generate_academic_calendar_view,
)

urlpatterns = [
    path('', school_calendar_view, name='school_calendar'),
    path('events/json/', calendar_events_json_view, name='calendar_events_json'),
    path('events/create/', create_calendar_event_ajax, name='calendar_event_create_ajax'),
    path('events/<int:event_id>/update/', update_calendar_event_ajax, name='calendar_event_update_ajax'),
    path('events/<int:event_id>/delete/', delete_calendar_event_ajax, name='calendar_event_delete_ajax'),
    path('generate/', generate_academic_calendar_view, name='generate_academic_calendar'),
]
