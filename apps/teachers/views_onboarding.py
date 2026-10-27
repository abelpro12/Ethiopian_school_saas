import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from django.http import JsonResponse

from apps.teachers.models import (
    TeacherProfile, StaffProfile, StaffDocument, StaffDocumentType,
    TeacherVacancy, TeacherApplication, VacancyStatus, CandidateApplicationStatus,
    Department, EmploymentStatus
)
from apps.academics.models import Subject
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


# --- Teacher Recruitment & Vacancy Subsystem Views (Requirement 9) ---

@login_required
@school_context_required
def vacancies_list_view(request):
    """
    Teacher Vacancies & Recruitment Hub.
    Allows administrators to create teacher vacancies, define required subject,
    qualifications, experience, and manage the candidate pipeline.
    """
    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
        messages.error(request, "Permission denied.")
        return redirect('teachers:management')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        dept_id = request.POST.get('department_id')
        subj_id = request.POST.get('subject_id')
        qual = request.POST.get('required_qualification', '').strip()
        exp = int(request.POST.get('min_years_experience', 2) or 2)
        emp_type = request.POST.get('employment_type', EmploymentStatus.FULL_TIME)
        open_pos = int(request.POST.get('open_positions', 1) or 1)
        deadline_str = request.POST.get('application_deadline')
        desc = request.POST.get('description', '').strip()
        reqs = request.POST.get('requirements', '').strip()

        dept = Department.objects.filter(school=school, id=dept_id).first() if dept_id else None
        subj = Subject.objects.filter(school=school, id=subj_id).first() if subj_id else None
        deadline = datetime.date.today() + datetime.timedelta(days=30)
        if deadline_str:
            try:
                deadline = datetime.date.fromisoformat(deadline_str)
            except ValueError:
                pass

        if not title or not qual:
            messages.error(request, "Vacancy title and required qualification are mandatory.")
        else:
            vac = TeacherVacancy.objects.create(
                school=school,
                title=title,
                department=dept,
                subject=subj,
                required_qualification=qual,
                min_years_experience=exp,
                employment_type=emp_type,
                open_positions=open_pos,
                application_deadline=deadline,
                description=desc,
                requirements=reqs,
                created_by=request.user,
                status=VacancyStatus.OPEN
            )
            AuditService.log_action(
                school=school,
                user=request.user,
                action='CREATE_TEACHER_VACANCY',
                object_type='TeacherVacancy',
                object_id=str(vac.id),
                details={'title': title, 'qualification': qual}
            )
            messages.success(request, f"Teacher vacancy '{title}' published successfully.")
        return redirect('teachers:vacancies_list')

    vacancies = TeacherVacancy.objects.filter(school=school).select_related('department', 'subject').prefetch_related('applications')
    departments = Department.objects.filter(school=school).order_by('name')
    subjects = Subject.objects.filter(school=school).order_by('name')

    context = {
        'vacancies': vacancies,
        'departments': departments,
        'subjects': subjects,
        'employment_types': EmploymentStatus.choices,
        'today': datetime.date.today().isoformat(),
        'default_deadline': (datetime.date.today() + datetime.timedelta(days=30)).isoformat(),
    }
    return render(request, 'teachers/vacancies_list.html', context)


@login_required
@school_context_required
def vacancy_detail_and_applications_view(request, vacancy_id):
    """
    Displays details for a specific vacancy and its candidate applications.
    Allows submitting a new candidate application or recording test/interview results.
    """
    school = get_school_context(request)
    vacancy = get_object_or_404(TeacherVacancy, id=vacancy_id, school=school)

    if request.method == 'POST':
        # Add new candidate application
        f_name = request.POST.get('first_name', '').strip()
        l_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        highest_qual = request.POST.get('highest_qualification', '').strip()
        spec = request.POST.get('specialization', '').strip()
        exp_years = int(request.POST.get('years_of_experience', 0) or 0)
        cv_file = request.FILES.get('cv_resume')
        cover = request.POST.get('cover_letter', '').strip()

        if not f_name or not l_name or not email or not phone:
            messages.error(request, "Candidate name, email, and phone number are required.")
        else:
            app = TeacherApplication.objects.create(
                school=school,
                vacancy=vacancy,
                first_name=f_name,
                last_name=l_name,
                email=email,
                phone=phone,
                highest_qualification=highest_qual,
                specialization=spec,
                years_of_experience=exp_years,
                cv_resume=cv_file,
                cover_letter=cover,
                status=CandidateApplicationStatus.SUBMITTED
            )
            AuditService.log_action(
                school=school,
                user=request.user,
                action='REGISTER_TEACHER_CANDIDATE',
                object_type='TeacherApplication',
                object_id=str(app.id),
                details={'candidate': app.full_name, 'vacancy': vacancy.title}
            )
            messages.success(request, f"Candidate {app.full_name} registered successfully for '{vacancy.title}'.")
        return redirect('teachers:vacancy_detail', vacancy_id=vacancy.id)

    applications = vacancy.applications.all().order_by('-created_at')

    context = {
        'vacancy': vacancy,
        'applications': applications,
        'statuses': CandidateApplicationStatus.choices,
        'today': datetime.date.today().isoformat(),
    }
    return render(request, 'teachers/vacancy_detail.html', context)


