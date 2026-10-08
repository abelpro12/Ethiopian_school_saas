from django.urls import path
from . import views
from . import views_discounts
from . import views_slips

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('pay/<int:invoice_id>/', views.record_payment_view, name='record_payment'),
    path('parent-pay/<int:invoice_id>/', views.parent_pay_view, name='parent_pay'),
    path('auth/<int:auth_id>/approve/', views.approve_manual_payment, name='approve_manual_payment'),

    # Discounts & Scholarships Hub (Item 3)
    path('discounts/', views_discounts.discounts_dashboard, name='discounts_dashboard'),

    # Bank Deposit Slip Verification Hub (Item 4)
    path('slips/', views_slips.slip_verification_hub, name='slip_verification_hub'),
    path('slips/<int:auth_id>/verify/', views_slips.verify_deposit_slip, name='verify_deposit_slip'),
]
