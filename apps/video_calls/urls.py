from django.urls import path
from . import views

app_name = 'video_calls'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('create/', views.create_meeting_view, name='create'),
    path('instant/', views.start_instant_call_view, name='instant'),
    path('room/<uuid:room_id>/', views.meeting_room_view, name='room'),
    path('room/<uuid:room_id>/detail/', views.meeting_detail_view, name='detail'),
    path('room/<uuid:room_id>/end/', views.end_meeting_view, name='end'),
    path('room/<uuid:room_id>/delete/', views.delete_meeting_view, name='delete'),
    path('room/<uuid:room_id>/api/attendance/', views.api_log_attendance_view, name='api_attendance'),

    
    # Public Guest Video Room Link
    path('guest/<str:token>/', views.guest_room_view, name='guest_room'),
]
