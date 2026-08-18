from django.urls import path
from . import views

app_name = 'homework'

urlpatterns = [
    path('', views.homework_list_view, name='list'),
    path('create/', views.create_homework_view, name='create'),
    path('<int:hw_id>/submit/', views.submit_homework_view, name='submit'),
    path('<int:hw_id>/detail/', views.homework_detail_view, name='detail'),
]
