import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Avg, Count, Q

from apps.academics.models import (
    AcademicYear,
    AcademicPeriod,
    PeriodStatus,
    SemesterArchive,
    SchoolEvent,
    EventCategory,
    EventType,
    EventStatus,
    TargetAudience,
)
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import AcademicPeriodResult
from apps.enrollment.services_period import AcademicPeriodCloseService
from apps.audit.services import AuditService


class AcademicPeriodLifecycleService:
    """
    Enterprise-grade lifecycle engine for Academic Periods (Terms & Semesters).
    Manages active term transitions, locking, administrative reopening with audit trails,
    historical snapshot archiving, supplementary exam schedules, and year rollover.
    """

    @classmethod
    def set_active_semester(cls, period: AcademicPeriod, user=None) -> dict:
        """
        Designates a semester as the currently active operational period for the school.
        Unsets is_current on all other periods.
        """
        school = period.school
        AcademicPeriod.objects.filter(school=school, is_current=True).exclude(id=period.id).update(is_current=False)

        period.is_current = True
        period.save(update_fields=['is_current'])

        # Also ensure the parent AcademicYear is active
        if period.academic_year and not period.academic_year.is_active:
            AcademicYear.objects.filter(school=school, is_active=True).exclude(id=period.academic_year.id).update(is_active=False)
            period.academic_year.is_active = True
            period.academic_year.save(update_fields=['is_active'])

        AuditService.log_action(
            school=school,
            user=user,
            action="PERIOD_ACTIVATED",
            object_type="AcademicPeriod",
            object_id=str(period.id),
            details={
                "period_name": period.name,
                "academic_year": period.academic_year.name if period.academic_year else "",
                "is_current": True
            }
        )

        return {
            "success": True,
            "message": f"'{period.name}' is now set as the active operational semester for {school.name}."
        }

    @classmethod
    def lock_semester(cls, period: AcademicPeriod, user=None, reason="") -> dict:
        """
        Locks a completed semester to strictly prevent mark alterations,
        retroactive attendance edits, or grade tampering.
        """
        school = period.school
        now = timezone.now()

        period.status = PeriodStatus.LOCKED
        period.locked_at = now
        period.locked_by = user
        period.save(update_fields=['status', 'locked_at', 'locked_by'])

        AuditService.log_action(
            school=school,
            user=user,
            action="PERIOD_LOCKED",
            object_type="AcademicPeriod",
            object_id=str(period.id),
            details={
                "period_name": period.name,
                "locked_at": now.isoformat(),
                "reason": reason or "Semester gradebook and records locked by administrator."
            }
        )

        return {
            "success": True,
            "message": f"Semester '{period.name}' has been locked. Mark entries and attendance edits are now frozen."
        }

    @classmethod
    def reopen_semester(cls, period: AcademicPeriod, user=None, reason="") -> dict:
        """
        Administratively reopens a locked/closed semester with mandatory reason and audit logging.
        """
        if not reason or not reason.strip():
            return {
                "success": False,
                "error": "A valid administrative justification reason is required to reopen a locked semester."
            }

        school = period.school
        now = timezone.now()

        period.status = PeriodStatus.OPEN
        period.reopened_at = now
        period.reopened_by = user
        period.reopen_reason = reason.strip()
        period.save(update_fields=['status', 'reopened_at', 'reopened_by', 'reopen_reason'])

        AuditService.log_action(
            school=school,
            user=user,
            action="PERIOD_REOPENED",
            object_type="AcademicPeriod",
            object_id=str(period.id),
            details={
                "period_name": period.name,
                "reopened_at": now.isoformat(),
                "reason": reason.strip(),
                "authorized_by": user.username if user else "Admin"
            }
        )

        return {
            "success": True,
            "message": f"Semester '{period.name}' has been successfully reopened for administrative corrections."
        }

    @classmethod
    def create_semester_archive(cls, period: AcademicPeriod, user=None, notes="") -> SemesterArchive:
        """
        Captures an immutable historical snapshot archive of a semester's results, pass rates,
        averages, top performers, and section distributions.
        """
        school = period.school
        results_qs = AcademicPeriodResult.objects.filter(school=school, period=period)

        total_students = results_qs.count()
        passed_students = results_qs.filter(average_score__gte=50.0).count()
        failed_students = total_students - passed_students

        overall_avg_val = results_qs.aggregate(avg=Avg('average_score'))['avg']
        overall_average = Decimal(str(round(float(overall_avg_val or 0.0), 2)))

        # Snapshot breakdown by grade and section
        enrollments = StudentEnrollment.objects.filter(
            school=school,
            academic_year=period.academic_year,
            status=EnrollmentStatus.ACTIVE
        ).select_related('grade', 'section')

        grade_distribution = {}
        for en in enrollments:
            g_name = en.grade.name if en.grade else "Unassigned"
            grade_distribution[g_name] = grade_distribution.get(g_name, 0) + 1

        top_performers = list(results_qs.order_by('-average_score')[:5].values(
            'enrollment__student__first_name',
            'enrollment__student__last_name',
            'enrollment__student__student_id',
            'average_score',
            'section_rank'
        ))

        def _json_safe(val):
            if isinstance(val, Decimal):
                return float(val)
            if isinstance(val, dict):
                return {k: _json_safe(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [_json_safe(x) for x in val]
            return val

        snapshot_payload = _json_safe({
            "period_name": period.name,
            "period_type": period.period_type,
            "academic_year": period.academic_year.name if period.academic_year else "",
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
            "instructional_days": period.instructional_days,
            "total_students_evaluated": total_students,
            "pass_rate_percentage": round((passed_students / total_students * 100), 2) if total_students > 0 else 0.0,
            "grade_distribution": grade_distribution,
            "top_performers": top_performers,
            "archived_timestamp": timezone.now().isoformat(),
        })

        archive = SemesterArchive.objects.create(
            school=school,
            period=period,
            academic_year=period.academic_year,
            archived_by=user,
            total_students=total_students,
            passed_students=passed_students,
            failed_students=failed_students,
            overall_average=overall_average,
            snapshot_data=snapshot_payload,
            notes=notes or f"Official semester closure archive for {period.name}."
        )

        AuditService.log_action(
            school=school,
            user=user,
            action="SEMESTER_ARCHIVE_CREATED",
            object_type="SemesterArchive",
            object_id=str(archive.id),
            details={
                "period_name": period.name,
                "total_students": total_students,
                "overall_average": float(overall_average)
            }
        )

        return archive

    @classmethod
    def execute_semester_close_workflow(cls, period: AcademicPeriod, user=None, notes="") -> dict:
        """
        Executes end-to-end semester closure:
        1. Executes calculation and publishing of period results and section ranks.
        2. Freezes & locks semester status to CLOSED.
        3. Generates immutable SemesterArchive historical snapshot.
        """
        school = period.school

        # 1. Execute close engine
        success, msg, count = AcademicPeriodCloseService.execute_period_close(
            period=period,
            school=school,
            published_by=user
        )

        if not success:
            return {"success": False, "error": msg}

        # 2. Update status to CLOSED and record lock time
        period.status = PeriodStatus.CLOSED
        period.locked_at = timezone.now()
        period.locked_by = user
        period.is_current = False
        period.save(update_fields=['status', 'locked_at', 'locked_by', 'is_current'])

        # 3. Create historical archive snapshot
        archive = cls.create_semester_archive(period=period, user=user, notes=notes)

        return {
            "success": True,
            "message": f"Semester '{period.name}' has been successfully closed, ranked, and archived ({count} students processed).",
            "archive_id": archive.id,
            "count": count
        }

    @classmethod
    def transition_to_next_semester(cls, current_period: AcademicPeriod, next_period: AcademicPeriod, user=None) -> dict:
        """
        Transitions the school from one semester to the next:
        - Verifies or executes closure on current_period.
        - Sets next_period.is_current = True, next_period.status = PeriodStatus.OPEN.
        - Unsets current_period.is_current.
        """
        school = current_period.school

        # If current period is not closed or locked, lock and archive it
        if current_period.status == PeriodStatus.OPEN:
            cls.lock_semester(current_period, user=user, reason="Automated lock prior to term rollover.")

        # Ensure historical archive exists
        if not SemesterArchive.objects.filter(school=school, period=current_period).exists():
            cls.create_semester_archive(current_period, user=user, notes="Archive created during term rollover.")

        # Rollover is_current pointer
        current_period.is_current = False
        current_period.save(update_fields=['is_current'])

        next_period.is_current = True
        if next_period.status != PeriodStatus.OPEN:
            next_period.status = PeriodStatus.OPEN
        next_period.save(update_fields=['is_current', 'status'])

        AuditService.log_action(
            school=school,
            user=user,
            action="SEMESTER_ROLLOVER_EXECUTED",
            object_type="AcademicPeriod",
            object_id=str(next_period.id),
            details={
                "previous_period": current_period.name,
                "new_active_period": next_period.name,
                "academic_year": next_period.academic_year.name if next_period.academic_year else ""
            }
        )

        return {
            "success": True,
            "message": f"Successfully transitioned school from '{current_period.name}' to '{next_period.name}'."
        }

    @classmethod
    def configure_supplementary_exams(cls, period: AcademicPeriod, start_date, end_date, user=None) -> dict:
        """
        Schedules supplementary/re-sit examination window for students with failed subjects or conditional status.
        """
        school = period.school
        if isinstance(start_date, str):
            start_date = datetime.date.fromisoformat(start_date)
        if isinstance(end_date, str):
            end_date = datetime.date.fromisoformat(end_date)

        if start_date >= end_date:
            return {"success": False, "error": "Supplementary exam start date must precede end date."}

        period.has_supplementary_exam = True
        period.supplementary_start_date = start_date
        period.supplementary_end_date = end_date
        period.save(update_fields=['has_supplementary_exam', 'supplementary_start_date', 'supplementary_end_date'])

        # Create calendar event
        event_title = f"{period.name} — Supplementary & Re-Sit Examinations"
        SchoolEvent.objects.update_or_create(
            school=school,
            academic_year=period.academic_year,
            title=event_title,
            defaults={
                'academic_period': period,
                'event_category': EventCategory.EXAMINATION,
                'event_type': EventType.EXAM_PERIOD,
                'target_audience': TargetAudience.ALL,
                'status': EventStatus.SCHEDULED,
                'start_date': start_date,
                'end_date': end_date,
                'location': "Designated Testing Halls",
                'description': f"Official supplementary and makeup examination session for {period.name}.",
                'is_automated': True,
                'is_override': False,
                'is_active': True,
                'created_by': user
            }
        )

        AuditService.log_action(
            school=school,
            user=user,
            action="SUPPLEMENTARY_EXAMS_SCHEDULED",
            object_type="AcademicPeriod",
            object_id=str(period.id),
            details={
                "period_name": period.name,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        )

        return {
            "success": True,
            "message": f"Supplementary examinations for '{period.name}' scheduled from {start_date} to {end_date}."
        }
