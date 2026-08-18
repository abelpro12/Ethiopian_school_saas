from django.urls import path
from .views import chapa_webhook_view

urlpatterns = [
    path('webhook/', chapa_webhook_view, name='chapa_webhook'),
]
