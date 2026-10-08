import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from apps.teachers.models import TeacherProfile, Department
from apps.teachers.workload_service import TeacherWorkloadService
from apps.accounts.models import UserRole
from apps.audit.services import AuditService
from apps.tenants.utils import get_school

logger = logging.getLogger(__name__)


def check_management_access(user):
    return user.role in [
        UserRole.SUPER_ADMIN,
        UserRole.SCHOOL_ADMIN,
        UserRole.PRINCIPAL,
        UserRole.REGISTRAR,
        UserRole.HR_MANAGER
    ]


@login_required
def workload_dashboard(request):
    """
    Teacher Workload & Capacity Management Hub.
    Visualizes teacher teaching loads, capacity thresholds, daily distribution,
    and department structures.
    """
    school = get_school(request)
    if not school:
        messages.error(request, "School context required.")
        return redirect('index')

    if not check_management_access(request.user):
        messages.error(request, "Unauthorized access to workload management.")
        return redirect('index')

    current_ay = getattr(request, 'academic_year', None)
    dept_id = request.GET.get('department_id')
    status_filter = request.GET.get('status')

    # Get metrics from service
    workload_data = TeacherWorkloadService.get_teacher_workload_metrics(
        school=school,
        academic_year=current_ay,
        department_id=int(dept_id) if dept_id else None,
        status_filter=status_filter
    )

    department_summaries = TeacherWorkloadService.get_department_summary(school)
    departments = Department.objects.filter(school=school).order_by('name')

    return render(request, 'teachers/workload_dashboard.html', {
        'teacher_metrics': workload_data['teacher_metrics'],
        'total_teachers': workload_data['total_teachers'],
        'total_school_periods': workload_data['total_school_periods'],
        'average_workload': workload_data['average_workload'],
        'overloaded_count': workload_data['overloaded_count'],
        'underallocated_count': workload_data['underallocated_count'],
        'optimal_count': workload_data['optimal_count'],
        'department_summaries': department_summaries,
        'departments': departments,
        'selected_dept': int(dept_id) if dept_id else None,
        'selected_status': status_filter,
    })


@login_required
def update_teacher_capacity(request):
    """
    Updates teacher maximum weekly and daily teaching period limits.
    """
    if request.method != 'POST' or not check_management_access(request.user):
        messages.error(request, "Unauthorized request.")
        return redirect('teachers:workload_dashboard')

    school = get_school(request)
    teacher_id = request.POST.get('teacher_id')
    max_weekly = request.POST.get('max_weekly_periods')
    max_daily = request.POST.get('max_daily_periods')
    dept_id = request.POST.get('department_id')

    try:
        teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
        if max_weekly:
            teacher.max_weekly_periods = max(1, int(max_weekly))
        if max_daily:
            teacher.max_daily_periods = max(1, int(max_daily))
        if dept_id:
            teacher.department_obj_id = int(dept_id)
            teacher.department = teacher.department_obj.name
        elif dept_id == "":
            teacher.department_obj = None

        teacher.save()

        AuditService.log_action(
            school=school,
            user=request.user,
            action="TEACHER_CAPACITY_UPDATED",
            resource_type="TEACHER_PROFILE",
            resource_id=str(teacher.id),
            details={
                'teacher': str(teacher),
                'max_weekly_periods': teacher.max_weekly_periods,
                'max_daily_periods': teacher.max_daily_periods,
                'department': teacher.department
            },
            ip_address=AuditService.get_client_ip(request)
        )

        messages.success(request, f"Updated workload capacity limits for {teacher.user.get_full_name()}.")
    except TeacherProfile.DoesNotExist:
        messages.error(request, "Teacher profile not found.")
    except Exception as e:
        messages.error(request, f"Error updating capacity: {e}")

    return redirect('teachers:workload_dashboard')


@login_required
def manage_departments(request):
    """
    Create or edit academic departments and assign Heads of Department (HOD).
    """
    if request.method != 'POST' or not check_management_access(request.user):
        messages.error(request, "Unauthorized request.")
        return redirect('teachers:workload_dashboard')

    school = get_school(request)
    action = request.POST.get('action')

    if action == 'create_department':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        description = request.POST.get('description', '').strip()
        hod_id = request.POST.get('head_of_department_id')

        if not name or not code:
            messages.error(request, "Department name and code are required.")
            return redirect('teachers:workload_dashboard')

        try:
            hod = TeacherProfile.objects.filter(id=hod_id, school=school).first() if hod_id else None
            dept = Department.objects.create(
                school=school,
                name=name,
                code=code,
                description=description,
                head_of_department=hod
            )
            messages.success(request, f"Department '{dept.name}' ({dept.code}) created successfully.")
        except Exception as e:
            messages.error(request, f"Error creating department: {e}")

    elif action == 'edit_department':
        dept_id = request.POST.get('department_id')
        try:
            dept = Department.objects.get(id=dept_id, school=school)
            dept.name = request.POST.get('name', dept.name).strip()
            dept.code = request.POST.get('code', dept.code).strip().upper()
            dept.description = request.POST.get('description', dept.description).strip()
            hod_id = request.POST.get('head_of_department_id')
            dept.head_of_department = TeacherProfile.objects.filter(id=hod_id, school=school).first() if hod_id else None
            dept.save()
            messages.success(request, f"Department '{dept.name}' updated successfully.")
        except Department.DoesNotExist:
            messages.error(request, "Department not found.")
        except Exception as e:
            messages.error(request, f"Error updating department: {e}")

    elif action == 'delete_department':
        dept_id = request.POST.get('department_id')
        try:
            dept = Department.objects.get(id=dept_id, school=school)
            dept_name = dept.name
            dept.delete()
            messages.success(request, f"Department '{dept_name}' removed.")
        except Department.DoesNotExist:
            messages.error(request, "Department not found.")

    return redirect('teachers:workload_dashboard')
