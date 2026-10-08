import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.finance.models import (
    ManualPaymentAuthorization, ManualPaymentStatus, Payment,
    PaymentStatus, StudentInvoice, InvoiceStatus, FinancialTransaction,
    TransactionType, Receipt
)
from apps.reports.models import DocumentVerification


@login_required
def slip_verification_hub(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT, UserRole.PRINCIPAL]:
        messages.error(request, "Unauthorized access to Bank Deposit Slip Verification Hub.")
        return redirect('finance:dashboard')

    status_filter = request.GET.get('status', ManualPaymentStatus.PENDING)
    bank_filter = request.GET.get('bank', '')
    query = request.GET.get('q', '').strip()

    qs = ManualPaymentAuthorization.objects.filter(school=school).select_related(
        'payment__invoice__student', 'payment__invoice__academic_year',
        'submitted_by', 'authorized_by'
    )

    if status_filter and status_filter != 'ALL':
        qs = qs.filter(status=status_filter)

    if bank_filter:
        qs = qs.filter(bank_name__iexact=bank_filter)

    if query:
        qs = qs.filter(
            Q(bank_reference__icontains=query) |
            Q(payment__invoice__invoice_number__icontains=query) |
            Q(payment__invoice__student__first_name__icontains=query) |
            Q(payment__invoice__student__last_name__icontains=query) |
            Q(payment__invoice__student__student_id__icontains=query)
        )

    authorizations = qs.order_by('-created_at')

    # Aggregates
    base_all = ManualPaymentAuthorization.objects.filter(school=school)
    pending_count = base_all.filter(status=ManualPaymentStatus.PENDING).count()
    pending_amount = base_all.filter(status=ManualPaymentStatus.PENDING).aggregate(
        total=Sum('payment__amount_paid')
    )['total'] or Decimal('0.00')

    approved_count = base_all.filter(status=ManualPaymentStatus.APPROVED).count()
    approved_amount = base_all.filter(status=ManualPaymentStatus.APPROVED).aggregate(
        total=Sum('payment__amount_paid')
    )['total'] or Decimal('0.00')

    rejected_count = base_all.filter(status=ManualPaymentStatus.REJECTED).count()

    banks = base_all.values_list('bank_name', flat=True).distinct()

    return render(request, 'finance/slip_verification_hub.html', {
        'authorizations': authorizations,
        'status_filter': status_filter,
        'bank_filter': bank_filter,
        'query': query,
        'banks': banks,
        'pending_count': pending_count,
        'pending_amount': pending_amount,
        'approved_count': approved_count,
        'approved_amount': approved_amount,
        'rejected_count': rejected_count,
        'statuses': ManualPaymentStatus.choices,
    })


@login_required
@transaction.atomic
def verify_deposit_slip(request, auth_id):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT]:
        messages.error(request, "Unauthorized access.")
        return redirect('finance:slip_verification_hub')

    auth_record = get_object_or_404(
        ManualPaymentAuthorization.objects.select_for_update(),
        id=auth_id,
        school=school
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            if auth_record.status == ManualPaymentStatus.APPROVED:
                messages.warning(request, "This deposit slip is already approved.")
                return redirect('finance:slip_verification_hub')

            # Optional adjusted verified amount
            verified_amount_str = request.POST.get('verified_amount')
            payment = auth_record.payment
            
            if verified_amount_str:
                try:
                    verified_amount = Decimal(verified_amount_str)
                    if verified_amount > 0:
                        payment.amount_paid = verified_amount
                        auth_record.verified_amount = verified_amount
                except Exception:
                    pass

            notes = request.POST.get('notes', '').strip()
            if notes:
                auth_record.notes = notes

            auth_record.status = ManualPaymentStatus.APPROVED
            auth_record.authorized_by = request.user
            auth_record.authorized_at = timezone.now()
            auth_record.save()

            # Mark Payment Successful & generate receipt number
            receipt_no = f"REC-MAN-{uuid.uuid4().hex[:8].upper()}"
            payment.status = PaymentStatus.SUCCESS
            payment.receipt_no = receipt_no
            payment.save()

            # Credit Invoice
            invoice = payment.invoice
            invoice.paid_amount += payment.amount_paid
            if invoice.remaining_balance <= Decimal('0.00'):
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID
            invoice.save()

            # Ledger Credit Transaction
            FinancialTransaction.objects.create(
                school=school,
                invoice=invoice,
                transaction_type=TransactionType.CREDIT,
                amount=payment.amount_paid,
                reference=f"VERIF-{auth_record.bank_reference}",
                created_by=request.user
            )

            # Digital Receipt
            Receipt.objects.get_or_create(
                school=school,
                payment=payment,
                defaults={'receipt_number': receipt_no}
            )

            # Document verification QR/Token
            DocumentVerification.objects.create(
                school=school,
                document_type='RECEIPT',
                verification_token=uuid.uuid4().hex,
                doc_number=receipt_no,
                metadata_json={
                    'invoice_number': invoice.invoice_number,
                    'student_id': invoice.student.student_id,
                    'amount_paid': str(payment.amount_paid),
                    'bank_reference': auth_record.bank_reference,
                    'bank_name': auth_record.bank_name,
                    'school_name': school.name,
                }
            )

            messages.success(
                request,
                f"Deposit slip {auth_record.bank_reference} APPROVED. "
                f"Credited ETB {payment.amount_paid:,.2f} to Invoice {invoice.invoice_number}. Receipt: {receipt_no}."
            )

        elif action == 'reject':
            reason = request.POST.get('rejection_reason', 'Deposit slip verification failed').strip()
            auth_record.status = ManualPaymentStatus.REJECTED
            auth_record.rejection_reason = reason
            auth_record.authorized_by = request.user
            auth_record.authorized_at = timezone.now()
            auth_record.save()

            payment = auth_record.payment
            payment.status = PaymentStatus.FAILED
            payment.notes = f"Rejected: {reason}"
            payment.save()

            messages.warning(
                request,
                f"Deposit slip {auth_record.bank_reference} was REJECTED. Reason: {reason}."
            )

    return redirect('finance:slip_verification_hub')
