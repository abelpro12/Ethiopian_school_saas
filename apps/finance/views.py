import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q

from apps.accounts.models import UserRole
from apps.finance.models import (
    FeeCategory, FeeStructure, StudentInvoice, InvoiceItem, 
    Payment, PaymentMethod, PaymentStatus, ManualPaymentAuthorization,
    ManualPaymentStatus, FinancialTransaction, TransactionType, InvoiceStatus
)
from apps.academics.models import AcademicYear, Grade, AcademicPeriod
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus


@login_required
def finance_dashboard(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Unauthorized access to Financial Management.")
        return redirect('index')

    current_ay = getattr(request, 'academic_year', None)
    
    invoices = StudentInvoice.objects.filter(school=school)
    if current_ay:
        invoices = invoices.filter(academic_year=current_ay)
        
    total_invoiced = invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_paid = invoices.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
    outstanding_balance = max(Decimal('0.00'), total_invoiced - total_paid)

    fee_categories = FeeCategory.objects.filter(school=school)
    fee_structures = FeeStructure.objects.filter(school=school).select_related('academic_year', 'grade', 'fee_category')
    if current_ay:
        fee_structures = fee_structures.filter(academic_year=current_ay)
    grades = Grade.objects.filter(school=school)
    academic_years = AcademicYear.objects.filter(school=school)

    # Handle Forms
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_category':
            name = request.POST.get('name')
            if name:
                FeeCategory.objects.get_or_create(school=school, name=name)
                messages.success(request, f"Fee category '{name}' created.")
            return redirect('finance:dashboard')

        elif action == 'add_structure':
            ay_id = request.POST.get('academic_year_id')
            grade_id = request.POST.get('grade_id')
            cat_id = request.POST.get('category_id')
            amount = request.POST.get('amount')
            due_date = request.POST.get('due_date')

            try:
                ay = AcademicYear.objects.get(id=ay_id, school=school)
                gr = Grade.objects.get(id=grade_id, school=school)
                cat = FeeCategory.objects.get(id=cat_id, school=school)
                FeeStructure.objects.update_or_create(
                    school=school, academic_year=ay, grade=gr, fee_category=cat,
                    defaults={'amount': Decimal(amount), 'due_date': due_date}
                )
                messages.success(request, f"Fee structure for {gr.name} - {cat.name} saved.")
            except Exception as e:
                messages.error(request, f"Error creating fee structure: {str(e)}")
            return redirect('finance:dashboard')

        elif action == 'generate_invoices':
            ay_id = request.POST.get('academic_year_id')
            grade_id = request.POST.get('grade_id')
            
            try:
                ay = AcademicYear.objects.get(id=ay_id, school=school)
                structures = FeeStructure.objects.filter(school=school, academic_year=ay)
                if grade_id:
                    structures = structures.filter(grade_id=grade_id)

                enrollments = StudentEnrollment.objects.filter(school=school, academic_year=ay, status=EnrollmentStatus.ACTIVE)
                if grade_id:
                    enrollments = enrollments.filter(grade_id=grade_id)

                generated_count = 0
                for enr in enrollments:
                    grade_structs = structures.filter(grade=enr.grade)
                    if not grade_structs.exists():
                        continue
                    
                    total = sum(s.amount for s in grade_structs)
                    earliest_due = min(s.due_date for s in grade_structs)
                    inv_no = f"INV-{ay.ethiopian_year}-{enr.student.student_id}"

                    invoice, created = StudentInvoice.objects.get_or_create(
                        school=school,
                        student=enr.student,
                        academic_year=ay,
                        invoice_number=inv_no,
                        defaults={
                            'total_amount': total,
                            'due_date': earliest_due,
                            'status': InvoiceStatus.UNPAID
                        }
                    )
                    if created:
                        for s in grade_structs:
                            InvoiceItem.objects.create(invoice=invoice, fee_category=s.fee_category, amount=s.amount)
                        FinancialTransaction.objects.create(
                            school=school, invoice=invoice, transaction_type=TransactionType.DEBIT,
                            amount=total, reference=f"DEBIT-{inv_no}", created_by=request.user
                        )
                        from apps.finance.discount_service import DiscountService
                        DiscountService.apply_discount_to_invoice(invoice, user=request.user)
                        generated_count += 1

                messages.success(request, f"Successfully generated {generated_count} student invoice(s).")
            except Exception as e:
                messages.error(request, f"Error generating invoices: {str(e)}")
            return redirect('finance:dashboard')

    recent_invoices = invoices.select_related('student', 'academic_year').order_by('-created_at')[:20]
    pending_manual_auths = ManualPaymentAuthorization.objects.filter(school=school, status=ManualPaymentStatus.PENDING).select_related('payment__invoice__student', 'submitted_by')

    return render(request, 'finance/dashboard.html', {
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'outstanding_balance': outstanding_balance,
        'fee_categories': fee_categories,
        'fee_structures': fee_structures,
        'grades': grades,
        'academic_years': academic_years,
        'recent_invoices': recent_invoices,
        'pending_manual_auths': pending_manual_auths,
    })


@login_required
def record_payment_view(request, invoice_id):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT]:
        messages.error(request, "Unauthorized access.")
        return redirect('finance:dashboard')

    invoice = get_object_or_404(StudentInvoice, id=invoice_id, school=school)

    if request.method == 'POST':
        amount = request.POST.get('amount')
        method = request.POST.get('method', PaymentMethod.CASH)
        notes = request.POST.get('notes', '')

        try:
            amount_dec = Decimal(amount)
            if amount_dec <= 0:
                messages.error(request, "Payment amount must be greater than zero.")
                return redirect('finance:record_payment', invoice_id=invoice.id)

            tx_ref = f"PAY-{uuid.uuid4().hex[:8].upper()}"
            receipt_no = f"REC-{uuid.uuid4().hex[:6].upper()}"

            payment = Payment.objects.create(
                school=school,
                invoice=invoice,
                tx_ref=tx_ref,
                amount_paid=amount_dec,
                payment_method=method,
                status=PaymentStatus.SUCCESS,
                receipt_no=receipt_no,
                notes=notes
            )

            # Update Invoice
            invoice.paid_amount += amount_dec
            if invoice.remaining_balance == 0:
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID
            invoice.save()

            # Record Ledger
            FinancialTransaction.objects.create(
                school=school,
                invoice=invoice,
                transaction_type=TransactionType.CREDIT,
                amount=amount_dec,
                reference=tx_ref,
                created_by=request.user
            )

            messages.success(request, f"Recorded payment of ETB {amount_dec} for Invoice {invoice.invoice_number}. Receipt #{receipt_no}.")
            return redirect('finance:dashboard')

        except Exception as e:
            messages.error(request, f"Error processing payment: {str(e)}")

    return render(request, 'finance/record_payment.html', {
        'invoice': invoice,
        'payment_methods': PaymentMethod.choices,
    })


