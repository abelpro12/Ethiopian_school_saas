import logging
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.students.models import StudentClearance, StudentProfile, ClearanceStatus, WithdrawalReason
from apps.enrollment.models import StudentEnrollment
from apps.audit.services import AuditService
from apps.communication.models import NotificationChannel
from apps.notifications.services import NotificationService

logger = logging.getLogger(__name__)


class ClearanceService:
    @staticmethod
    def get_student_operational_summary(student):
        """
        Retrieves real-time operational status for a student across:
        - Finance (unpaid invoices and total balance)
        - Library (unreturned borrowed books)
        - Academic / Enrollment status
        """
        school = student.school
        
        # Finance balance
        outstanding_balance = 0.00
        unpaid_invoices_count = 0
        try:
            from apps.finance.models import StudentInvoice, InvoiceStatus
            unpaid_invoices = StudentInvoice.objects.filter(
                school=school,
                student=student,
                status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]
            )
            unpaid_invoices_count = unpaid_invoices.count()
            outstanding_balance = float(sum(inv.remaining_balance for inv in unpaid_invoices))
        except Exception as e:
            logger.warning(f"Error checking finance for student {student.id}: {e}")

        # Library unreturned books
        unreturned_books_count = 0
        unreturned_books_titles = []
        try:
            from apps.library.models import BorrowRecord
            borrows = BorrowRecord.objects.filter(
                school=school,
                borrower_student=student,
                return_date__isnull=True
            ).select_related('book_copy__book')
            unreturned_books_count = borrows.count()
            unreturned_books_titles = [b.book_copy.book.title for b in borrows[:5]]
        except Exception as e:
            logger.warning(f"Error checking library for student {student.id}: {e}")

        # Active enrollment
        active_enrollment = StudentEnrollment.objects.filter(
            school=school,
            student=student,
            status='ACTIVE'
        ).select_related('section', 'grade', 'academic_year').first()

        return {
            'outstanding_balance': outstanding_balance,
            'unpaid_invoices_count': unpaid_invoices_count,
            'unreturned_books_count': unreturned_books_count,
            'unreturned_books_titles': unreturned_books_titles,
            'active_enrollment': active_enrollment,
        }

    @classmethod
    @transaction.atomic
    def initiate_clearance(cls, school, student, withdrawal_reason, reason_details=None,
                           destination_school=None, effective_date=None, user=None):
        """
        Initiates a new multi-department student clearance and withdrawal request.
        """
        if not effective_date:
            effective_date = timezone.now().date()

        # Check if an in-progress clearance already exists
        existing_active = StudentClearance.objects.filter(
            school=school,
            student=student,
            status__in=[ClearanceStatus.INITIATED, ClearanceStatus.UNDER_REVIEW]
        ).first()

        if existing_active:
            raise ValidationError(f"An active clearance request ({existing_active.clearance_number}) is already in progress for this student.")

        summary = cls.get_student_operational_summary(student)
        active_enrollment = summary['active_enrollment']
        academic_year = active_enrollment.academic_year if active_enrollment else None

        if not academic_year:
            from apps.academics.models import AcademicYear
            academic_year = AcademicYear.objects.filter(school=school, is_active=True).first()
            if not academic_year:
                academic_year = AcademicYear.objects.filter(school=school).first()

        if not academic_year:
            raise ValidationError("An active Academic Year is required to initiate clearance.")

        clearance_number = StudentClearance.generate_next_clearance_number(school)

        # Pre-populate finance balance
        balance = summary['outstanding_balance']
        auto_finance_remarks = f"Initial balance detected: {balance:.2f} ETB across {summary['unpaid_invoices_count']} invoice(s)." if balance > 0 else "No unpaid invoices on record."
        
        # Pre-populate library status
        auto_library_remarks = ""
        if summary['unreturned_books_count'] > 0:
            titles = ", ".join(summary['unreturned_books_titles'])
            auto_library_remarks = f"Student currently holds {summary['unreturned_books_count']} unreturned library item(s): {titles}."

        clearance = StudentClearance.objects.create(
            school=school,
            student=student,
            enrollment=active_enrollment,
            academic_year=academic_year,
            clearance_number=clearance_number,
            withdrawal_reason=withdrawal_reason,
            reason_details=reason_details or '',
            destination_school=destination_school or '',
            effective_date=effective_date,
            status=ClearanceStatus.INITIATED,
            outstanding_balance=balance,
            finance_remarks=auto_finance_remarks,
            library_remarks=auto_library_remarks,
            created_by=user
        )

        AuditService.log_action(
            school=school,
            user=user,
            action='INITIATE_STUDENT_CLEARANCE',
            object_type='StudentClearance',
            object_id=str(clearance.id),
            details={
                'clearance_number': clearance_number,
                'student': student.full_name,
                'student_id': student.student_id,
                'reason': withdrawal_reason,
                'destination_school': destination_school
            }
        )

        # Notify student / parent
        try:
            if student.user:
                NotificationService.send_notification(
                    school=school,
                    recipient_user=student.user,
                    channel=NotificationChannel.IN_APP,
                    message=f"A clearance request ({clearance_number}) has been initiated for {student.full_name}.",
                    subject="Clearance & Withdrawal Request Initiated",
                    category="announcement"
                )
        except Exception as e:
            logger.warning(f"Failed to send clearance initiation notification: {e}")

        return clearance

    @classmethod
    @transaction.atomic
    def sign_department(cls, school, clearance, department: str, cleared: bool, remarks: str = None, user=None):
        """
        Signs off or flags a specific department's clearance checklist item.
        Departments: 'library', 'finance', 'academic', 'property'
        """
        now = timezone.now()
        dept = department.lower().strip()

        if dept == 'library':
            clearance.library_cleared = cleared
            clearance.library_cleared_by = user
            clearance.library_cleared_at = now
            if remarks:
                clearance.library_remarks = remarks
        elif dept == 'finance':
            clearance.finance_cleared = cleared
            clearance.finance_cleared_by = user
            clearance.finance_cleared_at = now
            # Recheck balance
            summary = cls.get_student_operational_summary(clearance.student)
            clearance.outstanding_balance = summary['outstanding_balance']
            if remarks:
                clearance.finance_remarks = remarks
        elif dept == 'academic':
            clearance.academic_cleared = cleared
            clearance.academic_cleared_by = user
            clearance.academic_cleared_at = now
            if remarks:
                clearance.academic_remarks = remarks
        elif dept == 'property':
            clearance.property_cleared = cleared
            clearance.property_cleared_by = user
            clearance.property_cleared_at = now
            if remarks:
                clearance.property_remarks = remarks
        else:
            raise ValidationError(f"Invalid clearance department '{department}'. Must be one of library, finance, academic, property.")

        # If any signoff is updated and status is INITIATED, transition to UNDER_REVIEW
        if clearance.status == ClearanceStatus.INITIATED:
            clearance.status = ClearanceStatus.UNDER_REVIEW

        clearance.save()

        AuditService.log_action(
            school=school,
            user=user,
            action=f'SIGN_CLEARANCE_{dept.upper()}',
            object_type='StudentClearance',
            object_id=str(clearance.id),
            details={
                'clearance_number': clearance.clearance_number,
                'department': dept,
                'cleared': cleared,
                'remarks': remarks
            }
        )

        return clearance

    @classmethod
    @transaction.atomic
    def finalize_clearance(cls, school, clearance, approved: bool, final_remarks: str = None, user=None):
        """
        Final registrar / principal approval or rejection.
        When approved:
        - Validates all 4 departments are cleared.
        - Stamps certificate number and timestamp.
        - Transitions student profile status to TRANSFERRED or WITHDRAWN.
        - Updates student enrollment status.
        """
        now = timezone.now()

        if approved:
            if not clearance.all_departments_cleared:
                missing = []
                if not clearance.library_cleared: missing.append("Library")
                if not clearance.finance_cleared: missing.append("Finance")
                if not clearance.academic_cleared: missing.append("Academic")
                if not clearance.property_cleared: missing.append("Property/Store")
                raise ValidationError(f"Cannot grant final clearance approval. Pending sign-off from: {', '.join(missing)}.")

            clearance.status = ClearanceStatus.APPROVED
            clearance.final_approved_by = user
            clearance.final_approved_at = now
            clearance.final_remarks = final_remarks or 'Clearance completed and verified by administration.'
            clearance.certificate_issued = True
            clearance.certificate_number = clearance.clearance_number
            clearance.certificate_issued_at = now
            clearance.save()

            # Transition student status
            student = clearance.student
            if clearance.withdrawal_reason == WithdrawalReason.TRANSFER:
                student.status = 'TRANSFERRED'
            else:
                student.status = 'WITHDRAWN'
            student.save(update_fields=['status'])

            # Transition enrollment status
            if clearance.enrollment:
                enr = clearance.enrollment
                enr.status = 'TRANSFERRED' if clearance.withdrawal_reason == WithdrawalReason.TRANSFER else 'WITHDRAWN'
                enr.save(update_fields=['status'])

            AuditService.log_action(
                school=school,
                user=user,
                action='FINALIZE_STUDENT_CLEARANCE_APPROVED',
                object_type='StudentClearance',
                object_id=str(clearance.id),
                details={
                    'clearance_number': clearance.clearance_number,
                    'student': student.full_name,
                    'new_student_status': student.status,
                    'certificate_number': clearance.certificate_number
                }
            )

            # Notify student
            try:
                if student.user:
                    NotificationService.send_notification(
                        school=school,
                        recipient_user=student.user,
                        channel=NotificationChannel.IN_APP,
                        message=f"Official Clearance Certificate {clearance.certificate_number} has been approved and issued.",
                        subject="Clearance Certificate Approved",
                        category="announcement"
                    )
            except Exception as e:
                logger.warning(f"Failed to send clearance approval notification: {e}")

        else:
            clearance.status = ClearanceStatus.REJECTED
            clearance.final_approved_by = user
            clearance.final_approved_at = now
            clearance.final_remarks = final_remarks or 'Clearance rejected by administration.'
            clearance.save()

            AuditService.log_action(
                school=school,
                user=user,
                action='FINALIZE_STUDENT_CLEARANCE_REJECTED',
                object_type='StudentClearance',
                object_id=str(clearance.id),
                details={
                    'clearance_number': clearance.clearance_number,
                    'student': clearance.student.full_name,
                    'remarks': final_remarks
                }
            )

        return clearance
