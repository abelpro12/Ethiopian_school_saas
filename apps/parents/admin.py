from django.contrib import admin
from .models import ParentProfile, GuardianRelationship

@admin.register(ParentProfile)
class ParentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'relationship', 'phone', 'preferred_language', 'school')

@admin.register(GuardianRelationship)
class GuardianRelationshipAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student', 'is_primary', 'school')
