import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import UserRole
from apps.finance.models import (
    DiscountPolicy, DiscountType, DiscountCategory, StudentDiscount,
    StudentInvoice, InvoiceItem, FinancialTransaction, TransactionType,
    InvoiceStatus, FeeCategory
)
from apps.parents.models import GuardianRelationship
from apps.students.models import StudentProfile
from apps.teachers.models import TeacherProfile, StaffProfile

logger = logging.getLogger(__name__)


class DiscountService:
    @staticmethod
    def detect_sibling_info(student: StudentProfile) -> dict:
        """
        Detects all siblings for a student across all linked parent/guardian relationships.
        Determines the sibling order (1st child, 2nd child, 3rd child, etc.) based on
        admission date and birth date.
        """
        school = student.school
        parent_ids = GuardianRelationship.objects.filter(
            school=school, student=student
        ).values_list('parent_id', flat=True)

        if not parent_ids:
            return {
                'sibling_count': 1,
                'sibling_order': 1,
                'siblings': [student],
                'has_siblings': False,
            }

        # Query all students linked to any of the student's parents
        siblings_qs = StudentProfile.objects.filter(
            school=school,
            guardianships__parent_id__in=parent_ids
        ).distinct()

        # Sort siblings: older birth_date first (1st child is oldest), then earliest enrollment, then date_joined
        def sort_key(s):
            dob = s.date_of_birth or timezone.now().date()
            first_enr = s.enrollments.order_by('enrollment_date', 'id').first()
            enr_date = first_enr.enrollment_date if first_enr else timezone.now().date()
            joined = s.user.date_joined if s.user and hasattr(s.user, 'date_joined') else timezone.now()
            return (dob, enr_date, joined, str(s.id))

        all_siblings = sorted(list(siblings_qs), key=sort_key)
        sibling_count = len(all_siblings)

        try:
            student_index = [s.id for s in all_siblings].index(student.id)
            sibling_order = student_index + 1
        except ValueError:
            sibling_order = 1

        return {
            'sibling_count': sibling_count,
            'sibling_order': sibling_order,
            'siblings': all_siblings,
            'has_siblings': sibling_count > 1,
        }

    @staticmethod
    def is_staff_child(student: StudentProfile) -> tuple[bool, str]:
        """
        Checks whether a student has a parent/guardian who is an employee/staff/teacher at the school.
        Returns (is_staff_child, staff_details_string).
        """
        school = student.school
        guardians = GuardianRelationship.objects.filter(
            school=school, student=student
        ).select_related('parent__user')

        staff_roles = [
            UserRole.TEACHER, UserRole.ACCOUNTANT, UserRole.HR_MANAGER,
            UserRole.REGISTRAR, UserRole.PRINCIPAL, UserRole.LIBRARIAN,
            UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN
        ]

        for g in guardians:
            parent_user = g.parent.user
            if not parent_user:
                continue

            # Check direct role
            if parent_user.role in staff_roles:
                return True, f"Parent {parent_user.get_full_name()} ({parent_user.get_role_display()})"

            # Check if teacher profile exists
            if TeacherProfile.objects.filter(school=school, user=parent_user).exists():
                return True, f"Parent {parent_user.get_full_name()} (Teacher)"

            # Check if staff profile exists
            if StaffProfile.objects.filter(school=school, user=parent_user).exists():
                return True, f"Parent {parent_user.get_full_name()} (Staff)"

            # Check phone match with active staff
            parent_phone = (g.parent.phone or '').strip()
            if parent_phone:
                if TeacherProfile.objects.filter(school=school, phone=parent_phone).exists():
                    return True, f"Parent phone match ({parent_phone}) with Teacher Profile"

        return False, ""

    @staticmethod
    def get_applicable_discount(
        student: StudentProfile,
        academic_year,
        fee_category: FeeCategory = None
    ) -> tuple[DiscountPolicy | None, str]:
        """
        Finds the highest-priority applicable discount policy for a student.
        Order of precedence:
        1. Explicitly assigned StudentDiscount (e.g. Merit, Need-based, Custom)
        2. Staff Child Waiver (if parent is employee)
        3. Multi-Child Sibling Discount (based on sibling_order: 2nd child 10%, 3rd+ 20%)
        """
        school = student.school

        # 1. Explicit StudentDiscount assigned for this year
        assigned = StudentDiscount.objects.filter(
            school=school,
            student=student,
            academic_year=academic_year,
            is_active=True,
            discount_policy__is_active=True
        ).select_related('discount_policy').first()

        if assigned:
            policy = assigned.discount_policy
            if not policy.fee_category or policy.fee_category == fee_category:
                return policy, f"Assigned: {policy.name}"

        # 2. Staff Child Discount
        is_staff, staff_info = DiscountService.is_staff_child(student)
        if is_staff:
            staff_policy = DiscountPolicy.objects.filter(
                school=school,
                discount_category=DiscountCategory.STAFF_CHILD,
                is_active=True
            ).first()
            if staff_policy:
                if not staff_policy.fee_category or staff_policy.fee_category == fee_category:
                    return staff_policy, f"Staff Child Waiver ({staff_info})"

        # 3. Sibling Multi-Child Discount
        sibling_info = DiscountService.detect_sibling_info(student)
        order = sibling_info['sibling_order']

        if order >= 2:
            # Look for policy exactly matching this order, or highest order <= current order
            sibling_policies = DiscountPolicy.objects.filter(
                school=school,
                discount_category=DiscountCategory.SIBLING,
                is_active=True,
                auto_apply=True
            ).order_by('-sibling_order')

            matching_policy = None
            for p in sibling_policies:
                if p.sibling_order and p.sibling_order <= order:
                    matching_policy = p
                    break

            if matching_policy:
                if not matching_policy.fee_category or matching_policy.fee_category == fee_category:
                    order_suffix = "2nd" if order == 2 else ("3rd" if order == 3 else f"{order}th")
                    return matching_policy, f"Sibling Discount ({order_suffix} Child - Order #{order})"

        return None, ""

    @staticmethod
    def calculate_discount_amount(policy: DiscountPolicy, gross_amount: Decimal) -> Decimal:
        """Calculates discount amount from policy and gross amount."""
        if not policy or gross_amount <= Decimal('0.00'):
            return Decimal('0.00')

        if policy.discount_type == DiscountType.PERCENTAGE:
            pct = policy.value / Decimal('100.00')
            discount = (gross_amount * pct).quantize(Decimal('0.01'))
        else:
            discount = policy.value.quantize(Decimal('0.01'))

        return min(discount, gross_amount)

    @classmethod
    @transaction.atomic
    def apply_discount_to_invoice(
        cls,
        invoice: StudentInvoice,
        policy: DiscountPolicy = None,
        reason: str = None,
        user=None
    ) -> StudentInvoice:
        """
        Applies a discount policy to an invoice.
        Calculates eligible base amount (taking into account fee_category constraints if any),
        updates discount_amount, discount_policy, discount_reason, and adjusts invoice status.
        Creates or updates ledger FinancialTransaction for audit trail.
        """
        school = invoice.school

        if policy is None:
            policy, calculated_reason = cls.get_applicable_discount(
                invoice.student,
                invoice.academic_year
            )
            if not reason:
                reason = calculated_reason

        if not policy:
            # If no policy applies, reset discount if previously zero-based
            return invoice

        # Calculate base amount eligible for discount
        if policy.fee_category:
            items = invoice.items.filter(fee_category=policy.fee_category)
            if items.exists():
                base_amount = sum(item.amount for item in items)
            else:
                base_amount = Decimal('0.00')
        else:
            base_amount = invoice.total_amount

        discount_amount = cls.calculate_discount_amount(policy, base_amount)

        # Update invoice
        invoice.discount_amount = discount_amount
        invoice.discount_policy = policy
        invoice.discount_reason = reason or policy.name

        # Recalculate status
        net_amount = max(Decimal('0.00'), invoice.total_amount - invoice.discount_amount)
        if invoice.paid_amount >= net_amount and net_amount > 0:
            invoice.status = InvoiceStatus.PAID
        elif invoice.paid_amount > 0:
            invoice.status = InvoiceStatus.PARTIALLY_PAID
        elif net_amount == Decimal('0.00'):
            invoice.status = InvoiceStatus.PAID
        else:
            if invoice.status == InvoiceStatus.PAID and net_amount > invoice.paid_amount:
                invoice.status = InvoiceStatus.PARTIALLY_PAID

        invoice.save()

        # Record Ledger Transaction for discount
        if discount_amount > Decimal('0.00'):
            disc_ref = f"DISC-{invoice.invoice_number}"
            FinancialTransaction.objects.update_or_create(
                school=school,
                invoice=invoice,
                transaction_type=TransactionType.DISCOUNT,
                defaults={
                    'amount': discount_amount,
                    'reference': disc_ref,
                    'created_by': user
                }
            )

        return invoice

    @classmethod
    def batch_apply_discounts(cls, school, academic_year, grade=None) -> dict:
        """
        Iterates over all invoices in an academic year and applies discounts based
        on active sibling rules, staff child status, and assigned scholarships.
        """
        invoices = StudentInvoice.objects.filter(
            school=school,
            academic_year=academic_year
        ).select_related('student', 'academic_year')

        if grade:
            invoices = invoices.filter(student__enrollments__grade=grade, student__enrollments__academic_year=academic_year)

        processed = 0
        discounted = 0
        total_discount_awarded = Decimal('0.00')

        for invoice in invoices:
            processed += 1
            policy, reason = cls.get_applicable_discount(invoice.student, academic_year)
            if policy:
                cls.apply_discount_to_invoice(invoice, policy=policy, reason=reason)
                discounted += 1
                total_discount_awarded += invoice.discount_amount

        return {
            'processed_count': processed,
            'discounted_count': discounted,
            'total_discount_awarded': total_discount_awarded,
        }

    @staticmethod
    def ensure_default_policies(school):
        """
        Seeds standard Ethiopian private school discount policies if none exist:
        - 2nd Child Sibling Discount (10%)
        - 3rd+ Child Sibling Discount (20%)
        - Staff Child Fee Waiver (50%)
        - Full Academic Merit Scholarship (100%)
        - Need-Based Financial Aid (30%)
        """
        defaults = [
            {
                'name': '2nd Child Sibling Discount (10%)',
                'discount_category': DiscountCategory.SIBLING,
                'discount_type': DiscountType.PERCENTAGE,
                'value': Decimal('10.00'),
                'sibling_order': 2,
                'auto_apply': True,
                'description': 'Standard 10% reduction for the second enrolled child of the same family.',
            },
            {
                'name': '3rd+ Child Sibling Discount (20%)',
                'discount_category': DiscountCategory.SIBLING,
                'discount_type': DiscountType.PERCENTAGE,
                'value': Decimal('20.00'),
                'sibling_order': 3,
                'auto_apply': True,
                'description': 'Standard 20% reduction for the third and subsequent enrolled children of the same family.',
            },
            {
                'name': 'Staff Child Fee Waiver (50%)',
                'discount_category': DiscountCategory.STAFF_CHILD,
                'discount_type': DiscountType.PERCENTAGE,
                'value': Decimal('50.00'),
                'sibling_order': None,
                'auto_apply': True,
                'description': '50% tuition & operational fee waiver for children of active school teachers and staff.',
            },
            {
                'name': 'Academic Merit Scholarship (100%)',
                'discount_category': DiscountCategory.MERIT_SCHOLARSHIP,
                'discount_type': DiscountType.PERCENTAGE,
                'value': Decimal('100.00'),
                'sibling_order': None,
                'auto_apply': False,
                'description': 'Full scholarship awarded to outstanding top-ranking academic achievers.',
            },
            {
                'name': 'Need-Based Financial Assistance (30%)',
                'discount_category': DiscountCategory.NEED_BASED,
                'discount_type': DiscountType.PERCENTAGE,
                'value': Decimal('30.00'),
                'sibling_order': None,
                'auto_apply': False,
                'description': 'Financial aid reduction for low-income families verified by administration.',
            },
        ]

        created_policies = []
        for d in defaults:
            policy, created = DiscountPolicy.objects.get_or_create(
                school=school,
                name=d['name'],
                defaults=d
            )
            created_policies.append(policy)

        return created_policies
