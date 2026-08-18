from django.urls import path
from . import views

app_name = 'platform'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('schools/', views.school_list, name='school_list'),
    path('schools/provision/', views.provision_school, name='provision_school'),
    path('schools/<uuid:school_id>/', views.school_detail, name='school_detail'),
    path('schools/<uuid:school_id>/action/', views.school_action, name='school_action'),
    path('schools/<uuid:school_id>/subscription/', views.manage_school_subscription, name='manage_school_subscription'),
    path('schools/<uuid:school_id>/enter-context/', views.enter_school_context, name='enter_context'),
    path('exit-context/', views.exit_school_context, name='exit_context'),
    
    # Subscriptions & Free Trials Management
    path('subscriptions/', views.platform_subscription_management, name='subscription_management'),
    path('subscription-plans/', views.subscription_plan_list, name='subscription_plan_list'),
    path('subscription-plans/save/', views.save_subscription_plan, name='save_subscription_plan'),
    path('subscription-plans/<int:plan_id>/toggle/', views.toggle_subscription_plan, name='toggle_subscription_plan'),
]
