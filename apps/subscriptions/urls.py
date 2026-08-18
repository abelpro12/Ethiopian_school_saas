from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('billing/', views.subscription_billing_view, name='billing'),
    path('pay/', views.initiate_subscription_payment_view, name='initiate_payment'),
    path('callback/', views.subscription_payment_callback_view, name='payment_callback'),
    path('super-admin-action/', views.super_admin_subscription_action, name='super_admin_action'),
]
