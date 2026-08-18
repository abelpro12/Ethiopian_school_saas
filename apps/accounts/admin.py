from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'school', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'school', 'is_staff', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('School & Role Info', {'fields': ('school', 'role', 'phone', 'is_two_factor_enabled')}),
    )
