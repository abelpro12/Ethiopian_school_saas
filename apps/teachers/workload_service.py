import logging
from typing import Dict, List, Any, Optional
from django.db.models import Count, Q
from apps.teachers.models import TeacherProfile, TeacherAssignment, Department
from apps.academics.models import TimetableSlot, DayOfWeek, AcademicYear, Section, Subject
from apps.audit.services import AuditService

logger = logging.getLogger(__name__)


class TeacherWorkloadService:
    """
    Central service for calculating, visualizing, and enforcing teacher workload,
    department structures, and capacity management.
    """

    @classmethod
    def get_teacher_workload_metrics(
        cls,
        school,
        academic_year: Optional[AcademicYear] = None,
        department_id: Optional[int] = None,
        status_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates detailed workload metrics for all active teachers in a school.
        """
        teachers_qs = TeacherProfile.objects.filter(school=school).select_related(
            'user', 'department_obj'
        ).prefetch_related(
            'assignments__subject',
            'assignments__section__grade',
            'user__managed_sections__grade'
        ).order_by('user__first_name', 'user__last_name')

        if department_id:
            teachers_qs = teachers_qs.filter(department_obj_id=department_id)

        # Preload timetable slots for the school
        slots_qs = TimetableSlot.objects.filter(school=school)
        if academic_year:
            slots_qs = slots_qs.filter(
                Q(academic_year=academic_year) | Q(academic_year__isnull=True)
            )

        # Map teacher slots
        teacher_slots_map: Dict[int, List[TimetableSlot]] = {}
        for slot in slots_qs.select_related('subject', 'section', 'period_slot'):
            if slot.teacher_id:
                teacher_slots_map.setdefault(slot.teacher_id, []).append(slot)

        teacher_metrics = []
        total_school_periods = 0
        overloaded_count = 0
        underallocated_count = 0
        optimal_count = 0

        days_order = [
            DayOfWeek.MONDAY.value,
            DayOfWeek.TUESDAY.value,
            DayOfWeek.WEDNESDAY.value,
            DayOfWeek.THURSDAY.value,
            DayOfWeek.FRIDAY.value
        ]

        for teacher in teachers_qs:
            assigned_slots = teacher_slots_map.get(teacher.id, [])
            total_periods = len(assigned_slots)

            # Fallback to assignment estimates if no timetable slots are generated yet
            if total_periods == 0:
                t_assignments = teacher.assignments.all()
                if academic_year:
                    t_assignments = t_assignments.filter(academic_year=academic_year)
                # Count estimated periods based on subject weekly periods
                est_periods = sum(
                    getattr(a.subject, 'weekly_periods', 4) for a in t_assignments
                )
                total_periods = est_periods

            total_school_periods += total_periods
            max_limit = teacher.max_weekly_periods or 25
            pct = round((total_periods / max_limit) * 100, 1) if max_limit > 0 else 0.0

            # Daily periods breakdown
            daily_breakdown = {d: 0 for d in days_order}
            daily_overload = False
            for slot in assigned_slots:
                if slot.day_of_week in daily_breakdown:
                    daily_breakdown[slot.day_of_week] += 1
                    if daily_breakdown[slot.day_of_week] > teacher.max_daily_periods:
                        daily_overload = True

            # Workload status evaluation
            if pct > 100.0 or daily_overload:
                status = 'OVER'
                overloaded_count += 1
            elif pct < 60.0:
                status = 'UNDER'
                underallocated_count += 1
            else:
                status = 'OPTIMAL'
                optimal_count += 1

            if status_filter and status != status_filter:
                continue

            # Subjects & Sections taught
            assigned_subjects = list(teacher.assignments.values_list('subject__name', flat=True).distinct())
            assigned_sections = list(teacher.assignments.values_list('section__name', flat=True).distinct())
            homeroom_sec = teacher.user.managed_sections.filter(is_active=True).first()

            teacher_metrics.append({
                'teacher': teacher,
                'total_periods': total_periods,
                'max_weekly_periods': max_limit,
                'max_daily_periods': teacher.max_daily_periods,
                'workload_percentage': min(pct, 150.0),
                'status': status,
                'daily_breakdown': daily_breakdown,
                'daily_overload': daily_overload,
                'assigned_subjects': assigned_subjects,
                'assigned_sections': assigned_sections,
                'homeroom_section': homeroom_sec,
                'assignments_count': teacher.assignments.count(),
            })

        avg_load = round(total_school_periods / len(teachers_qs), 1) if teachers_qs.exists() else 0.0

        return {
            'teacher_metrics': teacher_metrics,
            'total_teachers': teachers_qs.count(),
            'total_school_periods': total_school_periods,
            'average_workload': avg_load,
            'overloaded_count': overloaded_count,
            'underallocated_count': underallocated_count,
            'optimal_count': optimal_count,
        }

    @classmethod
    def get_department_summary(cls, school) -> List[Dict[str, Any]]:
        """
        Returns aggregated workload and staffing metrics grouped by Department.
        """
        departments = Department.objects.filter(school=school).select_related(
            'head_of_department__user'
        ).annotate(
            num_teachers=Count('teachers', distinct=True)
        ).order_by('name')

        dept_summary = []
        for dept in departments:
            teachers = dept.teachers.all()
            total_periods = sum(t.total_weekly_periods for t in teachers)
            subjects_count = Subject.objects.filter(school=school, department=dept).count()
            avg_periods = round(total_periods / len(teachers), 1) if teachers.exists() else 0.0

            dept_summary.append({
                'department': dept,
                'head_name': dept.head_of_department.user.get_full_name() if dept.head_of_department else 'Not Appointed',
                'teacher_count': len(teachers),
                'subjects_count': subjects_count,
                'total_periods': total_periods,
                'avg_periods': avg_periods,
            })

        return dept_summary

    @classmethod
    def check_teacher_capacity(
        cls,
        teacher: TeacherProfile,
        additional_periods: int = 1,
        academic_year: Optional[AcademicYear] = None
    ) -> Dict[str, Any]:
        """
        Pre-flight check before assigning a teacher to a new subject/section.
        Returns whether the assignment would cause an overload.
        """
        current_periods = teacher.total_weekly_periods
        projected = current_periods + additional_periods
        max_allowed = teacher.max_weekly_periods or 25

        would_overload = projected > max_allowed
        return {
            'current_periods': current_periods,
            'additional_periods': additional_periods,
            'projected_periods': projected,
            'max_allowed': max_allowed,
            'would_overload': would_overload,
            'utilization_pct': round((projected / max_allowed) * 100, 1) if max_allowed > 0 else 0.0
        }
