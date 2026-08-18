from django.db import transaction
from django.utils import timezone
from apps.assessments.models import (
    StudentMark, MarkChangeAudit, ResultCorrectionRequest,
    ResultCorrectionRequestStatus, AcademicPeriodResult, MarkStatus
)

class MarkCorrectionError(Exception):
    pass

class MarkCorrectionService:
    @staticmethod
    @transaction.atomic
    def approve_correction_request(correction_request, admin_user):
        """
        Approves a post-lock result correction request:
        1. Verifies request is in PENDING state.
        2. Logs immutable MarkChangeAudit record (old_value, new_value, reason, changed_by).
        3. Updates StudentMark value.
        4. Recalculates AcademicPeriodResult for the enrollment and period.
        """
        if correction_request.status != ResultCorrectionRequestStatus.PENDING:
            raise MarkCorrectionError(f"Correction request is already {correction_request.get_status_display()}.")

        mark = correction_request.mark
        old_value = mark.mark_value
        new_value = correction_request.requested_value

        # 1. Log Audit
        MarkChangeAudit.objects.create(
            school=correction_request.school,
            mark=mark,
            old_value=old_value,
            new_value=new_value,
            reason=correction_request.reason,
            changed_by=admin_user
        )

        # 2. Apply Mark Update
        mark.mark_value = new_value
        mark.save()

        # 3. Update Request Status
        correction_request.status = ResultCorrectionRequestStatus.APPROVED
        correction_request.reviewed_by = admin_user
        correction_request.save()

        # 4. Recalculate Period Result if applicable
        enrollment = mark.enrollment
        period = mark.assessment_component.period
        school = mark.school

        all_period_marks = StudentMark.objects.filter(
            school=school,
            enrollment=enrollment,
            assessment_component__period=period
        )

        total_score = sum(m.mark_value for m in all_period_marks)
        count = all_period_marks.count()
        avg_score = (total_score / count) if count > 0 else 0

        # Update cache JSON
        results_json = {}
        for m in all_period_marks:
            results_json[m.assessment_component.subject.code] = float(m.mark_value)

        AcademicPeriodResult.objects.update_or_create(
            school=school,
            enrollment=enrollment,
            period=period,
            defaults={
                'total_score': total_score,
                'average_score': avg_score,
                'results_json': results_json
            }
        )

        return mark
