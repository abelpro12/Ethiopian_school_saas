from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('pay/<int:invoice_id>/', views.record_payment_view, name='record_payment'),
    path('parent-pay/<int:invoice_id>/', views.parent_pay_view, name='parent_pay'),
    path('auth/<int:auth_id>/approve/', views.approve_manual_payment, name='approve_manual_payment'),
]
