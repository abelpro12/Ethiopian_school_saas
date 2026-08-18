from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'object_type', 'object_id', 'ip_address', 'timestamp', 'school')
    list_filter = ('action', 'school', 'timestamp')
    readonly_fields = ('school', 'user', 'action', 'object_type', 'object_id', 'before_value', 'after_value', 'ip_address', 'timestamp')
