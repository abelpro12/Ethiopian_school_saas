from django.urls import path
from . import views

app_name = 'hr'

urlpatterns = [
    path('dashboard/', views.HRDashboardView.as_view(), name='dashboard'),
    path('contracts/', views.ContractListView.as_view(), name='contracts'),
    path('payroll/', views.PayrollListView.as_view(), name='payroll_list'),
    path('payroll/process/<int:period_id>/', views.ProcessPayrollView.as_view(), name='process_payroll'),
    path('payslip/<int:pk>/', views.PayslipDetailView.as_view(), name='payslip_detail'),
    path('performance/', views.PerformanceReviewView.as_view(), name='performance'),
]
