import uuid
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from apps.tenants.models import TenantAwareModel
from apps.academics.models import AcademicYear, AcademicPeriod, Grade
from apps.students.models import StudentProfile
from apps.accounts.models import User


class FeeCategory(TenantAwareModel):
    name = models.CharField(max_length=100)  # Registration, Tuition, Lab, Materials, Transport, Other

    class Meta:
        unique_together = ('school', 'name')

    def __str__(self):
        return self.name


class FeeStructure(TenantAwareModel):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='fee_structures')
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='fee_structures')
    fee_category = models.ForeignKey(FeeCategory, on_delete=models.CASCADE, related_name='fee_structures')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    due_date = models.DateField()

    class Meta:
        unique_together = ('school', 'academic_year', 'grade', 'fee_category')

    def __str__(self):
        return f"{self.grade.name} - {self.fee_category.name}: {self.amount} ETB"


class DiscountType(models.TextChoices):
    PERCENTAGE = 'PERCENTAGE', 'Percentage (%)'
    FIXED_AMOUNT = 'FIXED_AMOUNT', 'Fixed Amount (ETB)'


class DiscountCategory(models.TextChoices):
    SIBLING = 'SIBLING', 'Sibling / Multi-Child Discount'
    STAFF_CHILD = 'STAFF_CHILD', 'Staff Child Waiver'
    MERIT_SCHOLARSHIP = 'MERIT_SCHOLARSHIP', 'Merit Academic Scholarship'
    NEED_BASED = 'NEED_BASED', 'Need-Based Financial Aid'
    EARLY_BIRD = 'EARLY_BIRD', 'Early Bird Discount'
    CUSTOM = 'CUSTOM', 'Custom Rule / Waiver'


class DiscountPolicy(TenantAwareModel):
    name = models.CharField(max_length=150)
    discount_category = models.CharField(max_length=30, choices=DiscountCategory.choices, default=DiscountCategory.SIBLING)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.PERCENTAGE)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    sibling_order = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Sibling rank to trigger discount (e.g. 2 for 2nd child, 3 for 3rd and subsequent children)"
    )
    fee_category = models.ForeignKey(
        FeeCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='discount_policies',
        help_text="Optional fee category constraint (e.g., Tuition only). Blank applies to total invoice."
    )
    is_active = models.BooleanField(default=True)
    auto_apply = models.BooleanField(default=True, help_text="Automatically evaluate and apply during invoice generation")
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['discount_category', 'sibling_order', 'name']

    def __str__(self):
        val_str = f"{self.value}%" if self.discount_type == DiscountType.PERCENTAGE else f"{self.value} ETB"
        return f"{self.name} ({val_str})"


class StudentDiscount(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='assigned_discounts')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='student_discounts')
    discount_policy = models.ForeignKey(DiscountPolicy, on_delete=models.CASCADE, related_name='student_assignments')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_discounts')
    approved_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ('school', 'student', 'academic_year', 'discount_policy')
        ordering = ['-approved_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.discount_policy.name}"


class InvoiceStatus(models.TextChoices):
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
    PAID = 'PAID', 'Paid'
    OVERDUE = 'OVERDUE', 'Overdue'
    CANCELLED = 'CANCELLED', 'Cancelled'
    REFUNDED = 'REFUNDED', 'Refunded'


class StudentInvoice(TenantAwareModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='invoices')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='invoices')
    period = models.ForeignKey(AcademicPeriod, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    invoice_number = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_policy = models.ForeignKey(DiscountPolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name='applied_invoices')
    discount_reason = models.CharField(max_length=255, blank=True, default='')
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.UNPAID)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'invoice_number')

    @property
    def remaining_balance(self):
        net_total = max(Decimal('0.00'), self.total_amount - self.discount_amount)
        return max(Decimal('0.00'), net_total - self.paid_amount)

    @property
    def net_amount(self):
        return max(Decimal('0.00'), self.total_amount - self.discount_amount)

    @property
    def is_overdue(self):
        from datetime import date
        return self.remaining_balance > 0 and self.due_date < date.today()

    def __str__(self):
        return f"Invoice {self.invoice_number} ({self.student.full_name}): {self.remaining_balance} ETB left"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(StudentInvoice, on_delete=models.CASCADE, related_name='items')
    fee_category = models.ForeignKey(FeeCategory, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.fee_category.name}: {self.amount} ETB"


