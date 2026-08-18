from django.contrib import admin
from .models import School

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'subdomain', 'calendar_preference', 'is_active', 'created_at')
    search_fields = ('name', 'code', 'subdomain')
    list_filter = ('calendar_preference', 'is_active')