@login_required
@school_context_required
def update_application_status_view(request, application_id):
    """
    Updates a candidate application's recruitment status, test score, interview score,
    and interviewer notes.
    """
    if request.method != 'POST':
        return redirect('teachers:vacancies_list')

    school = get_school_context(request)
    app = get_object_or_404(TeacherApplication, id=application_id, school=school)

    new_status = request.POST.get('status', app.status)
    test_d = request.POST.get('test_date')
    test_sc = request.POST.get('test_score')
    interview_d = request.POST.get('interview_date')
    interview_sc = request.POST.get('interview_score')
    notes = request.POST.get('interviewer_notes', app.interviewer_notes or '').strip()

    if new_status in CandidateApplicationStatus.values:
        app.status = new_status
    if test_d:
        try:
            app.test_date = datetime.date.fromisoformat(test_d)
        except ValueError:
            pass
    if test_sc:
        try:
            app.test_score = float(test_sc)
        except ValueError:
            pass
    if interview_d:
        try:
            app.interview_date = datetime.date.fromisoformat(interview_d)
        except ValueError:
            pass
    if interview_sc:
        try:
            app.interview_score = float(interview_sc)
        except ValueError:
            pass
    app.interviewer_notes = notes
    app.save()

    AuditService.log_action(
        school=school,
        user=request.user,
        action='UPDATE_CANDIDATE_STATUS',
        object_type='TeacherApplication',
        object_id=str(app.id),
        details={'candidate': app.full_name, 'new_status': app.status}
    )
    messages.success(request, f"Candidate record for {app.full_name} updated ({app.get_status_display()}).")
    return redirect('teachers:vacancy_detail', vacancy_id=app.vacancy.id)


@login_required
@school_context_required
def convert_candidate_view(request, application_id):
    """
    1-click Conversion: Converts an accepted candidate into an active Teacher user and profile.
    Automatically assigns next Employee ID, provisions system login, and links uploaded CV (Requirement 9).
    """
    if request.method != 'POST':
        return redirect('teachers:vacancies_list')

    school = get_school_context(request)
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.HR_MANAGER]:
        messages.error(request, "Permission denied.")
        return redirect('teachers:vacancies_list')

    app = get_object_or_404(TeacherApplication, id=application_id, school=school)

    try:
        profile = app.convert_to_teacher()
        invite_msg = ""
        if profile.user.email:
            from apps.accounts.utils import generate_account_setup_url
            from apps.notifications.services import EmailService
            setup_url = generate_account_setup_url(request, profile.user)
            sent = EmailService.send_user_invitation_email(school, profile.user, setup_url)
            if sent:
                invite_msg = f" Password setup invitation sent to {profile.user.email}."
            else:
                invite_msg = f" Invitation email could not be sent to {profile.user.email}; account setup is pending."
        else:
            invite_msg = " No email provided on application; account setup is pending."

        messages.success(
            request,
            f"Successfully appointed and converted {app.full_name} into active Teacher! "
            f"Generated Employee ID: {profile.employee_id}, Username: {profile.user.username}.{invite_msg}"
        )
    except Exception as e:
        messages.error(request, f"Error converting candidate to teacher: {e}")

    return redirect('teachers:vacancy_detail', vacancy_id=app.vacancy.id)

