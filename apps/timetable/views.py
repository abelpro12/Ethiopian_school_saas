import csv
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academics.models import PeriodSlot, TimetableSlot, Section, DayOfWeek, Subject, Grade, AcademicYear
from apps.teachers.models import TeacherAssignment, TeacherProfile
from apps.accounts.models import UserRole
from apps.timetable.conflict_checker import TimetableConflictChecker
from apps.timetable.generator_service import TimetableGeneratorService
from apps.audit.services import AuditService
from apps.tenants.utils import get_school

logger = logging.getLogger(__name__)


def check_admin_access(user):
    return user.role in [
        UserRole.SUPER_ADMIN,
        UserRole.SCHOOL_ADMIN,
        UserRole.PRINCIPAL,
        UserRole.REGISTRAR,
        UserRole.ACADEMIC_DIRECTOR if hasattr(UserRole, 'ACADEMIC_DIRECTOR') else UserRole.PRINCIPAL
    ]


@login_required
def manage_period_slots(request):
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = get_school(request)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_period':
            name = request.POST.get('name')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            shift = request.POST.get('shift', 'FULL_DAY')

            try:
                PeriodSlot.objects.create(
                    school=school, name=name, start_time=start_time, end_time=end_time, shift=shift
                )
                messages.success(request, f"Period slot '{name}' added successfully.")
            except Exception as e:
                messages.error(request, f"Error adding period slot: {e}")
        elif action == 'delete_period':
            period_id = request.POST.get('period_id')
            try:
                period = PeriodSlot.objects.get(id=period_id, school=school)
                period.delete()
                messages.success(request, "Period slot deleted successfully.")
            except PeriodSlot.DoesNotExist:
                messages.error(request, "Period slot not found.")

        return redirect('timetable:period_slots')

    periods = PeriodSlot.objects.filter(school=school).order_by('start_time')
    return render(request, 'timetable/period_slots.html', {'periods': periods})


@login_required
def manage_timetable(request):
    """
    Timetable Hub with support for:
    - Section-level scheduling & interactive drag-and-drop
    - Individual Teacher timetable view
    - Master school-wide schedule
    - Automated generator triggering
    """
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = get_school(request)
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    sections = Section.objects.filter(school=school, is_active=True).select_related('grade').order_by('grade__level', 'name')
    teachers = TeacherProfile.objects.filter(school=school).select_related('user').order_by('user__first_name', 'user__last_name')
    periods = PeriodSlot.objects.filter(school=school).order_by('start_time')

    days = [
        {'value': DayOfWeek.MONDAY.value, 'label': DayOfWeek.MONDAY.label},
        {'value': DayOfWeek.TUESDAY.value, 'label': DayOfWeek.TUESDAY.label},
        {'value': DayOfWeek.WEDNESDAY.value, 'label': DayOfWeek.WEDNESDAY.label},
        {'value': DayOfWeek.THURSDAY.value, 'label': DayOfWeek.THURSDAY.label},
        {'value': DayOfWeek.FRIDAY.value, 'label': DayOfWeek.FRIDAY.label},
    ]

    view_mode = request.GET.get('view_mode', 'section')  # 'section', 'teacher', 'master'
    selected_section_id = request.GET.get('section_id')
    selected_teacher_id = request.GET.get('teacher_id')

    selected_section = None
    selected_teacher = None
    timetable = {}
    assignments = []

    # 1. Section Mode
    if view_mode == 'section' and selected_section_id:
        selected_section = get_object_or_404(Section, id=selected_section_id, school=school)
        slots = TimetableSlot.objects.filter(
            school=school, section=selected_section
        ).select_related('subject', 'teacher__user', 'period_slot')

        for slot in slots:
            key = f"{slot.day_of_week}_{slot.period_slot.id}"
            timetable[key] = slot

        assignments = TeacherAssignment.objects.filter(
            school=school, section=selected_section
        )
        if current_ay:
            assignments = assignments.filter(academic_year=current_ay)
        assignments = assignments.select_related('subject', 'teacher__user')

    # 2. Teacher Mode
    elif view_mode == 'teacher' and selected_teacher_id:
        selected_teacher = get_object_or_404(TeacherProfile, id=selected_teacher_id, school=school)
        slots = TimetableSlot.objects.filter(
            school=school, teacher=selected_teacher
        ).select_related('subject', 'section__grade', 'period_slot')

        for slot in slots:
            key = f"{slot.day_of_week}_{slot.period_slot.id}"
            timetable[key] = slot

    # 3. Master Grid Mode
    master_grid = {}
    if view_mode == 'master':
        all_slots = TimetableSlot.objects.filter(school=school).select_related(
            'section__grade', 'subject', 'teacher__user', 'period_slot'
        )
        for s in sections:
            master_grid[s.id] = {}
        for slot in all_slots:
            if slot.section_id in master_grid:
                key = f"{slot.day_of_week}_{slot.period_slot_id}"
    grid_rows = []
    for period in periods:
        row_cells = []
        for d in days:
            slot = timetable.get(f"{d['value']}_{period.id}")
            row_cells.append({
                'day': d['value'],
                'period': period,
                'slot': slot
            })
        grid_rows.append({
            'period': period,
            'cells': row_cells
        })

    return render(request, 'timetable/manage.html', {
        'sections': sections,
        'teachers': teachers,
        'periods': periods,
        'days': days,
        'view_mode': view_mode,
        'selected_section': selected_section,
        'selected_teacher': selected_teacher,
        'timetable': timetable,
        'grid_rows': grid_rows,
        'assignments': assignments,
        'master_grid': master_grid,
        'current_ay': current_ay,
    })


