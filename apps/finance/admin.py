from django.contrib import admin
from .models import FeeCategory, FeeStructure, StudentInvoice, InvoiceItem, Payment, Receipt

@admin.register(FeeCategory)
class FeeCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'school')

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('fee_category', 'grade', 'academic_year', 'amount', 'school')

@admin.register(StudentInvoice)
class StudentInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'student', 'total_amount', 'paid_amount', 'status', 'due_date', 'school')
    list_filter = ('status', 'school')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('tx_ref', 'invoice', 'amount_paid', 'payment_method', 'status', 'payment_date', 'school')

@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'payment', 'issued_at', 'school')
