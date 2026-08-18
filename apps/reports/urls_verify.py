from django.urls import path
from .views import verify_document_view

urlpatterns = [
    path('', verify_document_view, name='public_verify_document'),
]
