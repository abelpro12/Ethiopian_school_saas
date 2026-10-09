import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.http import HttpResponse

from apps.students.models import StudentClearance, StudentProfile, ClearanceStatus, WithdrawalReason, WithdrawalType
from apps.accounts.models import UserRole
from apps.enrollment.models import StudentEnrollment
from apps.students.clearance_service import ClearanceService
from apps.platform_management.decorators import school_context_required


def get_school_context(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)


@login_required
@school_context_required
def clearance_dashboard_view(request):
    school = get_school_context(request)
    status_filter = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()

    clearances = StudentClearance.objects.filter(school=school).select_related(
        'student', 'enrollment__section', 'enrollment__grade', 'academic_year',
        'final_approved_by'
    )

    if status_filter:
        clearances = clearances.filter(status=status_filter)

    if search_query:
        clearances = clearances.filter(
            Q(clearance_number__icontains=search_query) |
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__student_id__icontains=search_query) |
            Q(destination_school__icontains=search_query)
        )

    # Statistics
    stats_base = StudentClearance.objects.filter(school=school)
    total_count = stats_base.count()
    pending_count = stats_base.filter(status__in=[ClearanceStatus.INITIATED, ClearanceStatus.UNDER_REVIEW]).count()
    approved_count = stats_base.filter(status=ClearanceStatus.APPROVED).count()
    rejected_count = stats_base.filter(status=ClearanceStatus.REJECTED).count()

    context = {
        'clearances': clearances[:100],
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'status_filter': status_filter,
        'search_query': search_query,
        'status_choices': ClearanceStatus.choices,
        'withdrawal_reasons': WithdrawalReason.choices,
    }
    return render(request, 'students/clearance_dashboard.html', context)


@login_required
@school_context_required
def clearance_initiate_view(request):
    school = get_school_context(request)
    selected_student_id = request.GET.get('student_id')
    preselected_student = None
    operational_summary = None

    if selected_student_id:
        preselected_student = StudentProfile.objects.filter(school=school, id=selected_student_id).first()
        if preselected_student:
            operational_summary = ClearanceService.get_student_operational_summary(preselected_student)

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        withdrawal_type_id = request.POST.get('withdrawal_type_id')
        withdrawal_reason = request.POST.get('withdrawal_reason', WithdrawalReason.TRANSFER)
        reason_details = request.POST.get('reason_details', '')
        destination_school = request.POST.get('destination_school', '')
        effective_date_str = request.POST.get('effective_date')

        student = get_object_or_404(StudentProfile, id=student_id, school=school)
        effective_date = datetime.date.today()
        if effective_date_str:
            try:
                effective_date = datetime.date.fromisoformat(effective_date_str)
            except ValueError:
                pass

        withdrawal_type = None
        if withdrawal_type_id:
            withdrawal_type = WithdrawalType.objects.filter(school=school, id=withdrawal_type_id).first()

        try:
            clearance = ClearanceService.initiate_clearance(
                school=school,
                student=student,
                withdrawal_reason=withdrawal_reason,
                reason_details=reason_details,
                destination_school=destination_school,
                effective_date=effective_date,
                user=request.user,
                withdrawal_type=withdrawal_type
            )
            messages.success(request, f"Clearance workflow initiated successfully for {student.full_name} ({clearance.clearance_number}).")
            return redirect('students:clearance_detail', clearance_id=clearance.id)
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))
        except Exception as e:
            messages.error(request, f"Failed to initiate clearance: {e}")

    # Active students available for clearance
    students = StudentProfile.objects.filter(school=school, status='ACTIVE').order_by('first_name', 'last_name')[:300]
    withdrawal_types = WithdrawalType.objects.filter(school=school, is_active=True).order_by('name')
    if not withdrawal_types.exists():
        WithdrawalType.get_or_create_defaults(school)
        withdrawal_types = WithdrawalType.objects.filter(school=school, is_active=True).order_by('name')

    context = {
        'students': students,
        'preselected_student': preselected_student,
        'operational_summary': operational_summary,
        'withdrawal_types': withdrawal_types,
        'withdrawal_reasons': WithdrawalReason.choices,
        'today': datetime.date.today().isoformat(),
    }
    return render(request, 'students/clearance_initiate.html', context)


@login_required
@school_context_required
def clearance_detail_view(request, clearance_id):
    school = get_school_context(request)
    clearance = get_object_or_404(
        StudentClearance.objects.select_related(
            'student', 'enrollment__section', 'enrollment__grade', 'academic_year',
            'library_cleared_by', 'finance_cleared_by', 'academic_cleared_by', 'property_cleared_by',
            'final_approved_by', 'created_by'
        ),
        id=clearance_id,
        school=school
    )

    operational_summary = ClearanceService.get_student_operational_summary(clearance.student)

    # User permissions
    user_role = getattr(request.user, 'role', '')
    can_sign_library = user_role in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'LIBRARIAN']
    can_sign_finance = user_role in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'ACCOUNTANT']
    can_sign_academic = user_role in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'TEACHER', 'REGISTRAR']
    can_sign_property = user_role in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']
    can_finalize = user_role in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']

    context = {
        'clearance': clearance,
        'student': clearance.student,
        'summary': operational_summary,
        'can_sign_library': can_sign_library,
        'can_sign_finance': can_sign_finance,
        'can_sign_academic': can_sign_academic,
        'can_sign_property': can_sign_property,
        'can_finalize': can_finalize,
    }
    return render(request, 'students/clearance_detail.html', context)


