from django.contrib import admin
from .models import TeacherProfile, TeacherAssignment

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'user', 'specialization', 'phone', 'school')

@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'subject', 'section', 'academic_year', 'school')
