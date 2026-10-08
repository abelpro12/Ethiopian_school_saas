from django.urls import path
from . import views

app_name = 'timetable'

urlpatterns = [
    path('manage/', views.manage_timetable, name='manage'),
    path('period-slots/', views.manage_period_slots, name='period_slots'),
    path('api/assign/', views.assign_slot_htmx, name='assign_slot'),
    path('api/remove/', views.remove_slot_htmx, name='remove_slot'),
    path('api/move-or-swap/', views.move_or_swap_slot_api, name='move_or_swap_slot'),
    path('api/toggle-lock/', views.toggle_slot_lock_api, name='toggle_slot_lock'),
    path('auto-generate/', views.auto_generate_timetable_view, name='auto_generate'),
    path('export/', views.export_timetable_view, name='export'),
]