@login_required
def assign_slot_htmx(request):
    """
    Standard or HTMX slot assignment with conflict validation.
    """
    if request.method != "POST" or not check_admin_access(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    section_id = request.POST.get('section_id')
    day = request.POST.get('day')
    period_id = request.POST.get('period_id')
    assignment_id = request.POST.get('assignment_id')
    room = request.POST.get('room', '').strip()

    try:
        section = Section.objects.get(id=section_id, school=school)
        period = PeriodSlot.objects.get(id=period_id, school=school)
        assignment = TeacherAssignment.objects.get(id=assignment_id, school=school)

        teacher = assignment.teacher
        subject = assignment.subject
        ay = assignment.academic_year

        TimetableConflictChecker.check_conflicts(school, section, teacher, room, day, period)

        slot, _ = TimetableSlot.objects.update_or_create(
            school=school,
            section=section,
            day_of_week=day,
            period_slot=period,
            defaults={
                'academic_year': ay,
                'subject': subject,
                'teacher': teacher,
                'room': room,
                'is_locked': False
            }
        )

        AuditService.log_action(
            school=school,
            user=request.user,
            action="TIMETABLE_SLOT_ASSIGNED",
            resource_type="TIMETABLE_SLOT",
            resource_id=str(slot.id),
            details={
                'section': section.name,
                'subject': subject.name,
                'teacher': str(teacher),
                'day': day,
                'period': period.name
            },
            ip_address=AuditService.get_client_ip(request)
        )

        return render(request, 'timetable/partials/slot_cell.html', {
            'slot': slot,
            'day': day,
            'period': period,
            'section': section
        })

    except ValidationError as e:
        return HttpResponse(
            f"<div class='p-2 bg-red-100 text-red-800 text-xs rounded border border-red-200 mt-2'>{e.messages[0]}</div>",
            status=400
        )
    except Exception as e:
        return HttpResponse(
            f"<div class='p-2 bg-red-100 text-red-800 text-xs rounded border border-red-200 mt-2'>Error: {str(e)}</div>",
            status=400
        )


@login_required
def remove_slot_htmx(request):
    """
    Deletes a timetable slot.
    """
    if request.method != "POST" or not check_admin_access(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    slot_id = request.POST.get('slot_id')

    try:
        slot = TimetableSlot.objects.get(id=slot_id, school=school)
        day = slot.day_of_week
        period = slot.period_slot
        section = slot.section

        AuditService.log_action(
            school=school,
            user=request.user,
            action="TIMETABLE_SLOT_REMOVED",
            resource_type="TIMETABLE_SLOT",
            resource_id=str(slot.id),
            details={
                'section': section.name,
                'subject': slot.subject.name,
                'day': day,
                'period': period.name
            },
            ip_address=AuditService.get_client_ip(request)
        )

        slot.delete()

        return render(request, 'timetable/partials/slot_cell.html', {
            'slot': None,
            'day': day,
            'period': period,
            'section': section
        })
    except Exception as e:
        return HttpResponse(f"Error: {e}", status=400)


@login_required
def move_or_swap_slot_api(request):
    """
    Interactive Drag-and-Drop / Move or Swap API.
    Moves a source slot to target (day, period), or cleanly swaps if target cell is already occupied.
    Validates zero conflicts in both directions.
    """
    if request.method != "POST" or not check_admin_access(request.user):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    school = get_school(request)
    source_slot_id = request.POST.get('source_slot_id')
    target_day = request.POST.get('target_day')
    target_period_id = request.POST.get('target_period_id')
    section_id = request.POST.get('section_id')

    if not all([source_slot_id, target_day, target_period_id, section_id]):
        return JsonResponse({'success': False, 'error': 'Missing required parameters.'}, status=400)

    try:
        section = Section.objects.get(id=section_id, school=school)
        source_slot = TimetableSlot.objects.get(id=source_slot_id, school=school, section=section)
        target_period = PeriodSlot.objects.get(id=target_period_id, school=school)

        if source_slot.is_locked:
            return JsonResponse({'success': False, 'error': 'This slot is pinned/locked. Unlock it first to move.'}, status=400)

        # Check if target cell already has a slot for this section
        target_slot = TimetableSlot.objects.filter(
            school=school, section=section, day_of_week=target_day, period_slot=target_period
        ).first()

        with transaction.atomic():
            if target_slot:
                # SWAP OPERATION
                if target_slot.is_locked:
                    return JsonResponse({'success': False, 'error': 'The target slot is pinned/locked and cannot be swapped.'}, status=400)

                # Check conflict for source moving to target slot
                TimetableConflictChecker.check_conflicts(
                    school=school,
                    section=section,
                    teacher=source_slot.teacher,
                    room=source_slot.room,
                    day_of_week=target_day,
                    period_slot=target_period,
                    exclude_slot_id=target_slot.id
                )

                # Check conflict for target moving to source slot
                TimetableConflictChecker.check_conflicts(
                    school=school,
                    section=section,
                    teacher=target_slot.teacher,
                    room=target_slot.room,
                    day_of_week=source_slot.day_of_week,
                    period_slot=source_slot.period_slot,
                    exclude_slot_id=source_slot.id
                )

                # Execute atomic swap without violating unique_together constraint
                orig_day = source_slot.day_of_week
                orig_period = source_slot.period_slot

                TimetableSlot.objects.filter(id=target_slot.id).update(day_of_week='SWAPPING')
                TimetableSlot.objects.filter(id=source_slot.id).update(day_of_week=target_day, period_slot=target_period)
                TimetableSlot.objects.filter(id=target_slot.id).update(day_of_week=orig_day, period_slot=orig_period)

                source_slot.refresh_from_db()
                target_slot.refresh_from_db()

                action_type = "SLOTS_SWAPPED"
                msg = f"Swapped {source_slot.subject.name} and {target_slot.subject.name} successfully."
            else:
                # MOVE OPERATION
                TimetableConflictChecker.check_conflicts(
                    school=school,
                    section=section,
                    teacher=source_slot.teacher,
                    room=source_slot.room,
                    day_of_week=target_day,
                    period_slot=target_period,
                    exclude_slot_id=source_slot.id
                )

                source_slot.day_of_week = target_day
                source_slot.period_slot = target_period
                source_slot.save()

                action_type = "SLOT_MOVED"
                msg = f"Moved {source_slot.subject.name} to {target_day} {target_period.name}."

            AuditService.log_action(
                school=school,
                user=request.user,
                action=f"TIMETABLE_{action_type}",
                resource_type="TIMETABLE_SLOT",
                resource_id=str(source_slot.id),
                details={'message': msg, 'section': section.name},
                ip_address=AuditService.get_client_ip(request)
            )

        return JsonResponse({'success': True, 'message': msg})

    except ValidationError as e:
        return JsonResponse({'success': False, 'error': e.messages[0]}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def toggle_slot_lock_api(request):
    """
    Toggles is_locked flag on a TimetableSlot to pin it against automatic regeneration.
    """
    if request.method != "POST" or not check_admin_access(request.user):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    school = get_school(request)
    slot_id = request.POST.get('slot_id')

    try:
        slot = TimetableSlot.objects.get(id=slot_id, school=school)
        slot.is_locked = not slot.is_locked
        slot.save(update_fields=['is_locked'])

        AuditService.log_action(
            school=school,
            user=request.user,
            action="TIMETABLE_SLOT_LOCK_TOGGLED",
            resource_type="TIMETABLE_SLOT",
            resource_id=str(slot.id),
            details={'is_locked': slot.is_locked, 'subject': slot.subject.name, 'section': slot.section.name},
            ip_address=AuditService.get_client_ip(request)
        )

        return JsonResponse({'success': True, 'is_locked': slot.is_locked})
    except TimetableSlot.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Slot not found'}, status=404)


@login_required
def auto_generate_timetable_view(request):
    """
    Executes automatic constraint-satisfaction timetable scheduling.
    """
    if request.method != "POST" or not check_admin_access(request.user):
        messages.error(request, "Unauthorized request.")
        return redirect('timetable:manage')

    school = get_school(request)
    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()

    scope = request.POST.get('scope', 'SELECTED')  # 'SELECTED' or 'ALL'
    section_id = request.POST.get('section_id')
    grade_id = request.POST.get('grade_id')
    shift = request.POST.get('shift', 'FULL_DAY')
    clear_unlocked = request.POST.get('clear_unlocked') == 'on' or request.POST.get('clear_unlocked') == 'true'
    prioritize_core = request.POST.get('prioritize_core_morning') == 'on' or request.POST.get('prioritize_core_morning') == 'true'

    section_ids = None
    if scope == 'SELECTED' and section_id:
        section_ids = [int(section_id)]
    elif scope == 'GRADE' and grade_id:
        section_ids = list(Section.objects.filter(school=school, grade_id=grade_id).values_list('id', flat=True))

    try:
        result = TimetableGeneratorService.generate_timetable(
            school=school,
            academic_year=current_ay,
            section_ids=section_ids,
            shift=shift,
            clear_unlocked=clear_unlocked,
            prioritize_core_morning=prioritize_core,
            user=request.user,
            ip_address=AuditService.get_client_ip(request)
        )

        if result.get('success'):
            messages.success(
                request,
                f"Automatic generation completed successfully! Created {result['slots_created']} slots "
                f"across {result['sections_scheduled']} sections in {result['elapsed_seconds']}s (100% fulfillment)."
            )
        else:
            unplaced = len(result.get('unplaced_items', []))
            messages.warning(
                request,
                f"Generation finished with {result.get('slots_created', 0)} slots created ({result.get('success_rate', 0)}%). "
                f"{unplaced} subject slot(s) could not be placed due to period limit constraints."
            )
    except Exception as e:
        messages.error(request, f"Error generating timetable: {e}")

    redirect_url = 'timetable:manage'
    if section_id:
        redirect_url += f'?section_id={section_id}'
    return redirect(redirect_url)


@login_required
def export_timetable_view(request):
    """
    Exports timetable to Printable HTML / PDF view or CSV file.
    """
    school = get_school(request)
    fmt = request.GET.get('format', 'print')  # 'print' or 'csv'
    section_id = request.GET.get('section_id')
    teacher_id = request.GET.get('teacher_id')

    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
    periods = PeriodSlot.objects.filter(school=school).order_by('start_time')
    days = [
        {'value': DayOfWeek.MONDAY.value, 'label': DayOfWeek.MONDAY.label},
        {'value': DayOfWeek.TUESDAY.value, 'label': DayOfWeek.TUESDAY.label},
        {'value': DayOfWeek.WEDNESDAY.value, 'label': DayOfWeek.WEDNESDAY.label},
        {'value': DayOfWeek.THURSDAY.value, 'label': DayOfWeek.THURSDAY.label},
        {'value': DayOfWeek.FRIDAY.value, 'label': DayOfWeek.FRIDAY.label},
    ]

    selected_section = None
    selected_teacher = None
    timetable = {}

    if section_id:
        selected_section = get_object_or_404(Section, id=section_id, school=school)
        slots = TimetableSlot.objects.filter(school=school, section=selected_section).select_related('subject', 'teacher__user', 'period_slot')
        for s in slots:
            timetable[f"{s.day_of_week}_{s.period_slot_id}"] = s
    elif teacher_id:
        selected_teacher = get_object_or_404(TeacherProfile, id=teacher_id, school=school)
        slots = TimetableSlot.objects.filter(school=school, teacher=selected_teacher).select_related('subject', 'section__grade', 'period_slot')
        for s in slots:
            timetable[f"{s.day_of_week}_{s.period_slot_id}"] = s

    if fmt == 'csv':
        response = HttpResponse(content_type='text/csv')
        title = selected_section.name if selected_section else (selected_teacher.user.get_full_name() if selected_teacher else "School")
        response['Content-Disposition'] = f'attachment; filename="timetable_{title}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Period', 'Time'] + [d['label'] for d in days])

        for period in periods:
            row = [period.name, f"{period.start_time.strftime('%H:%M')} - {period.end_time.strftime('%H:%M')}"]
            for d in days:
                key = f"{d['value']}_{period.id}"
                slot = timetable.get(key)
                if slot:
                    cell_val = f"{slot.subject.name} ({slot.teacher.user.get_full_name() if slot.teacher else 'No Teacher'})"
                else:
                    cell_val = "—"
                row.append(cell_val)
            writer.writerow(row)
        return response

    # Printable HTML view
    grid_rows = []
    for period in periods:
        row_cells = []
        for d in days:
            slot = timetable.get(f"{d['value']}_{period.id}")
            row_cells.append({
                'day': d['value'],
                'period': period,
                'slot': slot
            })
        grid_rows.append({
            'period': period,
            'cells': row_cells
        })

    return render(request, 'timetable/print_view.html', {
        'school': school,
        'current_ay': current_ay,
        'selected_section': selected_section,
        'selected_teacher': selected_teacher,
        'periods': periods,
        'days': days,
        'timetable': timetable,
        'grid_rows': grid_rows,
    })
