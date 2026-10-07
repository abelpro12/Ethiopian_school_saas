from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    path('inbox/', views.inbox_view, name='inbox'),
    path('compose/', views.compose_view, name='compose'),
    path('thread/<int:conv_id>/', views.thread_view, name='thread'),
    path('archive/<int:conv_id>/', views.archive_conversation_view, name='archive'),
    path('api/unread-count/', views.unread_count_api, name='unread_count_api'),
]
