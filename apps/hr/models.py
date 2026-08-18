import uuid
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.academics.models import AcademicYear


class ContractType(models.TextChoices):
    PERMANENT = 'PERMANENT', 'Permanent / Full-Time'
    CONTRACT = 'CONTRACT', 'Fixed-Term Contract'
    PROBATION = 'PROBATION', 'Probationary Period'
    PART_TIME = 'PART_TIME', 'Part-Time'


class ContractStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    EXPIRED = 'EXPIRED', 'Expired'
    TERMINATED = 'TERMINATED', 'Terminated'


class StaffContract(TenantAwareModel):
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hr_contracts')
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.PERMANENT)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=ContractStatus.choices, default=ContractStatus.ACTIVE)
    contract_document = models.FileField(upload_to='hr_contracts/', blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Contract: {self.staff_user.get_full_name()} ({self.get_contract_type_display()})"


class SalaryStructure(TenantAwareModel):
    staff_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='salary_structure')
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    tin_number = models.CharField(max_length=50, blank=True, null=True, help_text="Tax Identification Number")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Salary Config: {self.staff_user.username} - {self.basic_salary} ETB"


class ItemType(models.TextChoices):
    ALLOWANCE = 'ALLOWANCE', 'Allowance'
    DEDUCTION = 'DEDUCTION', 'Deduction'


class AllowanceDeduction(TenantAwareModel):
    salary_structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE, related_name='components')
    type = models.CharField(max_length=20, choices=ItemType.choices)
    title = models.CharField(max_length=100, help_text="e.g., Transport Allowance, Tax, Pension 7%")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_percentage = models.BooleanField(default=False, help_text="If checked, amount is treated as % of basic salary")

    def __str__(self):
        return f"{self.title} ({self.get_type_display()}) for {self.salary_structure.staff_user.username}"


class PayrollPeriod(TenantAwareModel):
    name = models.CharField(max_length=100, help_text="e.g., Meskerem 2017 / Sept 2024")
    start_date = models.DateField()
    end_date = models.DateField()
    is_processed = models.BooleanField(default=False)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"Payroll: {self.name} [{self.school.code}]"


class PayslipStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    GENERATED = 'GENERATED', 'Generated'
    PAID = 'PAID', 'Paid'


class Payslip(TenantAwareModel):
    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='payslips')
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payslips')
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    total_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=PayslipStatus.choices, default=PayslipStatus.DRAFT)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'payroll_period', 'staff_user')

    def __str__(self):
        return f"Payslip: {self.staff_user.get_full_name()} - {self.payroll_period.name} ({self.net_salary} ETB)"


class PayslipItem(models.Model):
    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=100)
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.title}: {self.amount} ETB"


class StaffPerformanceReview(TenantAwareModel):
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='performance_reviews')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='conducted_reviews')
    review_date = models.DateField()
    rating = models.IntegerField(choices=[(i, f"{i} Stars") for i in range(1, 6)], default=5)
    strengths = models.TextField(blank=True, null=True)
    areas_for_improvement = models.TextField(blank=True, null=True)
    goals = models.TextField(blank=True, null=True)
    comments = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Performance Review: {self.staff_user.get_full_name()} ({self.rating}/5)"


class StaffLeaveBalance(TenantAwareModel):
    staff_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leave_balances')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='leave_balances')
    annual_leave_allocated = models.IntegerField(default=16)
    annual_leave_used = models.IntegerField(default=0)
    sick_leave_allocated = models.IntegerField(default=12)
    sick_leave_used = models.IntegerField(default=0)

    class Meta:
        unique_together = ('school', 'staff_user', 'academic_year')

    def __str__(self):
        return f"Leave Balance ({self.academic_year.name}): {self.staff_user.username}"
