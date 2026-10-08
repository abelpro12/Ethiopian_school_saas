import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.http import JsonResponse

from apps.teachers.models import TeacherProfile, StaffProfile, StaffDocument, StaffDocumentType
from apps.accounts.models import UserRole
from apps.audit.services import AuditService
from apps.platform_management.decorators import school_context_required


def get_school_context(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)


@login_required
@school_context_required
def onboarding_dashboard_view(request):
    """
    Teacher Recruitment & Onboarding Pipeline Hub.
    Visualizes candidate progression across stages:
    APPLIED -> INTERVIEWED -> OFFERED -> ONBOARDING -> ACTIVE (or REJECTED)
    """
    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
        messages.error(request, "Access restricted to school administrators and HR managers.")
        return redirect('teachers:management')

    stage_filter = request.GET.get('stage', '').strip()
    search_query = request.GET.get('q', '').strip()

    teachers = TeacherProfile.objects.filter(school=school).select_related('user', 'department_obj').prefetch_related(
        'staff_documents'
    ).order_by('-user__date_joined')

    if stage_filter:
        teachers = teachers.filter(onboarding_status=stage_filter)

    if search_query:
        teachers = teachers.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(department__icontains=search_query) |
            Q(specialization__icontains=search_query)
        )

    # Stage metrics
    all_qs = TeacherProfile.objects.filter(school=school)
    total_count = all_qs.count()
    applied_count = all_qs.filter(onboarding_status='APPLIED').count()
    interviewed_count = all_qs.filter(onboarding_status='INTERVIEWED').count()
    offered_count = all_qs.filter(onboarding_status='OFFERED').count()
    onboarding_count = all_qs.filter(onboarding_status='ONBOARDING').count()
    active_count = all_qs.filter(onboarding_status='ACTIVE').count()
    rejected_count = all_qs.filter(onboarding_status='REJECTED').count()

    context = {
        'teachers': teachers,
        'total_count': total_count,
        'applied_count': applied_count,
        'interviewed_count': interviewed_count,
        'offered_count': offered_count,
        'onboarding_count': onboarding_count,
        'active_count': active_count,
        'rejected_count': rejected_count,
        'stage_filter': stage_filter,
        'search_query': search_query,
        'document_types': StaffDocumentType.choices,
    }
    return render(request, 'teachers/onboarding_dashboard.html', context)


@login_required
@school_context_required
def update_onboarding_stage_view(request, teacher_id):
    """
    Updates a teacher's recruitment stage, checklist items, and emergency contact details.
    """
    if request.method != 'POST':
        return redirect('teachers:onboarding_dashboard')

    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
        messages.error(request, "Permission denied.")
        return redirect('teachers:onboarding_dashboard')

    teacher = get_object_or_404(TeacherProfile, id=teacher_id, school=school)
    new_stage = request.POST.get('onboarding_status', teacher.onboarding_status)
    background_check = request.POST.get('background_check_completed') == '1'
    contract_signed = request.POST.get('contract_signed') == '1'
    emergency_name = request.POST.get('emergency_contact_name', teacher.emergency_contact_name or '').strip()
    emergency_phone = request.POST.get('emergency_contact_phone', teacher.emergency_contact_phone or '').strip()

    valid_stages = ['APPLIED', 'INTERVIEWED', 'OFFERED', 'ONBOARDING', 'ACTIVE', 'REJECTED']
    if new_stage in valid_stages:
        old_stage = teacher.onboarding_status
        teacher.onboarding_status = new_stage
        teacher.background_check_completed = background_check
        teacher.contract_signed = contract_signed
        teacher.emergency_contact_name = emergency_name
        teacher.emergency_contact_phone = emergency_phone
        teacher.save()

        AuditService.log_action(
            school=school,
            user=request.user,
            action='UPDATE_TEACHER_ONBOARDING_STAGE',
            object_type='TeacherProfile',
            object_id=str(teacher.id),
            details={
                'teacher': teacher.user.get_full_name(),
                'old_stage': old_stage,
                'new_stage': new_stage,
                'background_check': background_check,
                'contract_signed': contract_signed
            }
        )
        messages.success(request, f"Updated onboarding profile for {teacher.user.get_full_name()} ({teacher.get_onboarding_status_display()}).")
    else:
        messages.error(request, f"Invalid onboarding stage '{new_stage}'.")

    return redirect('teachers:onboarding_dashboard')