class PaymentMethod(models.TextChoices):
    CHAPA = 'CHAPA', 'Chapa Digital Payment'
    TELEBIRR = 'TELEBIRR', 'Telebirr SuperApp / USSD'
    CBE_BIRR = 'CBE_BIRR', 'CBE Birr'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer (CBE / Awash / Dashen)'
    CASH = 'CASH', 'Cash'
    MANUAL = 'MANUAL', 'Manual Receipt Adjustment'


class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Approval / Processing'
    SUCCESS = 'SUCCESS', 'Successful'
    FAILED = 'FAILED', 'Failed'
    REVERSED = 'REVERSED', 'Reversed / Refunded'


class Payment(TenantAwareModel):
    invoice = models.ForeignKey(StudentInvoice, on_delete=models.CASCADE, related_name='payments')
    tx_ref = models.CharField(max_length=100, unique=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices, default=PaymentMethod.CHAPA)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    receipt_no = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.tx_ref} ({self.amount_paid} ETB) - {self.status}"


class TransactionType(models.TextChoices):
    DEBIT = 'DEBIT', 'Debit (Invoice Creation)'
    CREDIT = 'CREDIT', 'Credit (Payment Received)'
    DISCOUNT = 'DISCOUNT', 'Discount Adjustment'
    WAIVER = 'WAIVER', 'Fee Waiver'
    REFUND = 'REFUND', 'Refund Issued'
    REVERSAL = 'REVERSAL', 'Payment Reversal'


class FinancialTransaction(TenantAwareModel):
    invoice = models.ForeignKey(StudentInvoice, on_delete=models.CASCADE, related_name='ledger_transactions')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ledger {self.reference}: {self.transaction_type} {self.amount} ETB"


class ManualPaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Admin Verification'
    APPROVED = 'APPROVED', 'Approved & Credited'
    REJECTED = 'REJECTED', 'Rejected'


class ManualPaymentAuthorization(TenantAwareModel):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='manual_auth')
    bank_reference = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100, default='CBE')
    deposit_slip_image = models.FileField(upload_to='deposit_slips/', blank=True, null=True)
    deposit_date = models.DateField(null=True, blank=True)
    verified_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=ManualPaymentStatus.choices, default=ManualPaymentStatus.PENDING)
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='submitted_manual_payments')
    authorized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='authorized_manual_payments')
    authorized_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"Manual Auth {self.bank_reference} ({self.status})"


class ReconciliationStatus(models.TextChoices):
    RECONCILED = 'RECONCILED', 'Reconciled'
    DISCREPANCY = 'DISCREPANCY', 'Discrepancy Found'
    UNDER_INVESTIGATION = 'UNDER_INVESTIGATION', 'Under Investigation'


class PaymentReconciliation(TenantAwareModel):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='reconciliation')
    provider_tx_id = models.CharField(max_length=100)
    provider_amount = models.DecimalField(max_digits=10, decimal_places=2)
    internal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=30, choices=ReconciliationStatus.choices, default=ReconciliationStatus.RECONCILED)
    checked_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Reconciliation {self.payment.tx_ref} - {self.status}"


class AdjustmentType(models.TextChoices):
    REFUND = 'REFUND', 'Full / Partial Refund'
    REVERSAL = 'REVERSAL', 'Payment Reversal'
    CANCELLED = 'CANCELLED', 'Transaction Cancelled'
    DUPLICATE = 'DUPLICATE', 'Duplicate Payment Refund'
    MANUAL_ADJUSTMENT = 'MANUAL_ADJUSTMENT', 'Manual Adjustment'


class PaymentRefund(TenantAwareModel):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    adjustment_type = models.CharField(max_length=30, choices=AdjustmentType.choices, default=AdjustmentType.REFUND)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.TextField()
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.adjustment_type} of {self.amount} ETB for {self.payment.tx_ref}"


class Receipt(TenantAwareModel):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='receipt')
    receipt_number = models.CharField(max_length=100, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    pdf_file = models.FileField(upload_to='receipt_pdfs/', blank=True, null=True)

    def __str__(self):
        return f"Receipt {self.receipt_number}"
