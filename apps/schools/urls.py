from django.urls import path
from .views import (
    index_view, login_view, logout_view, admin_dashboard,
    teacher_portal, parent_portal, student_portal,
    initiate_chapa_payment_view, user_management_view, portal_selectors_api, centralized_search_api,
    seattle_academy_website_view, seattle_academy_login_view, seattle_academy_about_view, seattle_academy_news_gallery_view,
    manage_news_view, manage_gallery_view, seattle_academy_contact_api, manage_contact_messages_view,
    id_card_generator_view, verify_id_card_view, upload_id_card_photo_view
)
from apps.parents.views import parent_dashboard_view
from apps.students.views import student_dashboard_view

urlpatterns = [
    path('', index_view, name='index'),
    path('seattle-academy/', seattle_academy_website_view, name='seattle_academy_home'),
    path('seattle-academy/about/', seattle_academy_about_view, name='seattle_academy_about'),
    path('seattle-academy/login/', seattle_academy_login_view, name='seattle_academy_login'),
    path('seattle-academy/news-events/', seattle_academy_news_gallery_view, name='seattle_academy_news_gallery'),
    path('seattle-academy/contact-api/', seattle_academy_contact_api, name='seattle_academy_contact_api'),

    path('login/', login_view, name='login'),

    path('logout/', logout_view, name='logout'),
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('id-cards/', id_card_generator_view, name='id_card_generator'),
    path('id-cards/upload-photo/', upload_id_card_photo_view, name='upload_id_card_photo'),
    path('verify-id/<str:username>/', verify_id_card_view, name='verify_id_card'),

    path('portal/manage-news/', manage_news_view, name='manage_news'),
    path('portal/manage-gallery/', manage_gallery_view, name='manage_gallery'),
    path('portal/manage-messages/', manage_contact_messages_view, name='manage_contact_messages'),
    path('teacher/', teacher_portal, name='teacher_portal'),
    path('parent/', parent_dashboard_view, name='parent_portal'),
    path('student/', student_dashboard_view, name='student_portal'),
    path('settings/users/', user_management_view, name='user_management'),
    path('finance/pay/<uuid:invoice_id>/', initiate_chapa_payment_view, name='initiate_chapa_payment'),
    path('api/portal-selectors/', portal_selectors_api, name='portal_selectors_api'),
    path('api/centralized-search/', centralized_search_api, name='centralized_search_api'),
]




