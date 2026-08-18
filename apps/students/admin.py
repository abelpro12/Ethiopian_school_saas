from django.contrib import admin
from .models import StudentProfile

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'full_name', 'gender', 'school', 'status')
    list_filter = ('school', 'gender', 'status')
    search_fields = ('student_id', 'first_name', 'middle_name', 'last_name')
