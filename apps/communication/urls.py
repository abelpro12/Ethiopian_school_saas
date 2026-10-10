from django.urls import path
from apps.communication import views
from apps.assessments import views_sms

app_name = 'communication'

urlpatterns = [
    # Parent Meeting Requests Module
    path('parent-meetings/', views.parent_meetings_list, name='parent_meetings'),
    path('parent-meetings/create/', views.create_parent_meeting, name='create_parent_meeting'),
    path('parent-meetings/<str:meeting_id>/status/', views.update_parent_meeting_status, name='update_parent_meeting_status'),
    path('parent-meetings/<str:meeting_id>/resend-sms/', views.resend_parent_meeting_sms, name='resend_parent_meeting_sms'),

    # Configurable SMS Templates
    path('templates/', views.sms_templates_view, name='sms_templates'),

    # Payment Due-Date Reminders Engine
    path('payment-reminders/', views.payment_reminders_dashboard, name='payment_reminders'),
    path('payment-reminders/trigger/', views.trigger_payment_reminders, name='trigger_payment_reminders'),

    # Exam / Test Results SMS Dispatcher
    path('exam-results-sms/', views_sms.exam_results_sms_dashboard, name='exam_results_sms'),
    path('exam-results-sms/send/', views_sms.exam_results_sms_send_api, name='exam_results_sms_send'),

    # Report Card SMS Dispatcher
    path('report-cards-sms/', views_sms.report_cards_sms_dashboard, name='report_cards_sms'),
    path('report-cards-sms/send/', views_sms.report_cards_sms_send_api, name='report_cards_sms_send'),

    # Telegram Bot Webhook & Sync APIs
    path('telegram/sync/', views.sync_telegram_bot_api, name='sync_telegram_bot_api'),
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
]
