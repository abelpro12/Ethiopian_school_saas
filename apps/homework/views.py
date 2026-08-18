import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from apps.accounts.models import UserRole
from .models import HomeworkAssignment, HomeworkSubmission, HomeworkStatus, SubmissionStatus


@login_required
def homework_list_view(request):
    """Unified homework list — teachers see their posted assignments, students see pending homework."""
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None)
    user = request.user

    if user.role == UserRole.TEACHER:
        teacher = getattr(user, 'teacher_profile', None)
        from apps.teachers.models import TeacherAssignment
        if teacher and current_ay:
            section_ids = TeacherAssignment.objects.filter(
                school=school, teacher=teacher, academic_year=current_ay
            ).values_list('section_id', flat=True)
            assignments = HomeworkAssignment.objects.filter(
                school=school, section_id__in=section_ids, assigned_by=user
            ).select_related('subject', 'section__grade')
        else:
            assignments = HomeworkAssignment.objects.filter(school=school, assigned_by=user)
        return render(request, 'homework/teacher_list.html', {'assignments': assignments, 'current_ay': current_ay})

    elif user.role == UserRole.STUDENT:
        student_profile = getattr(user, 'student_profile', None)
        from apps.enrollment.models import StudentEnrollment
        if student_profile and current_ay:
            enrollment = StudentEnrollment.objects.filter(school=school, student=student_profile, academic_year=current_ay).first()
            if enrollment:
                hw_list = HomeworkAssignment.objects.filter(
                    school=school, section=enrollment.section, status=HomeworkStatus.ACTIVE
                ).select_related('subject', 'assigned_by')
            else:
                hw_list = []
        else:
            hw_list = []
        # Get submission statuses
        hw_with_status = []
        for hw in hw_list:
            sub = HomeworkSubmission.objects.filter(school=school, homework=hw, student=user).first()
            hw_with_status.append({'hw': hw, 'submission': sub})
        return render(request, 'homework/student_view.html', {'hw_with_status': hw_with_status, 'current_ay': current_ay})

    # Admin view — all homework
    all_hw = HomeworkAssignment.objects.filter(school=school).select_related('subject', 'section__grade', 'assigned_by')
    if current_ay:
        all_hw = all_hw.filter(academic_year=current_ay)
    return render(request, 'homework/admin_list.html', {'assignments': all_hw, 'current_ay': current_ay})


@login_required
def create_homework_view(request):
    """Teacher creates a new homework assignment."""
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None)
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.TEACHER, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL]:
        messages.error(request, "Unauthorized.")
        return redirect('messaging:inbox')

    from apps.academics.models import Subject, Section
    from apps.teachers.models import TeacherAssignment
    teacher = getattr(user, 'teacher_profile', None)
    if teacher and current_ay:
        t_assignments = TeacherAssignment.objects.filter(school=school, teacher=teacher, academic_year=current_ay).select_related('subject', 'section__grade')
        subjects = list({ta.subject for ta in t_assignments})
        sections = list({ta.section for ta in t_assignments})
    else:
        subjects = Subject.objects.filter(school=school)
        sections = Section.objects.filter(school=school)
        sections = Section.objects.filter(school=school)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        subject_id = request.POST.get('subject_id')
        section_id = request.POST.get('section_id')
        due_date_str = request.POST.get('due_date')
        max_marks = request.POST.get('max_marks') or None

        try:
            due_date = datetime.datetime.strptime(due_date_str, '%Y-%m-%d').date()
            subject = Subject.objects.get(id=subject_id, school=school)
            section = Section.objects.get(id=section_id, school=school)
            hw = HomeworkAssignment.objects.create(
                school=school,
                academic_year=current_ay,
                title=title, description=description,
                subject=subject, section=section,
                assigned_by=user, due_date=due_date,
                max_marks=max_marks or 10.0
            )
            messages.success(request, f"Homework '{hw.title}' posted for Section {section.name}.")
            return redirect('homework:list')
        except Exception as e:
            messages.error(request, f"Error creating homework: {e}")

    return render(request, 'homework/create.html', {
        'subjects': subjects,
        'sections': sections,
        'today': datetime.date.today().isoformat(),
    })


@login_required
def submit_homework_view(request, hw_id):
    """Student submits a homework assignment."""
    school = getattr(request, 'school', None)
    hw = get_object_or_404(HomeworkAssignment, id=hw_id, school=school)
    user = request.user

    existing = HomeworkSubmission.objects.filter(school=school, homework=hw, student=user).first()

    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        attachment = request.FILES.get('attachment')
        is_late = datetime.date.today() > hw.due_date

        sub, created = HomeworkSubmission.objects.update_or_create(
            school=school, homework=hw, student=user,
            defaults={
                'notes': notes,
                'status': SubmissionStatus.LATE if is_late else SubmissionStatus.SUBMITTED,
            }
        )
        if attachment:
            sub.attachment = attachment
            sub.save()
        msg = "Homework re-submitted." if not created else "Homework submitted successfully!"
        if is_late:
            msg += " (Late submission)"
        messages.success(request, msg)
        return redirect('homework:list')

    return render(request, 'homework/submit.html', {'hw': hw, 'existing': existing})


@login_required
def homework_detail_view(request, hw_id):
    """Teacher views submissions for a homework assignment."""
    school = getattr(request, 'school', None)
    hw = get_object_or_404(HomeworkAssignment, id=hw_id, school=school)
    submissions = HomeworkSubmission.objects.filter(school=school, homework=hw).select_related('student__student_profile')
    return render(request, 'homework/detail.html', {'hw': hw, 'submissions': submissions})
