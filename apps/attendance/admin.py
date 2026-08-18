from django.contrib import admin
from .models import AttendanceRecord, AttendanceCorrection

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'section', 'date', 'status', 'school')
    list_filter = ('status', 'date', 'school')

@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    list_display = ('attendance_record', 'old_status', 'new_status', 'corrected_by', 'timestamp', 'school')