@login_required
def approve_manual_payment(request, auth_id):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT]:
        messages.error(request, "Unauthorized access.")
        return redirect('finance:dashboard')

    manual_auth = get_object_or_404(ManualPaymentAuthorization, id=auth_id, school=school)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            manual_auth.status = ManualPaymentStatus.APPROVED
            manual_auth.authorized_by = request.user
            manual_auth.save()

            payment = manual_auth.payment
            payment.status = PaymentStatus.SUCCESS
            payment.save()

            invoice = payment.invoice
            invoice.paid_amount += payment.amount_paid
            if invoice.remaining_balance == 0:
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID
            invoice.save()

            FinancialTransaction.objects.create(
                school=school,
                invoice=invoice,
                transaction_type=TransactionType.CREDIT,
                amount=payment.amount_paid,
                reference=payment.tx_ref,
                created_by=request.user
            )
            messages.success(request, f"Approved payment {payment.tx_ref} of ETB {payment.amount_paid}.")

        elif action == 'reject':
            reason = request.POST.get('reason', 'Verification failed')
            manual_auth.status = ManualPaymentStatus.REJECTED
            manual_auth.rejection_reason = reason
            manual_auth.authorized_by = request.user
            manual_auth.save()

            payment = manual_auth.payment
            payment.status = PaymentStatus.FAILED
            payment.save()
            messages.warning(request, f"Rejected payment {payment.tx_ref}.")

    return redirect('finance:dashboard')