@login_required
@school_context_required
def clearance_sign_department_view(request, clearance_id):
    if request.method != 'POST':
        return redirect('students:clearance_detail', clearance_id=clearance_id)

    school = get_school_context(request)
    clearance = get_object_or_404(StudentClearance, id=clearance_id, school=school)

    department = request.POST.get('department', '').strip().lower()
    cleared = request.POST.get('cleared') == '1'
    remarks = request.POST.get('remarks', '').strip()

    try:
        ClearanceService.sign_department(
            school=school,
            clearance=clearance,
            department=department,
            cleared=cleared,
            remarks=remarks,
            user=request.user
        )
        status_text = "cleared" if cleared else "flagged / un-cleared"
        messages.success(request, f"{department.capitalize()} department successfully {status_text} for {clearance.student.full_name}.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))
    except Exception as e:
        messages.error(request, f"Error updating sign-off: {e}")

    return redirect('students:clearance_detail', clearance_id=clearance.id)


@login_required
@school_context_required
def clearance_finalize_view(request, clearance_id):
    if request.method != 'POST':
        return redirect('students:clearance_detail', clearance_id=clearance_id)

    school = get_school_context(request)
    clearance = get_object_or_404(StudentClearance, id=clearance_id, school=school)

    action = request.POST.get('action', 'approve').strip().lower()
    final_remarks = request.POST.get('final_remarks', '').strip()
    is_approved = (action == 'approve')

    try:
        ClearanceService.finalize_clearance(
            school=school,
            clearance=clearance,
            approved=is_approved,
            final_remarks=final_remarks,
            user=request.user
        )
        if is_approved:
            messages.success(request, f"Clearance {clearance.clearance_number} officially APPROVED. Certificate issued and student marked as {clearance.student.status}.")
        else:
            messages.warning(request, f"Clearance {clearance.clearance_number} has been officially REJECTED / BLOCKED.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))
    except Exception as e:
        messages.error(request, f"Error finalizing clearance: {e}")

    return redirect('students:clearance_detail', clearance_id=clearance.id)


@login_required
@school_context_required
def clearance_certificate_view(request, clearance_id):
    school = get_school_context(request)
    clearance = get_object_or_404(
        StudentClearance.objects.select_related(
            'student', 'enrollment__section', 'enrollment__grade', 'academic_year',
            'library_cleared_by', 'finance_cleared_by', 'academic_cleared_by', 'property_cleared_by',
            'final_approved_by'
        ),
        id=clearance_id,
        school=school
    )

    if clearance.status != ClearanceStatus.APPROVED and not clearance.certificate_issued:
        messages.error(request, "Clearance certificate cannot be generated until final administrative approval is granted.")
        return redirect('students:clearance_detail', clearance_id=clearance.id)

    context = {
        'school': school,
        'clearance': clearance,
        'student': clearance.student,
        'enrollment': clearance.enrollment,
        'printed_at': datetime.datetime.now(),
    }
    return render(request, 'students/clearance_certificate.html', context)


@login_required
@school_context_required
def withdrawal_types_list_view(request):
    """
    Admin management view for customizable withdrawal categories (Requirement 3).
    Allows Miss Helen / School Admins to configure withdrawal types, required documents,
    and required clearance steps.
    """
    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Permission denied.")
        return redirect('students:clearance_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        description = request.POST.get('description', '').strip()
        steps_raw = request.POST.get('required_clearance_steps', 'library,finance,academic,property')
        docs_raw = request.POST.get('required_documents', '')
        req_steps = [s.strip() for s in steps_raw.split(',') if s.strip()]
        req_docs = [d.strip() for d in docs_raw.split(',') if d.strip()]

        if not name:
            messages.error(request, "Withdrawal type name is required.")
        else:
            wtype, created = WithdrawalType.objects.get_or_create(
                school=school,
                name=name,
                defaults={
                    'code': code or name[:10].upper(),
                    'description': description,
                    'required_clearance_steps': req_steps,
                    'required_documents': req_docs,
                    'is_active': True,
                }
            )
            if not created:
                wtype.code = code or wtype.code
                wtype.description = description
                wtype.required_clearance_steps = req_steps
                wtype.required_documents = req_docs
                wtype.is_active = True
                wtype.save()
            messages.success(request, f"Withdrawal category '{name}' saved successfully.")
        return redirect('students:withdrawal_types_list')

    types = WithdrawalType.objects.filter(school=school).order_by('name')
    if not types.exists():
        WithdrawalType.get_or_create_defaults(school)
        types = WithdrawalType.objects.filter(school=school).order_by('name')

    context = {
        'withdrawal_types': types,
    }
    return render(request, 'students/withdrawal_types_list.html', context)