@login_required
@school_context_required
def upload_staff_document_view(request):
    """
    Uploads a credential, contract, or verification document for a teacher or staff member.
    """
    if request.method != 'POST':
        return redirect('teachers:onboarding_dashboard')

    school = get_school_context(request)
    teacher_id = request.POST.get('teacher_id')
    staff_id = request.POST.get('staff_id')
    doc_type = request.POST.get('document_type', StaffDocumentType.EMPLOYMENT)
    title = request.POST.get('title', '').strip()
    file_obj = request.FILES.get('file')
    expiry_date_str = request.POST.get('expiry_date')
    notes = request.POST.get('notes', '').strip()

    if not title or not file_obj:
        messages.error(request, "Document title and file are required.")
        return redirect('teachers:onboarding_dashboard')

    teacher = None
    staff = None
    if teacher_id:
        teacher = get_object_or_404(TeacherProfile, id=teacher_id, school=school)
    elif staff_id:
        staff = get_object_or_404(StaffProfile, id=staff_id, school=school)
    else:
        messages.error(request, "Please specify a teacher or staff member.")
        return redirect('teachers:onboarding_dashboard')

    expiry_date = None
    if expiry_date_str:
        try:
            expiry_date = datetime.date.fromisoformat(expiry_date_str)
        except ValueError:
            pass

    doc = StaffDocument.objects.create(
        school=school,
        teacher=teacher,
        staff=staff,
        document_type=doc_type,
        title=title,
        file=file_obj,
        expiry_date=expiry_date,
        notes=notes,
        uploaded_by=request.user,
        verification_status='PENDING'
    )

    owner_name = teacher.user.get_full_name() if teacher else staff.user.get_full_name()
    AuditService.log_action(
        school=school,
        user=request.user,
        action='UPLOAD_STAFF_DOCUMENT',
        object_type='StaffDocument',
        object_id=str(doc.id),
        details={
            'title': title,
            'owner': owner_name,
            'type': doc_type
        }
    )

    messages.success(request, f"Document '{title}' uploaded successfully for {owner_name}. Pending verification.")
    return redirect('teachers:onboarding_dashboard')


@login_required
@school_context_required
def verify_staff_document_view(request, document_id):
    """
    Verifies or rejects a staff/teacher credential document.
    """
    if request.method != 'POST':
        return redirect('teachers:onboarding_dashboard')

    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
        messages.error(request, "Permission denied.")
        return redirect('teachers:onboarding_dashboard')

    doc = get_object_or_404(StaffDocument, id=document_id, school=school)
    action = request.POST.get('action', 'verify').strip().lower()
    notes = request.POST.get('notes', '').strip()

    if action == 'verify':
        doc.verification_status = 'VERIFIED'
        doc.verified_by = request.user
        doc.verified_at = timezone.now()
        if notes:
            doc.notes = notes
        doc.save()
        messages.success(request, f"Document '{doc.title}' has been officially verified and approved.")
    elif action == 'reject':
        doc.verification_status = 'REJECTED'
        doc.verified_by = request.user
        doc.verified_at = timezone.now()
        if notes:
            doc.notes = notes
        doc.save()
        messages.warning(request, f"Document '{doc.title}' has been marked as rejected.")

    AuditService.log_action(
        school=school,
        user=request.user,
        action=f"DOCUMENT_{action.upper()}",
        object_type='StaffDocument',
        object_id=str(doc.id),
        details={
            'title': doc.title,
            'status': doc.verification_status,
            'notes': notes
        }
    )

    return redirect('teachers:onboarding_dashboard')
