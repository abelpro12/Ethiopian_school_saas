from django.db import migrations


class Migration(migrations.Migration):
    """
    Initial migration for the timetable app.
    The timetable app uses models from apps.academics (TimetableSlot, PeriodSlot)
    and does not define its own models — this migration records the initial state.
    """
    dependencies = [
        ('academics', '0004_section_tutorial_teacher'),
    ]

    operations = []
