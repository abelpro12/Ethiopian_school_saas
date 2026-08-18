from django.contrib import admin
from .models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'ethiopian_year', 'gregorian_start_date', 'gregorian_end_date', 'is_active')
    list_filter = ('school', 'is_active')

@admin.register(AcademicPeriod)
class AcademicPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'school', 'period_type', 'start_date', 'end_date', 'is_current')
    list_filter = ('school', 'is_current')

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'school')
    list_filter = ('school', 'level')

@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'school')

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade', 'stream', 'school', 'capacity', 'shift')
    list_filter = ('school', 'grade', 'shift')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'amharic_name', 'grade', 'stream', 'school')
    list_filter = ('school', 'grade', 'stream')
