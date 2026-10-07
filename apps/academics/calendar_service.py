import datetime
from django.utils import timezone
from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    SchoolEvent,
    EventCategory,
    EventType,
    EventStatus,
    TargetAudience,
)
from apps.academics.ethiopian_date import ethiopian_to_gregorian, gregorian_to_ethiopian, format_ethiopian_date
from apps.audit.services import AuditService


class AcademicCalendarService:
    """
    Automated generation and lifecycle management for the school academic calendar.
    Generates academic milestones, registration periods, examination windows,
    parent-teacher conferences, breaks, and Ethiopian national & religious holidays.
    """

    @classmethod
    def generate_events_for_academic_year(cls, academic_year: AcademicYear, user=None, overwrite=False) -> dict:
        school = academic_year.school
        ey = academic_year.ethiopian_year or 2017
        ay_start = academic_year.gregorian_start_date
        ay_end = academic_year.gregorian_end_date

        if not ay_start or not ay_end:
            return {"success": False, "error": "Academic Year must have valid start and end dates."}

        created_count = 0
        skipped_count = 0
        preserved_overrides = 0

        # If overwrite requested, remove previously automated events that were NOT manually overridden
        if overwrite:
            overrides_count = SchoolEvent.objects.filter(
                school=school,
                academic_year=academic_year,
                is_automated=True,
                is_override=True
            ).count()
            preserved_overrides = overrides_count

            SchoolEvent.objects.filter(
                school=school,
                academic_year=academic_year,
                is_automated=True,
                is_override=False
            ).delete()

        candidates = []

        # -------------------------------------------------------------
        # 1. ACADEMIC YEAR MILESTONES
        # -------------------------------------------------------------
        candidates.append({
            'title': f"{academic_year.name} — Academic Year Begins",
            'event_category': EventCategory.ACADEMIC,
            'event_type': EventType.SCHOOL_EVENT,
            'target_audience': TargetAudience.ALL,
            'start_date': ay_start,
            'end_date': ay_start,
            'start_time': datetime.time(8, 0),
            'end_time': datetime.time(16, 30),
            'location': "School Campus",
            'description': f"Official commencement of the {academic_year.name} academic school year."
        })

        candidates.append({
            'title': f"{academic_year.name} — Academic Year Closing & Awards Ceremony",
            'event_category': EventCategory.CEREMONY,
            'event_type': EventType.YEAR_CLOSING,
            'target_audience': TargetAudience.ALL,
            'start_date': ay_end,
            'end_date': ay_end,
            'start_time': datetime.time(9, 0),
            'end_time': datetime.time(15, 0),
            'location': "Main Auditorium / Assembly Ground",
            'description': "Annual closing ceremony, student awards, report card distribution, and graduation."
        })

        # -------------------------------------------------------------
        # 2. ADMISSION & REGISTRATION WINDOWS
        # -------------------------------------------------------------
        early_reg_start = ay_start - datetime.timedelta(days=14)
        candidates.append({
            'title': "Student Registration & Admission Window",
            'event_category': EventCategory.REGISTRATION,
            'event_type': EventType.REGISTRATION_PERIOD,
            'target_audience': TargetAudience.PARENTS,
            'start_date': early_reg_start,
            'end_date': ay_start - datetime.timedelta(days=1),
            'start_time': datetime.time(8, 30),
            'end_time': datetime.time(17, 0),
            'location': "Registrar Office",
            'description': "Official registration, document verification, and tuition fee settlement period for new and returning students."
        })

        candidates.append({
            'title': "Late Registration & Course Add/Drop Period",
            'event_category': EventCategory.REGISTRATION,
            'event_type': EventType.REGISTRATION_PERIOD,
            'target_audience': TargetAudience.ALL,
            'start_date': ay_start,
            'end_date': ay_start + datetime.timedelta(days=7),
            'start_time': datetime.time(8, 30),
            'end_time': datetime.time(16, 0),
            'location': "Registrar Office",
            'description': "Late registration window with applicable late fees, subject adjustments, and section transfers."
        })

        # -------------------------------------------------------------
        # 3. TEACHER ORIENTATION & TRAINING
        # -------------------------------------------------------------
        teacher_train_start = ay_start - datetime.timedelta(days=3)
        candidates.append({
            'title': "Faculty Orientation & Curriculum Planning Workshop",
            'event_category': EventCategory.TRAINING,
            'event_type': EventType.TEACHER_MEETING,
            'target_audience': TargetAudience.TEACHERS,
            'start_date': teacher_train_start,
            'end_date': ay_start - datetime.timedelta(days=1),
            'start_time': datetime.time(9, 0),
            'end_time': datetime.time(16, 0),
            'location': "Staff Development Hall",
            'description': "Comprehensive teacher training, pedagogical review, lesson planning, and digital portal onboarding."
        })

        # -------------------------------------------------------------
        # 4. PERIOD / SEMESTER MILESTONES
        # -------------------------------------------------------------
        periods = list(academic_year.academic_periods.all().order_by('start_date'))
        for p_idx, period in enumerate(periods, start=1):
            p_start = period.start_date
            p_end = period.end_date
            p_days = (p_end - p_start).days

            # Term Start
            candidates.append({
                'title': f"{period.name} — Term Commences & Orientation",
                'event_category': EventCategory.ACADEMIC,
                'event_type': EventType.SCHOOL_EVENT,
                'target_audience': TargetAudience.ALL,
                'start_date': p_start,
                'end_date': p_start,
                'academic_period': period,
                'description': f"First day of {period.name}. Class distribution and orientation."
            })

            # Classes Begin
            if p_days > 2:
                candidates.append({
                    'title': f"{period.name} — Regular Classroom Instruction Begins",
                    'event_category': EventCategory.ACADEMIC,
                    'event_type': EventType.SCHOOL_EVENT,
                    'target_audience': TargetAudience.ALL,
                    'start_date': p_start + datetime.timedelta(days=1),
                    'end_date': p_start + datetime.timedelta(days=1),
                    'academic_period': period,
                    'description': f"Regular timetable teaching and subject syllabus implementation commences."
                })

            # Midterm Exams
            if p_days >= 30:
                mid_point = p_start + datetime.timedelta(days=p_days // 2)
                mid_exam_start = mid_point - datetime.timedelta(days=2)
                mid_exam_end = mid_point + datetime.timedelta(days=2)
                candidates.append({
                    'title': f"{period.name} — Midterm Examination Window",
                    'event_category': EventCategory.EXAMINATION,
                    'event_type': EventType.EXAM_PERIOD,
                    'target_audience': TargetAudience.ALL,
                    'start_date': mid_exam_start,
                    'end_date': mid_exam_end,
                    'start_time': datetime.time(8, 30),
                    'end_time': datetime.time(13, 0),
                    'academic_period': period,
                    'location': "Assigned Examination Rooms",
                    'description': f"Midterm assessments across all grades and subjects for {period.name}."
                })

                # Midterm PTA / Conference
                pta_date = mid_exam_end + datetime.timedelta(days=3)
                if pta_date < p_end:
                    candidates.append({
                        'title': f"{period.name} — Parent-Teacher Midterm Progress Meeting",
                        'event_category': EventCategory.MEETING,
                        'event_type': EventType.PARENT_MEETING,
                        'target_audience': TargetAudience.PARENTS,
                        'start_date': pta_date,
                        'end_date': pta_date,
                        'start_time': datetime.time(9, 0),
                        'end_time': datetime.time(13, 0),
                        'academic_period': period,
                        'location': "School Campus & Classrooms",
                        'description': "Consultation meetings between parents and homeroom/subject teachers regarding student midterm progress."
                    })

            # Final Exams
            if p_days >= 20:
                fin_start = p_end - datetime.timedelta(days=6)
                fin_end = p_end - datetime.timedelta(days=2)
                if fin_start > p_start:
                    candidates.append({
                        'title': f"{period.name} — Final Examination Window",
                        'event_category': EventCategory.EXAMINATION,
                        'event_type': EventType.EXAM_PERIOD,
                        'target_audience': TargetAudience.ALL,
                        'start_date': fin_start,
                        'end_date': fin_end,
                        'start_time': datetime.time(8, 30),
                        'end_time': datetime.time(13, 0),
                        'academic_period': period,
                        'location': "Assigned Examination Rooms",
                        'description': f"End-of-term comprehensive final examinations for {period.name}."
                    })

            # Term Result Publication
            candidates.append({
                'title': f"{period.name} — Report Card & Results Release",
                'event_category': EventCategory.ACADEMIC,
                'event_type': EventType.RESULT_PUBLICATION,
                'target_audience': TargetAudience.ALL,
                'start_date': p_end,
                'end_date': p_end,
                'academic_period': period,
                'description': f"Official release of {period.name} report cards, rank distributions, and transcript updates."
            })

            # Inter-Semester Break (if next period exists)
            if p_idx < len(periods):
                next_period = periods[p_idx]
                if (next_period.start_date - p_end).days > 1:
                    break_start = p_end + datetime.timedelta(days=1)
                    break_end = next_period.start_date - datetime.timedelta(days=1)
                    candidates.append({
                        'title': f"Inter-Semester Vacation & Break",
                        'event_category': EventCategory.BREAK,
                        'event_type': EventType.SCHOOL_EVENT,
                        'target_audience': TargetAudience.ALL,
                        'start_date': break_start,
                        'end_date': break_end,
                        'description': "School break for students and staff between academic terms."
                    })

        # Year-End Vacation / Summer Break
        summer_start = ay_end + datetime.timedelta(days=1)
        summer_end = summer_start + datetime.timedelta(days=45)
        candidates.append({
            'title': "Annual Summer Vacation & Recess",
            'event_category': EventCategory.BREAK,
            'event_type': EventType.SCHOOL_EVENT,
            'target_audience': TargetAudience.ALL,
            'start_date': summer_start,
            'end_date': summer_end,
            'description': "Official summer vacation and school recess before the upcoming academic year."
        })

        # -------------------------------------------------------------
        # 5. ETHIOPIAN NATIONAL & RELIGIOUS HOLIDAYS
        # -------------------------------------------------------------
        ethiopian_holidays = [
            ("Enkutatash (Ethiopian New Year 🇪🇹)", 1, 1, 1, "Celebration of the Ethiopian New Year."),
            ("Meskel (Finding of the True Cross ✝️)", 1, 17, 1, "Public holiday celebrating the discovery of the True Cross."),
            ("Genna (Ethiopian Christmas 🎄)", 4, 29, 1, "Celebration of the Nativity according to the Ethiopian Orthodox tradition."),
            ("Timket (Ethiopian Epiphany 🕊️)", 5, 11, 2, "Commemoration of the baptism of Jesus in the Jordan River."),
            ("Victory of Adwa Day 🇪🇹", 6, 23, 1, "Commemoration of the historic victory of Ethiopia at the Battle of Adwa (1896)."),
            ("Ethiopian Good Friday (Siklet ✝️)", 8, 22, 1, "National holiday observing Good Friday according to the Eastern Christian calendar."),
            ("Ethiopian Easter (Fasika 🕊️)", 8, 24, 1, "Celebration of the Resurrection of Jesus Christ (Fasika)."),
            ("Patriots' Victory Day (Miazia 27 🇪🇹)", 8, 27, 1, "Commemoration of the liberation of Ethiopia in 1941."),
            ("Downfall of the Derg (Ginbot 20 🇪🇹)", 9, 20, 1, "National holiday commemorating the end of the Derg regime in 1991."),
        ]

        for h_title, eth_m, eth_d, duration_days, h_desc in ethiopian_holidays:
            h_greg = ethiopian_to_gregorian(ey, eth_m, eth_d)
            if h_greg:
                h_greg_end = h_greg + datetime.timedelta(days=duration_days - 1)
                # Include holiday if it falls reasonably within the academic year window
                if (ay_start - datetime.timedelta(days=15)) <= h_greg <= (ay_end + datetime.timedelta(days=15)):
                    candidates.append({
                        'title': h_title,
                        'event_category': EventCategory.HOLIDAY,
                        'event_type': EventType.HOLIDAY,
                        'target_audience': TargetAudience.ALL,
                        'start_date': h_greg,
                        'end_date': h_greg_end,
                        'description': f"{h_desc} (No regular classes scheduled)."
                    })

        # Islamic Holidays for Ethiopian Academic Calendar
        # (Approximate Gregorian dates calculated for the typical Ethiopian academic year cycle)
        islamic_holidays = [
            ("Mawlid (The Prophet's Birthday 🌙)", datetime.date(ay_start.year, 9, 16) if ay_start else None, "Commemoration of the birth of the Prophet Muhammad (PBUH)."),
            ("Eid al-Fitr (End of Ramadan 🌙)", datetime.date(ay_start.year + 1, 3, 31) if ay_start else None, "Islamic holiday marking the conclusion of Ramadan fasting."),
            ("Eid al-Adha (Arafa 🌙)", datetime.date(ay_start.year + 1, 6, 7) if ay_start else None, "Feast of the Sacrifice, celebrating the devotion of Ibrahim."),
        ]

        for isl_title, isl_date, isl_desc in islamic_holidays:
            if isl_date and (ay_start <= isl_date <= ay_end):
                candidates.append({
                    'title': isl_title,
                    'event_category': EventCategory.HOLIDAY,
                    'event_type': EventType.HOLIDAY,
                    'target_audience': TargetAudience.ALL,
                    'start_date': isl_date,
                    'end_date': isl_date,
                    'description': f"{isl_desc} (Official public holiday)."
                })

        # -------------------------------------------------------------
        # 6. PERSIST CANDIDATES INTO DATABASE
        # -------------------------------------------------------------
        for cand in candidates:
            # Check if this automated event already exists
            existing = SchoolEvent.objects.filter(
                school=school,
                academic_year=academic_year,
                title=cand['title'],
                start_date=cand['start_date']
            ).first()

            if existing:
                if existing.is_override:
                    preserved_overrides += 1
                skipped_count += 1
                continue

            SchoolEvent.objects.create(
                school=school,
                academic_year=academic_year,
                academic_period=cand.get('academic_period'),
                title=cand['title'],
                event_category=cand.get('event_category', EventCategory.ACADEMIC),
                event_type=cand.get('event_type', EventType.SCHOOL_EVENT),
                target_audience=cand.get('target_audience', TargetAudience.ALL),
                status=EventStatus.SCHEDULED,
                start_date=cand['start_date'],
                end_date=cand.get('end_date'),
                start_time=cand.get('start_time'),
                end_time=cand.get('end_time'),
                location=cand.get('location'),
                description=cand.get('description'),
                is_automated=True,
                is_override=False,
                is_active=True,
                created_by=user
            )
            created_count += 1

        # Audit log
        AuditService.log_action(
            school=school,
            user=user,
            action="ACADEMIC_CALENDAR_GENERATED",
            object_type="AcademicYear",
            object_id=academic_year.id,
            details={
                "created_count": created_count,
                "skipped_count": skipped_count,
                "preserved_overrides": preserved_overrides,
                "total_candidates": len(candidates),
                "academic_year": academic_year.name,
            }
        )

        return {
            "success": True,
            "created": created_count,
            "skipped": skipped_count,
            "preserved_overrides": preserved_overrides,
            "total": len(candidates)
        }
