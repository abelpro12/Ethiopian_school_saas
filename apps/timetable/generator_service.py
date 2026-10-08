import logging
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from django.db import transaction
from django.db.models import Q

from apps.academics.models import (
    TimetableSlot, PeriodSlot, Section, Subject, DayOfWeek, AcademicYear
)
from apps.teachers.models import TeacherAssignment, TeacherProfile
from apps.audit.services import AuditService

logger = logging.getLogger(__name__)


class TimetableGeneratorService:
    """
    Intelligent constraint-satisfaction engine for automatic timetable generation.
    Enforces:
    1. Zero teacher double-booking across sections.
    2. Zero section double-booking.
    3. Zero room double-booking.
    4. Exact subject weekly period quotas (Subject.weekly_periods).
    5. Core subjects (Math, English, Science) morning slot prioritization.
    6. Fair daily distribution (max 1 or 2 periods of same subject per day).
    7. Teacher daily and weekly maximum workload limits.
    8. Full preservation of locked/pinned slots.
    """

    DAYS_ORDER = [
        DayOfWeek.MONDAY.value,
        DayOfWeek.TUESDAY.value,
        DayOfWeek.WEDNESDAY.value,
        DayOfWeek.THURSDAY.value,
        DayOfWeek.FRIDAY.value
    ]

    @classmethod
    def generate_timetable(
        cls,
        school,
        academic_year: AcademicYear,
        section_ids: Optional[List[int]] = None,
        shift: str = 'FULL_DAY',
        clear_unlocked: bool = True,
        prioritize_core_morning: bool = True,
        max_daily_per_subject: int = 2,
        user=None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes automatic timetable scheduling for target sections.
        """
        start_time = time.time()

        # 1. Resolve target sections
        sections_qs = Section.objects.filter(school=school, is_active=True).select_related('grade', 'stream')
        if section_ids:
            sections_qs = sections_qs.filter(id__in=section_ids)

        sections = list(sections_qs.order_by('grade__level', 'name'))
        if not sections:
            return {
                'success': False,
                'error': "No active sections found to generate timetable for.",
                'slots_created': 0,
                'unplaced_items': []
            }

        # 2. Resolve available period slots
        periods_qs = PeriodSlot.objects.filter(school=school)
        if shift:
            periods_qs = periods_qs.filter(Q(shift=shift) | Q(shift='FULL_DAY'))
        periods = list(periods_qs.order_by('start_time'))

        if not periods:
            return {
                'success': False,
                'error': f"No period slots configured for shift '{shift}'. Please add daily periods first.",
                'slots_created': 0,
                'unplaced_items': []
            }

        total_grid_capacity = len(cls.DAYS_ORDER) * len(periods)

        # 3. Handle existing locked slots
        with transaction.atomic():
            if clear_unlocked:
                TimetableSlot.objects.filter(
                    school=school,
                    section__in=sections,
                    is_locked=False
                ).delete()

            # Track busy states across the whole school
            busy_teachers: Set[Tuple[int, str, int]] = set()  # (teacher_id, day, period_id)
            busy_sections: Set[Tuple[int, str, int]] = set()  # (section_id, day, period_id)
            busy_rooms: Set[Tuple[str, str, int]] = set()      # (room, day, period_id)

            teacher_day_counts: Dict[Tuple[int, str], int] = {}
            teacher_week_counts: Dict[int, int] = {}
            section_day_subj_counts: Dict[Tuple[int, str, int], int] = {}

            # Prepopulate with existing preserved slots in the school
            existing_slots = TimetableSlot.objects.filter(school=school).select_related(
                'teacher', 'section', 'period_slot', 'subject'
            )

            locked_retained_count = 0
            for slot in existing_slots:
                day = slot.day_of_week
                p_id = slot.period_slot_id

                if slot.teacher_id:
                    busy_teachers.add((slot.teacher_id, day, p_id))
                    teacher_day_counts[(slot.teacher_id, day)] = teacher_day_counts.get((slot.teacher_id, day), 0) + 1
                    teacher_week_counts[slot.teacher_id] = teacher_week_counts.get(slot.teacher_id, 0) + 1

                if slot.section_id:
                    busy_sections.add((slot.section_id, day, p_id))
                    if slot.subject_id:
                        key = (slot.section_id, day, slot.subject_id)
                        section_day_subj_counts[key] = section_day_subj_counts.get(key, 0) + 1

                if slot.room:
                    busy_rooms.add((slot.room, day, p_id))

                if slot.section in sections and slot.is_locked:
                    locked_retained_count += 1

            # 4. Prepare teacher assignment requirements
            slots_to_create = []
            unplaced_items = []
            total_required_slots = 0

            # Define slot candidates
            # Earlier periods (index 0, 1, 2) vs later periods
            all_slot_coords = []
            for day in cls.DAYS_ORDER:
                for idx, period in enumerate(periods):
                    all_slot_coords.append((day, period, idx))

            # Teacher limits lookup cache
            teacher_cache: Dict[int, TeacherProfile] = {
                t.id: t for t in TeacherProfile.objects.filter(school=school)
            }

            for section in sections:
                assignments = list(TeacherAssignment.objects.filter(
                    school=school,
                    section=section,
                    academic_year=academic_year
                ).select_related('subject', 'teacher'))

                if not assignments:
                    unplaced_items.append({
                        'section': section.name,
                        'grade': section.grade.name,
                        'subject': 'N/A',
                        'teacher': 'N/A',
                        'reason': 'No teacher assignments configured for section in this academic year.'
                    })
                    continue

                # Sort assignments: Core subjects first, then subjects with higher weekly periods
                assignments.sort(
                    key=lambda a: (
                        not getattr(a.subject, 'is_core', False),
                        -getattr(a.subject, 'weekly_periods', 4)
                    )
                )

                # Count already existing locked slots for this section per subject
                existing_section_slots = existing_slots.filter(section=section)
                subject_locked_counts = {}
                for s in existing_section_slots:
                    subject_locked_counts[s.subject_id] = subject_locked_counts.get(s.subject_id, 0) + 1

                for assignment in assignments:
                    subject = assignment.subject
                    teacher = assignment.teacher
                    req_periods = getattr(subject, 'weekly_periods', 4) or 4
                    already_locked = subject_locked_counts.get(subject.id, 0)
                    needed_periods = max(0, req_periods - already_locked)

                    total_required_slots += needed_periods
                    is_core = getattr(subject, 'is_core', False)
                    teacher_profile = teacher_cache.get(teacher.id) if teacher else None
                    max_teacher_weekly = teacher_profile.max_weekly_periods if teacher_profile else 30
                    max_teacher_daily = teacher_profile.max_daily_periods if teacher_profile else 6

                    # Find slots for this subject
                    placed_for_subject = 0
                    for _ in range(needed_periods):
                        placed = False

                        # Sort candidate coordinates:
                        # For core subjects: prioritize earlier periods (idx < len(periods) // 2)
                        # Spread across days: sort days by least subject count currently on that day
                        candidate_slots = list(all_slot_coords)
                        if is_core and prioritize_core_morning:
                            candidate_slots.sort(
                                key=lambda item: (
                                    section_day_subj_counts.get((section.id, item[0], subject.id), 0),
                                    item[2]  # period index ascending (morning first)
                                )
                            )
                        else:
                            candidate_slots.sort(
                                key=lambda item: (
                                    section_day_subj_counts.get((section.id, item[0], subject.id), 0),
                                    -item[2] if not is_core else item[2]
                                )
                            )

                        for day, period, p_idx in candidate_slots:
                            # 1. Section conflict
                            if (section.id, day, period.id) in busy_sections:
                                continue

                            # 2. Teacher conflict
                            if teacher and (teacher.id, day, period.id) in busy_teachers:
                                continue

                            # 3. Subject daily density
                            current_subj_day = section_day_subj_counts.get((section.id, day, subject.id), 0)
                            if current_subj_day >= max_daily_per_subject:
                                continue

                            # 4. Teacher daily workload
                            if teacher:
                                t_day_count = teacher_day_counts.get((teacher.id, day), 0)
                                if t_day_count >= max_teacher_daily:
                                    continue

                                # 5. Teacher weekly workload
                                t_week_count = teacher_week_counts.get(teacher.id, 0)
                                if t_week_count >= max_teacher_weekly:
                                    continue

                            # Room determination (default section room if present)
                            room = getattr(section, 'room_number', '') or ''
                            if room and (room, day, period.id) in busy_rooms:
                                continue

                            # Placed successfully!
                            busy_sections.add((section.id, day, period.id))
                            if teacher:
                                busy_teachers.add((teacher.id, day, period.id))
                                teacher_day_counts[(teacher.id, day)] = teacher_day_counts.get((teacher.id, day), 0) + 1
                                teacher_week_counts[teacher.id] = teacher_week_counts.get(teacher.id, 0) + 1

                            section_day_subj_counts[(section.id, day, subject.id)] = current_subj_day + 1
                            if room:
                                busy_rooms.add((room, day, period.id))

                            slots_to_create.append(TimetableSlot(
                                school=school,
                                academic_year=academic_year,
                                section=section,
                                subject=subject,
                                teacher=teacher,
                                day_of_week=day,
                                period_slot=period,
                                room=room,
                                is_locked=False
                            ))

                            placed = True
                            placed_for_subject += 1
                            break

                        if not placed:
                            reason = (
                                f"Could not schedule period {placed_for_subject + 1}/{needed_periods}. "
                                f"No conflict-free slot found (Teacher {teacher.user.get_full_name() if teacher else 'N/A'} "
                                f"or Section {section.name} period limits reached)."
                            )
                            unplaced_items.append({
                                'section': section.name,
                                'grade': section.grade.name,
                                'subject': subject.name,
                                'teacher': teacher.user.get_full_name() if teacher else 'N/A',
                                'reason': reason
                            })

            # Bulk create all scheduled slots
            if slots_to_create:
                TimetableSlot.objects.bulk_create(slots_to_create)

        elapsed = round(time.time() - start_time, 2)
        total_created = len(slots_to_create)
        success_rate = round(
            (total_created / total_required_slots * 100), 1
        ) if total_required_slots > 0 else 100.0

        AuditService.log_action(
            school=school,
            user=user,
            action="TIMETABLE_AUTO_GENERATED",
            resource_type="TIMETABLE",
            details={
                'academic_year': str(academic_year),
                'sections_count': len(sections),
                'slots_created': total_created,
                'locked_retained': locked_retained_count,
                'total_required': total_required_slots,
                'success_rate': success_rate,
                'unplaced_count': len(unplaced_items),
                'elapsed_seconds': elapsed
            },
            ip_address=ip_address
        )

        return {
            'success': len(unplaced_items) == 0,
            'slots_created': total_created,
            'slots_locked_retained': locked_retained_count,
            'total_required': total_required_slots,
            'success_rate': success_rate,
            'fulfillment_rate': success_rate,
            'sections_scheduled': len(sections),
            'unplaced_items': unplaced_items,
            'elapsed_seconds': elapsed
        }
