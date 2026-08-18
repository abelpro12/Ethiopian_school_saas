from django import forms
from .models import StaffContract, SalaryStructure, AllowanceDeduction, PayrollPeriod, StaffPerformanceReview, StaffLeaveBalance

class StaffContractForm(forms.ModelForm):
    class Meta:
        model = StaffContract
        fields = ['staff_user', 'contract_type', 'start_date', 'end_date', 'basic_salary', 'status', 'notes', 'contract_document']
        widgets = {
            'staff_user': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'contract_type': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'status': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
        }

class SalaryStructureForm(forms.ModelForm):
    class Meta:
        model = SalaryStructure
        fields = ['staff_user', 'basic_salary', 'bank_name', 'account_number', 'tin_number']
        widgets = {
            'staff_user': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'bank_name': forms.TextInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'account_number': forms.TextInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'tin_number': forms.TextInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
        }

class AllowanceDeductionForm(forms.ModelForm):
    class Meta:
        model = AllowanceDeduction
        fields = ['type', 'title', 'amount', 'is_percentage']
        widgets = {
            'type': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'title': forms.TextInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'amount': forms.NumberInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'is_percentage': forms.CheckboxInput(attrs={'class': 'rounded border-slate-300 text-brand-600 focus:ring-brand-500'}),
        }

class PayrollPeriodForm(forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm', 'placeholder': 'e.g. Meskerem 2017'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
        }

class StaffPerformanceReviewForm(forms.ModelForm):
    class Meta:
        model = StaffPerformanceReview
        fields = ['staff_user', 'review_date', 'rating', 'strengths', 'areas_for_improvement', 'goals', 'comments']
        widgets = {
            'staff_user': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'review_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'rating': forms.Select(attrs={'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'strengths': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'areas_for_improvement': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'goals': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
            'comments': forms.Textarea(attrs={'rows': 2, 'class': 'w-full border border-slate-300 rounded-xl px-3 py-2 text-sm'}),
        }