@login_required
def parent_pay_view(request, invoice_id):
    from apps.payments.services import ChapaService

    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role != UserRole.PARENT:
        messages.error(request, "Only parents can use this payment gateway.")
        return redirect('index')

    invoice = get_object_or_404(StudentInvoice, id=invoice_id, school=school)

    # Check if parent is linked to this student
    try:
        from apps.parents.models import GuardianRelationship, ParentProfile
        parent_profile = ParentProfile.objects.get(user=request.user, school=school)
        GuardianRelationship.objects.get(parent=parent_profile, student=invoice.student)
    except (ParentProfile.DoesNotExist, GuardianRelationship.DoesNotExist):
        messages.error(request, "You are not authorized to pay this invoice.")
        return redirect('parent_portal')

    if invoice.remaining_balance <= Decimal('0.00'):
        messages.success(request, "This invoice is already paid in full.")
        return redirect('parent_portal')

    if request.method == 'POST':
        method = request.POST.get('payment_method', 'CHAPA')

        if method == 'CHAPA':
            try:
                callback_url = request.build_absolute_uri('/')
                res = ChapaService.initialize_payment(
                    school=school,
                    invoice=invoice,
                    amount=invoice.remaining_balance,
                    parent_email=request.user.email or "parent@school.com",
                    first_name=request.user.first_name or "Parent",
                    last_name=request.user.last_name or "User",
                    callback_url=callback_url
                )
                return redirect(res['checkout_url'])
            except Exception as e:
                messages.error(request, f"Error initializing Chapa payment: {str(e)}")
                return redirect('finance:parent_pay', invoice_id=invoice.id)

        elif method in ['TELEBIRR', 'CBE_BIRR']:
            # Digital mobile wallet checkout request
            phone = request.POST.get('payer_phone', request.user.parent_profile.phone or '')
            prefix = "TEL" if method == 'TELEBIRR' else "CBEB"
            tx_ref = f"{prefix}-{uuid.uuid4().hex[:10].upper()}"

            amount_to_pay = invoice.remaining_balance
            payment = Payment.objects.create(
                school=school,
                invoice=invoice,
                tx_ref=tx_ref,
                amount_paid=amount_to_pay,
                payment_method=method,
                status=PaymentStatus.PENDING,
                notes=f"Mobile payment initiated via {method} for {phone}"
            )

            # Also create manual authorization record so cashiers can see pending mobile push
            ManualPaymentAuthorization.objects.create(
                school=school,
                payment=payment,
                bank_reference=tx_ref,
                bank_name=method,
                status=ManualPaymentStatus.PENDING,
                submitted_by=request.user,
                notes=f"Mobile money prompt sent to {phone}. Awaiting confirmation."
            )

            messages.success(
                request,
                f"{method} payment request initiated (Ref: {tx_ref})! "
                f"Please authorize the prompt on phone number {phone} or show this reference to the school cashier."
            )
            return redirect('parent_portal')

        elif method == 'BANK_TRANSFER':
            bank_name = request.POST.get('bank_name', 'CBE').strip()
            bank_reference = request.POST.get('bank_reference', '').strip()
            deposit_date = request.POST.get('deposit_date')
            amount_str = request.POST.get('amount_paid', str(invoice.remaining_balance))
            deposit_slip_image = request.FILES.get('deposit_slip_image')
            notes = request.POST.get('notes', '').strip()

            if not bank_reference:
                messages.error(request, "Please enter the bank deposit/transfer transaction reference.")
                return redirect('finance:parent_pay', invoice_id=invoice.id)

            try:
                amount_dec = Decimal(amount_str)
                if amount_dec <= Decimal('0.00'):
                    messages.error(request, "Amount deposited must be greater than zero.")
                    return redirect('finance:parent_pay', invoice_id=invoice.id)
            except Exception:
                messages.error(request, "Invalid amount entered.")
                return redirect('finance:parent_pay', invoice_id=invoice.id)

            tx_ref = f"SLIP-{uuid.uuid4().hex[:8].upper()}"
            payment = Payment.objects.create(
                school=school,
                invoice=invoice,
                tx_ref=tx_ref,
                amount_paid=amount_dec,
                payment_method=PaymentMethod.BANK_TRANSFER,
                status=PaymentStatus.PENDING,
                notes=notes
            )

            ManualPaymentAuthorization.objects.create(
                school=school,
                payment=payment,
                bank_reference=bank_reference,
                bank_name=bank_name,
                deposit_date=deposit_date if deposit_date else None,
                deposit_slip_image=deposit_slip_image,
                status=ManualPaymentStatus.PENDING,
                submitted_by=request.user,
                notes=notes
            )

            messages.success(
                request,
                f"Bank deposit slip with reference '{bank_reference}' submitted successfully! "
                f"Our school cashier/accountant will verify and issue your digital receipt."
            )
            return redirect('parent_portal')

    return render(request, 'finance/parent_pay.html', {
        'invoice': invoice,
        'student': invoice.student,
        'remaining_balance': invoice.remaining_balance,
    })

