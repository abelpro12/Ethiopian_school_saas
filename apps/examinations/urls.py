from django.urls import path
from . import views

app_name = 'examinations'

urlpatterns = [
    # Teacher & Admin Management
    path('', views.online_exam_list_view, name='list'),
    path('online/create/', views.online_exam_create_view, name='create'),
    path('online/<uuid:exam_id>/', views.online_exam_detail_view, name='detail'),
    path('online/<uuid:exam_id>/edit/', views.online_exam_edit_view, name='edit'),
    path('online/<uuid:exam_id>/delete/', views.online_exam_delete_view, name='delete'),
    path('online/<uuid:exam_id>/publish/', views.online_exam_toggle_publish_view, name='toggle_publish'),
    
    # Question Builder
    path('online/<uuid:exam_id>/questions/', views.online_exam_questions_builder_view, name='questions_builder'),
    path('online/<uuid:exam_id>/questions/<uuid:question_id>/delete/', views.online_exam_question_delete_view, name='question_delete'),
    path('online/<uuid:exam_id>/questions/bulk/', views.online_exam_bulk_questions_view, name='bulk_questions'),
    
    # Live Proctoring & Monitoring
    path('online/<uuid:exam_id>/monitor/', views.online_exam_monitor_view, name='monitor'),
    path('online/<uuid:exam_id>/monitor/action/', views.online_exam_monitor_action_view, name='monitor_action'),
    path('online/<uuid:exam_id>/monitor/api/', views.online_exam_live_status_api, name='live_status_api'),
    
    # Evaluation, Grading Studio & Analytics
    path('online/<uuid:exam_id>/grading/', views.online_exam_grading_list_view, name='grading_list'),
    path('online/<uuid:exam_id>/grade/<uuid:attempt_id>/', views.online_exam_submission_grade_view, name='grade_submission'),
    path('online/<uuid:exam_id>/sync-grades/', views.online_exam_sync_grades_view, name='sync_grades'),
    path('online/<uuid:exam_id>/analytics/', views.online_exam_analytics_view, name='analytics'),
    
    # Student Testing Portal & CBT Room
    path('student/', views.student_exam_list_view, name='student_list'),
    path('student/<uuid:exam_id>/instructions/', views.student_exam_instructions_view, name='student_instructions'),
    path('student/<uuid:exam_id>/room/', views.student_exam_room_view, name='student_room'),
    path('student/<uuid:exam_id>/submit/', views.student_submit_exam_view, name='student_submit'),
    path('student/attempt/<uuid:attempt_id>/result/', views.student_exam_result_view, name='student_result'),
    path('student/api/save-answer/', views.student_save_answer_api, name='save_answer_api'),
    path('student/api/log-event/', views.student_log_proctoring_event_api, name='log_proctoring_api'),
]
