from django.contrib import admin
from .models import AuditLog, LoginAuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'object_type', 'object_id', 'ip_address', 'timestamp', 'school')
    list_filter = ('action', 'school', 'timestamp')
    search_fields = ('action', 'object_type', 'object_id', 'user__username', 'ip_address')
    readonly_fields = ('school', 'user', 'action', 'object_type', 'object_id', 'before_value', 'after_value', 'ip_address', 'timestamp')


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ('username_attempted', 'user', 'status', 'ip_address', 'timestamp', 'school')
    list_filter = ('status', 'school', 'timestamp')
    search_fields = ('username_attempted', 'user__username', 'ip_address', 'failure_reason')
    readonly_fields = ('school', 'username_attempted', 'user', 'status', 'ip_address', 'user_agent', 'timestamp', 'failure_reason')
