from django.db import models

class CalendarChoice(models.TextChoices):
    ETHIOPIAN = 'ETHIOPIAN', 'Ethiopian Calendar'
    GREGORIAN = 'GREGORIAN', 'Gregorian Calendar'

class ShiftChoice(models.TextChoices):
    MORNING = 'MORNING', 'Morning'
    AFTERNOON = 'AFTERNOON', 'Afternoon'
    FULL_DAY = 'FULL_DAY', 'Full Day'
