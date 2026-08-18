from django.contrib import admin
from .models import DocumentVerification

@admin.register(DocumentVerification)
class DocumentVerificationAdmin(admin.ModelAdmin):
    list_display = ('doc_number', 'document_type', 'verification_token', 'is_valid', 'created_at', 'school')
    list_filter = ('document_type', 'is_valid', 'school')
