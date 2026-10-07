from django.contrib import admin
from .models import AssessmentComponent, StudentMark, MarkChangeAudit, MarkEntryLock

@admin.register(AssessmentComponent)
class AssessmentComponentAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'weight', 'max_marks', 'period', 'school')

@admin.register(StudentMark)
class StudentMarkAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'assessment_component', 'mark_value', 'status', 'school')
    list_filter = ('status', 'school')

@admin.register(MarkChangeAudit)
class MarkChangeAuditAdmin(admin.ModelAdmin):
    list_display = ('mark', 'old_value', 'new_value', 'changed_by', 'timestamp', 'school')

@admin.register(MarkEntryLock)
class MarkEntryLockAdmin(admin.ModelAdmin):
    list_display = ('lock_type', 'grade', 'subject', 'teacher', 'section', 'is_active', 'reason', 'school', 'created_at')
    list_filter = ('is_active', 'lock_type', 'school', 'grade')
    search_fields = ('reason', 'grade__name', 'subject__name', 'teacher__username')
