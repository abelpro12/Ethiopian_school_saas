import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.models import UserRole
from apps.students.models import StudentProfile
from apps.parents.models import GuardianRelationship
from apps.messaging.models import Conversation, Message
from .models import DisciplinaryIncident, DisciplinaryAction, IncidentStatus, DisciplinaryActionType


@login_required
def incident_log_view(request):
    """List all disciplinary incidents for this school/year."""
    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None)
    user = request.user

    if user.role not in [UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.TEACHER, UserRole.SUPER_ADMIN]:
        messages.error(request, "Unauthorized.")
        return redirect('index')

    incidents = DisciplinaryIncident.objects.filter(school=school).select_related('reported_by', 'reviewed_by')
    if current_ay:
        incidents = incidents.filter(academic_year=current_ay)

    # Severity filter
    severity = request.GET.get('severity')
    if severity:
        incidents = incidents.filter(severity=severity)
    status_filter = request.GET.get('status')
    if status_filter:
        incidents = incidents.filter(status=status_filter)

    return render(request, 'discipline/incident_log.html', {
        'incidents': incidents,
        'current_ay': current_ay,
        'severity_choices': DisciplinaryIncident._meta.get_field('severity').choices,
        'status_choices': DisciplinaryIncident._meta.get_field('status').choices,
    })


@login_required
def log_incident_view(request):
    """Log a new disciplinary incident."""
    from apps.academics.models import AcademicYear, Grade, Section
    from apps.enrollment.models import StudentEnrollment

    school = getattr(request, 'school', None)
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date').first()
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.TEACHER]:
        messages.error(request, "Unauthorized.")
        return redirect('index')

    # Fetch ONLY enrolled students in active academic year
    enrollments = StudentEnrollment.objects.filter(school=school)
    if current_ay:
        enrollments = enrollments.filter(academic_year=current_ay)

    enrollments = enrollments.select_related('student__user', 'grade', 'section').order_by(
        'grade__level', 'grade__stream_type', 'section__name', 'student__first_name', 'student__last_name'
    )

    grouped_students = {}
    for en in enrollments:
        grd = en.grade
        sec = en.section
        grd_title = f"Grade {grd.level}" if grd else "Unassigned Grade"
        if grd and grd.stream_type != 'GEN':
            grd_title += f" ({grd.get_stream_type_display()})"
        if sec:
            grd_title += f" — Section {sec.name}"

        if grd_title not in grouped_students:
            grouped_students[grd_title] = []

        grouped_students[grd_title].append({
            'id': en.student.id,
            'full_name': en.student.full_name,
            'student_id': en.student.student_id or en.student.user.username,
            'grade_id': en.grade_id,
            'section_id': en.section_id,
        })

    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    sections = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category')
        severity = request.POST.get('severity')
        description = request.POST.get('description', '').strip()
        incident_date_str = request.POST.get('incident_date')
        location = request.POST.get('location', '').strip()
        student_ids = request.POST.getlist('student_ids')
        action_type = request.POST.get('action_type')
        action_desc = request.POST.get('action_description', '').strip()

        try:
            incident_date = datetime.datetime.strptime(incident_date_str, '%Y-%m-%d').date()
            incident = DisciplinaryIncident.objects.create(
                school=school,
                academic_year=current_ay,
                title=title, category=category, severity=severity,
                description=description, incident_date=incident_date,
                location=location, reported_by=user
            )
            if student_ids:
                involved_students = StudentProfile.objects.filter(id__in=student_ids, school=school)
                incident.students_involved.set(involved_students)
                # Create action for each student if action type selected
                if action_type:
                    for student in involved_students:
                        DisciplinaryAction.objects.create(
                            school=school, incident=incident, student=student,
                            action_type=action_type, description=action_desc,
                            effective_date=incident_date, administered_by=user
                        )
            messages.success(request, f"Incident '{title}' logged successfully.")
            return redirect('discipline:detail', incident_id=incident.id)
        except Exception as e:
            messages.error(request, f"Error logging incident: {e}")

    return render(request, 'discipline/log_incident.html', {
        'grouped_students': grouped_students,
        'grades': grades,
        'sections': sections,
        'current_ay': current_ay,
        'category_choices': DisciplinaryIncident._meta.get_field('category').choices,
        'severity_choices': DisciplinaryIncident._meta.get_field('severity').choices,
        'action_choices': DisciplinaryAction._meta.get_field('action_type').choices,
        'today': datetime.date.today().isoformat(),
    })



@login_required
def incident_detail_view(request, incident_id):
    """View details and actions for a specific incident."""
    school = getattr(request, 'school', None)
    incident = get_object_or_404(DisciplinaryIncident, id=incident_id, school=school)
    actions = DisciplinaryAction.objects.filter(school=school, incident=incident).select_related('student', 'administered_by')

    if request.method == 'POST':
        action_type_post = request.POST.get('action')
        if action_type_post == 'update_status':
            new_status = request.POST.get('status')
            if new_status in dict(IncidentStatus.choices):
                incident.status = new_status
                incident.reviewed_by = request.user
                incident.save()
                messages.success(request, f"Incident status updated to {incident.get_status_display()}.")
        elif action_type_post == 'notify_parent':
            incident.parent_notified = True
            incident.parent_notification_date = datetime.date.today()
            incident.save()

            # Send automated message to parents of all involved students
            for student in incident.students_involved.all():
                guardians = GuardianRelationship.objects.filter(student=student, school=school).select_related('parent__user')
                for guardian in guardians:
                    parent_user = guardian.parent.user
                    subject = f"Disciplinary Notice: {student.first_name} {student.last_name}"
                    body = f"Dear {parent_user.get_full_name()},\n\nWe are writing to inform you of a disciplinary incident involving {student.first_name} on {incident.incident_date.strftime('%b %d, %Y')}.\n\nCategory: {incident.get_category_display()}\nSeverity: {incident.get_severity_display()}\n\nPlease contact the school administration for further details.\n\nRegards,\n{school.name} Administration"
                    
                    conversation = Conversation.objects.create(
                        school=school,
                        subject=subject,
                        created_by=request.user
                    )
                    conversation.participants.add(request.user, parent_user)
                    
                    Message.objects.create(
                        school=school,
                        conversation=conversation,
                        sender=request.user,
                        body=body
                    )

            messages.success(request, "Parent notification recorded and messages sent.")
        return redirect('discipline:detail', incident_id=incident_id)

    return render(request, 'discipline/incident_detail.html', {
        'incident': incident,
        'actions': actions,
        'status_choices': IncidentStatus.choices,
    })
