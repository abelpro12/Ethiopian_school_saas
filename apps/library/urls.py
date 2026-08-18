from django.urls import path
from . import views

app_name = 'library'

urlpatterns = [
    path('', views.library_catalog_view, name='catalog'),
    path('dashboard/', views.borrow_dashboard_view, name='dashboard'),
    path('add/', views.add_book_view, name='add_book'),
    path('edit/<int:book_id>/', views.edit_book_view, name='edit_book'),
    path('delete/<int:book_id>/', views.delete_book_view, name='delete_book'),
]
