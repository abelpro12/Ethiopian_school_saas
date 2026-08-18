import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View, TemplateView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.teachers.models import StaffProfile, TeacherProfile, StaffLeaveRequest
from .models import (
    StaffContract, SalaryStructure, AllowanceDeduction, ItemType,
    PayrollPeriod, Payslip, PayslipItem, PayslipStatus,
    StaffPerformanceReview, StaffLeaveBalance
)
from .forms import (
    StaffContractForm, SalaryStructureForm, AllowanceDeductionForm,
    PayrollPeriodForm, StaffPerformanceReviewForm
)
from apps.platform_management.decorators import school_context_required
from django.utils.decorators import method_decorator


def get_school(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)


@method_decorator(school_context_required, name='dispatch')
class HRDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'hr/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school = get_school(self.request)
        
        # Staff Counts
        teachers_count = TeacherProfile.objects.filter(school=school).count() if school else 0
        other_staff_count = StaffProfile.objects.filter(school=school).count() if school else 0
        active_contracts = StaffContract.objects.filter(school=school, status='ACTIVE').count() if school else 0
        
        # Payroll metrics
        latest_payroll = PayrollPeriod.objects.filter(school=school).first() if school else None
        total_payroll_cost = Payslip.objects.filter(school=school, payroll_period=latest_payroll).aggregate(total=Sum('net_salary'))['total'] or 0 if (school and latest_payroll) else 0
        
        # Pending leave requests
        pending_leaves = StaffLeaveRequest.objects.filter(school=school, status='PENDING').count() if school else 0
        
        # Recent Performance Reviews
        recent_reviews = StaffPerformanceReview.objects.filter(school=school).order_by('-review_date')[:5] if school else []

        context.update({
            'teachers_count': teachers_count,
            'other_staff_count': other_staff_count,
            'total_staff': teachers_count + other_staff_count,
            'active_contracts': active_contracts,
            'latest_payroll': latest_payroll,
            'total_payroll_cost': total_payroll_cost,
            'pending_leaves': pending_leaves,
            'recent_reviews': recent_reviews,
            'title': 'HR & Payroll Dashboard'
        })
        return context


class ContractListView(LoginRequiredMixin, View):
    template_name = 'hr/contracts.html'

    def get(self, request):
        school = get_school(request)
        contracts = StaffContract.objects.filter(school=school).select_related('staff_user').order_by('-start_date') if school else []
        form = StaffContractForm()
        if school:
            form.fields['staff_user'].queryset = User.objects.filter(school=school, role__in=[UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.HR_MANAGER])

        context = {
            'contracts': contracts,
            'form': form,
            'title': 'Staff Contracts & Terms'
        }
        return render(request, self.template_name, context)

    def post(self, request):
        school = get_school(request)
        form = StaffContractForm(request.POST, request.FILES)
        if form.is_valid():
            contract = form.save(commit=False)
            contract.school = school
            contract.save()
            messages.success(request, f'Contract created for {contract.staff_user.get_full_name()}.')
            return redirect('hr:contracts')

        contracts = StaffContract.objects.filter(school=school).select_related('staff_user') if school else []
        return render(request, self.template_name, {'contracts': contracts, 'form': form, 'title': 'Staff Contracts & Terms'})


class PayrollListView(LoginRequiredMixin, View):
    template_name = 'hr/payroll_list.html'

    def get(self, request):
        school = get_school(request)
        periods = PayrollPeriod.objects.filter(school=school) if school else []
        form = PayrollPeriodForm()
        context = {
            'periods': periods,
            'form': form,
            'title': 'Payroll Periods'
        }
        return render(request, self.template_name, context)

    def post(self, request):
        school = get_school(request)
        form = PayrollPeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.school = school
            period.save()
            messages.success(request, f'Payroll period "{period.name}" created.')
            return redirect('hr:payroll_list')
        
        periods = PayrollPeriod.objects.filter(school=school) if school else []
        return render(request, self.template_name, {'periods': periods, 'form': form, 'title': 'Payroll Periods'})


class ProcessPayrollView(LoginRequiredMixin, View):
    def post(self, request, period_id):
        school = get_school(request)
        period = get_object_or_404(PayrollPeriod, id=period_id, school=school)
        
        staff_users = User.objects.filter(
            school=school,
            role__in=[UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.HR_MANAGER]
        )

        for staff in staff_users:
            salary_struct, _ = SalaryStructure.objects.get_or_create(
                school=school,
                staff_user=staff,
                defaults={'basic_salary': 10000.00}
            )
            
            basic = salary_struct.basic_salary
            allowances_sum = 0
            deductions_sum = 0

            payslip, _ = Payslip.objects.get_or_create(
                school=school,
                payroll_period=period,
                staff_user=staff,
                defaults={
                    'basic_salary': basic,
                    'total_allowances': 0,
                    'total_deductions': 0,
                    'net_salary': basic,
                    'status': PayslipStatus.GENERATED
                }
            )

            payslip.items.all().delete()

            for component in salary_struct.components.all():
                amt = (basic * (component.amount / 100)) if component.is_percentage else component.amount
                PayslipItem.objects.create(
                    payslip=payslip,
                    title=component.title,
                    item_type=component.type,
                    amount=amt
                )
                if component.type == ItemType.ALLOWANCE:
                    allowances_sum += amt
                else:
                    deductions_sum += amt

            payslip.basic_salary = basic
            payslip.total_allowances = allowances_sum
            payslip.total_deductions = deductions_sum
            payslip.net_salary = (basic + allowances_sum) - deductions_sum
            payslip.status = PayslipStatus.GENERATED
            payslip.save()

        period.is_processed = True
        period.processed_by = request.user
        period.processed_at = timezone.now()
        period.save()

        messages.success(request, f'Payroll period "{period.name}" successfully processed for {staff_users.count()} staff members.')
        return redirect('hr:payroll_list')


class PayslipDetailView(LoginRequiredMixin, DetailView):
    model = Payslip
    template_name = 'hr/payslip.html'
    context_object_name = 'payslip'

    def get_queryset(self):
        school = get_school(self.request)
        return Payslip.objects.filter(school=school) if school else Payslip.objects.none()


class PerformanceReviewView(LoginRequiredMixin, View):
    template_name = 'hr/performance.html'

    def get(self, request):
        school = get_school(request)
        reviews = StaffPerformanceReview.objects.filter(school=school).select_related('staff_user', 'reviewer').order_by('-review_date') if school else []
        form = StaffPerformanceReviewForm()
        if school:
            form.fields['staff_user'].queryset = User.objects.filter(school=school, role__in=[UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.HR_MANAGER])

        context = {
            'reviews': reviews,
            'form': form,
            'title': 'Staff Performance Reviews'
        }
        return render(request, self.template_name, context)

    def post(self, request):
        school = get_school(request)
        form = StaffPerformanceReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.school = school
            review.reviewer = request.user
            review.save()
            messages.success(request, f'Performance review logged for {review.staff_user.get_full_name()}.')
            return redirect('hr:performance')

        reviews = StaffPerformanceReview.objects.filter(school=school).select_related('staff_user', 'reviewer') if school else []
        return render(request, self.template_name, {'reviews': reviews, 'form': form, 'title': 'Staff Performance Reviews'})
