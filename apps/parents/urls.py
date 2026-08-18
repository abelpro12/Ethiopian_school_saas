from django.urls import path
from . import views

app_name = 'parents'

urlpatterns = [
    path('dashboard/', views.parent_dashboard_view, name='dashboard'),
]
