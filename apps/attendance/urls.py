from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('section/<int:section_id>/', views.SectionAttendanceView.as_view(), name='section_attendance'),
    path('tutorial/', views.TutorialAttendanceView.as_view(), name='tutorial_attendance'),
    path('staff/', views.StaffAttendanceView.as_view(), name='staff_attendance'),
    path('staff/export/', views.StaffAttendanceExportView.as_view(), name='staff_attendance_export'),
    path('reports/', views.AttendanceReportSummaryView.as_view(), name='reports'),
]
