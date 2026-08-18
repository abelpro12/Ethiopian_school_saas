from django.urls import path
from . import views

app_name = 'timetable'

urlpatterns = [
    path('manage/', views.manage_timetable, name='manage'),
    path('period-slots/', views.manage_period_slots, name='period_slots'),
    path('api/assign/', views.assign_slot_htmx, name='assign_slot'),
    path('api/remove/', views.remove_slot_htmx, name='remove_slot'),
]
