from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import ValidationError

from apps.academics.models import PeriodSlot, TimetableSlot, Section, DayOfWeek
from apps.teachers.models import TeacherAssignment
from apps.accounts.models import UserRole
from apps.timetable.conflict_checker import TimetableConflictChecker

def check_admin_access(user):
    return user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]

@login_required
def manage_period_slots(request):
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = getattr(request, 'school', None) or request.user.school

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
                messages.success(request, "Period slot added successfully.")
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
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = getattr(request, 'school', None) or request.user.school
    current_ay = getattr(request, 'academic_year', None)

    sections = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name')
    periods = PeriodSlot.objects.filter(school=school).order_by('start_time')
    days = [
        {'value': DayOfWeek.MONDAY.value, 'label': DayOfWeek.MONDAY.label},
        {'value': DayOfWeek.TUESDAY.value, 'label': DayOfWeek.TUESDAY.label},
        {'value': DayOfWeek.WEDNESDAY.value, 'label': DayOfWeek.WEDNESDAY.label},
        {'value': DayOfWeek.THURSDAY.value, 'label': DayOfWeek.THURSDAY.label},
        {'value': DayOfWeek.FRIDAY.value, 'label': DayOfWeek.FRIDAY.label},
    ]

    selected_section_id = request.GET.get('section_id')
    selected_section = None
    timetable = {}
    assignments = []

    if selected_section_id:
        selected_section = get_object_or_404(Section, id=selected_section_id, school=school)
        slots = TimetableSlot.objects.filter(school=school, section=selected_section).select_related('subject', 'teacher', 'period_slot')
        
        for slot in slots:
            key = f"{slot.day_of_week}_{slot.period_slot.id}"
            timetable[key] = slot
            
        assignments = TeacherAssignment.objects.filter(
            school=school, section=selected_section, academic_year=current_ay
        ).select_related('subject', 'teacher__user')

    return render(request, 'timetable/manage.html', {
        'sections': sections,
        'periods': periods,
        'days': days,
        'selected_section': selected_section,
        'timetable': timetable,
        'assignments': assignments,
    })

@login_required
def assign_slot_htmx(request):
    if request.method != "POST" or not check_admin_access(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = getattr(request, 'school', None) or request.user.school
    section_id = request.POST.get('section_id')
    day = request.POST.get('day')
    period_id = request.POST.get('period_id')
    assignment_id = request.POST.get('assignment_id')
    room = request.POST.get('room', '')

    try:
        section = Section.objects.get(id=section_id, school=school)
        period = PeriodSlot.objects.get(id=period_id, school=school)
        assignment = TeacherAssignment.objects.get(id=assignment_id, school=school)
        
        teacher = assignment.teacher
        subject = assignment.subject

        TimetableConflictChecker.check_conflicts(school, section, teacher, room, day, period)

        slot, created = TimetableSlot.objects.update_or_create(
            school=school,
            section=section,
            day_of_week=day,
            period_slot=period,
            defaults={
                'subject': subject,
                'teacher': teacher,
                'room': room
            }
        )
        
        return render(request, 'timetable/partials/slot_cell.html', {
            'slot': slot,
            'day': day,
            'period': period,
            'section': section
        })

    except ValidationError as e:
        return HttpResponse(f"<div class='p-2 bg-red-100 text-red-800 text-xs rounded border border-red-200 mt-2'>{e.messages[0]}</div>", status=400)
    except Exception as e:
        return HttpResponse(f"<div class='p-2 bg-red-100 text-red-800 text-xs rounded border border-red-200 mt-2'>Error: {str(e)}</div>", status=400)

@login_required
def remove_slot_htmx(request):
    if request.method != "POST" or not check_admin_access(request.user):
        return HttpResponse("Unauthorized", status=403)

    school = getattr(request, 'school', None) or request.user.school
    slot_id = request.POST.get('slot_id')
    
    try:
        slot = TimetableSlot.objects.get(id=slot_id, school=school)
        day = slot.day_of_week
        period = slot.period_slot
        section = slot.section
        slot.delete()
        
        return render(request, 'timetable/partials/slot_cell.html', {
            'slot': None,
            'day': day,
            'period': period,
            'section': section
        })
    except Exception as e:
        return HttpResponse("Error", status=400)
