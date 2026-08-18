from django.core.exceptions import ValidationError
from apps.academics.models import TimetableSlot


class TimetableConflictChecker:
    @staticmethod
    def check_conflicts(school, section, teacher, room, day_of_week, period_slot, exclude_slot_id=None):
        """
        Validates zero teacher double-booking, room double-booking, or section double-booking.
        """
        qs = TimetableSlot.objects.filter(school=school, day_of_week=day_of_week, period_slot=period_slot)
        if exclude_slot_id:
            qs = qs.exclude(id=exclude_slot_id)

        # 1. Section conflict
        if qs.filter(section=section).exists():
            raise ValidationError(f"Section '{section.name}' is already assigned a subject during {period_slot.name} on {day_of_week}.")

        # 2. Teacher conflict
        if teacher and qs.filter(teacher=teacher).exists():
            raise ValidationError(f"Teacher '{teacher.username}' is already teaching another class during {period_slot.name} on {day_of_week}.")

        # 3. Room conflict
        if room and qs.filter(room=room).exists():
            raise ValidationError(f"Room '{room}' is already occupied during {period_slot.name} on {day_of_week}.")

        return True
