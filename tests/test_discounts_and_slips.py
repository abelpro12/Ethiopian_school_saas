import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.schools.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, Grade, Stream, Section
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile, EmploymentStatus
from apps.finance.models import (
    FeeCategory, FeeStructure, StudentInvoice, InvoiceItem, InvoiceStatus,
    DiscountPolicy, DiscountType, DiscountCategory, StudentDiscount,
    Payment, PaymentMethod, PaymentStatus, ManualPaymentAuthorization,
    ManualPaymentStatus, FinancialTransaction, TransactionType, Receipt
)
from apps.finance.discount_service import DiscountService


class FamilyDiscountsAndBankDepositSlipsTests(TestCase):
    """
    Unit and integration tests for Priority 3:
    - Item 3: Multi-child family discount & custom discount rules
      (10% for 2nd child, 20% for 3rd+ child, 50% staff child waiver, merit scholarships, batch recalculation).
    - Item 4: Bank Deposit Slip Verification Hub & multi-payment gateway options
      (Slip submission, cashier verification, invoice crediting, receipt generation, rejection handling).
    """

    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Alpha Ethiopian Academy",
            code="ALPHA",
            calendar_preference="ETHIOPIAN"
        )

        # Admin & Accountant
        self.admin = User.objects.create_superuser(
            username="admin_alpha",
            email="admin@alpha.edu.et",
            password="adminpassword123",
            role=UserRole.SCHOOL_ADMIN,
            school=self.school
        )

        self.accountant = User.objects.create_user(
            username="cashier_kassahun",
            email="kassahun@alpha.edu.et",
            password="acctpassword123",
            role=UserRole.ACCOUNTANT,
            school=self.school,
            first_name="Kassahun",
            last_name="Tadesse"
        )

        # Academic Year
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2017 E.C.",
            ethiopian_year=2017,
            gregorian_start_date=datetime.date(2024, 9, 11),
            gregorian_end_date=datetime.date(2025, 7, 7),
            is_active=True
        )

        # Grade, Stream & Section
        self.grade = Grade.objects.create(school=self.school, name="Grade 9", level=9)
        self.stream = Stream.objects.create(school=self.school, name="General", code="GEN")
        self.section = Section.objects.create(
            school=self.school,
            grade=self.grade,
            stream=self.stream,
            name="9-A"
        )

        # Fee Categories
        self.cat_tuition = FeeCategory.objects.create(school=self.school, name="Tuition")
        self.cat_transport = FeeCategory.objects.create(school=self.school, name="Transport")

        # Fee Structure: 1000 ETB Tuition
        self.fee_structure = FeeStructure.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            grade=self.grade,
            fee_category=self.cat_tuition,
            amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30)
        )

    def _create_student(self, student_id, first_name, last_name, dob=None):
        """Helper to create valid StudentProfile with User account."""
        u = User.objects.create_user(
            username=f"u_{student_id.lower()}",
            role=UserRole.STUDENT,
            school=self.school,
            first_name=first_name,
            last_name=last_name
        )
        return StudentProfile.objects.create(
            school=self.school,
            user=u,
            student_id=student_id,
            first_name=first_name,
            middle_name="Abebe",
            last_name=last_name,
            gender="M",
            date_of_birth=dob or datetime.date(2010, 1, 1),
            status="ACTIVE"
        )

    def test_default_discount_policies_creation(self):
        """Verify automatic seeding of standard Ethiopian school discount policies."""
        policies = DiscountService.ensure_default_policies(self.school)
        self.assertEqual(len(policies), 5)

        p_2nd = DiscountPolicy.objects.get(school=self.school, sibling_order=2)
        self.assertEqual(p_2nd.value, Decimal('10.00'))
        self.assertEqual(p_2nd.discount_category, DiscountCategory.SIBLING)

        p_3rd = DiscountPolicy.objects.get(school=self.school, sibling_order=3)
        self.assertEqual(p_3rd.value, Decimal('20.00'))
        self.assertEqual(p_3rd.discount_category, DiscountCategory.SIBLING)

        p_staff = DiscountPolicy.objects.get(school=self.school, discount_category=DiscountCategory.STAFF_CHILD)
        self.assertEqual(p_staff.value, Decimal('50.00'))

    def test_multi_child_sibling_discount_calculation(self):
        """
        Verify that 3 children from the same parent receive correct tiered discounts:
        - 1st child: 0% discount (eldest, born 2010)
        - 2nd child: 10% discount (-100 ETB on 1000 ETB tuition, born 2012)
        - 3rd child: 20% discount (-200 ETB on 1000 ETB tuition, born 2015)
        """
        DiscountService.ensure_default_policies(self.school)

        # Create Parent
        parent_user = User.objects.create_user(
            username="parent_abebe",
            first_name="Abebe",
            last_name="Kebede",
            role=UserRole.PARENT,
            school=self.school
        )
        parent_profile = ParentProfile.objects.create(
            school=self.school,
            user=parent_user,
            phone="0911223344"
        )

        # Create 3 children with ordered birth dates (eldest first)
        child1 = self._create_student("STU-001", "Nahom", "Abebe", dob=datetime.date(2010, 5, 12))
        child2 = self._create_student("STU-002", "Helina", "Abebe", dob=datetime.date(2012, 8, 20))
        child3 = self._create_student("STU-003", "Robel", "Abebe", dob=datetime.date(2015, 3, 10))

        for c in [child1, child2, child3]:
            GuardianRelationship.objects.create(
                school=self.school,
                parent=parent_profile,
                student=c,
                is_primary=True
            )

        # Check sibling detection
        info1 = DiscountService.detect_sibling_info(child1)
        info2 = DiscountService.detect_sibling_info(child2)
        info3 = DiscountService.detect_sibling_info(child3)

        self.assertEqual(info1['sibling_order'], 1)
        self.assertEqual(info2['sibling_order'], 2)
        self.assertEqual(info3['sibling_order'], 3)
        self.assertTrue(info1['has_siblings'])

        # Create invoices for all 3
        inv1 = StudentInvoice.objects.create(
            school=self.school, student=child1, academic_year=self.academic_year,
            invoice_number="INV-2017-001", total_amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )
        inv2 = StudentInvoice.objects.create(
            school=self.school, student=child2, academic_year=self.academic_year,
            invoice_number="INV-2017-002", total_amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )
        inv3 = StudentInvoice.objects.create(
            school=self.school, student=child3, academic_year=self.academic_year,
            invoice_number="INV-2017-003", total_amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )

        # Apply discounts
        DiscountService.apply_discount_to_invoice(inv1)
        DiscountService.apply_discount_to_invoice(inv2)
        DiscountService.apply_discount_to_invoice(inv3)

        inv1.refresh_from_db()
        inv2.refresh_from_db()
        inv3.refresh_from_db()

        # Child 1: standard rate (0 discount)
        self.assertEqual(inv1.discount_amount, Decimal('0.00'))
        self.assertEqual(inv1.remaining_balance, Decimal('1000.00'))

        # Child 2: 10% discount (100 ETB)
        self.assertEqual(inv2.discount_amount, Decimal('100.00'))
        self.assertEqual(inv2.remaining_balance, Decimal('900.00'))
        self.assertEqual(inv2.net_amount, Decimal('900.00'))
        self.assertIn("Sibling Discount", inv2.discount_reason)

        # Child 3: 20% discount (200 ETB)
        self.assertEqual(inv3.discount_amount, Decimal('200.00'))
        self.assertEqual(inv3.remaining_balance, Decimal('800.00'))
        self.assertEqual(inv3.net_amount, Decimal('800.00'))
        self.assertIn("Sibling Discount", inv3.discount_reason)

        # Ledger transaction created for child 2 and child 3
        tx_disc = FinancialTransaction.objects.filter(
            invoice=inv2, transaction_type=TransactionType.DISCOUNT
        ).first()
        self.assertIsNotNone(tx_disc)
        self.assertEqual(tx_disc.amount, Decimal('100.00'))

    def test_staff_child_50_percent_waiver(self):
        """Verify automatic 50% fee waiver for child of active teacher."""
        DiscountService.ensure_default_policies(self.school)

        # Teacher user & profile
        teacher_user = User.objects.create_user(
            username="teacher_almaz",
            first_name="Almaz",
            last_name="Tarekegn",
            role=UserRole.TEACHER,
            school=self.school
        )
        TeacherProfile.objects.create(
            school=self.school,
            user=teacher_user,
            employee_id="T-100",
            employment_status=EmploymentStatus.FULL_TIME
        )

        parent_profile = ParentProfile.objects.create(
            school=self.school,
            user=teacher_user,
            phone="0922334455"
        )

        student = self._create_student("STU-STAFF-01", "Yonas", "Almaz", dob=datetime.date(2013, 1, 1))
        GuardianRelationship.objects.create(
            school=self.school,
            parent=parent_profile,
            student=student,
            is_primary=True
        )

        is_staff, staff_desc = DiscountService.is_staff_child(student)
        self.assertTrue(is_staff)

        # Invoice for 2000 ETB
        invoice = StudentInvoice.objects.create(
            school=self.school,
            student=student,
            academic_year=self.academic_year,
            invoice_number="INV-2017-STAFF",
            total_amount=Decimal('2000.00'),
            due_date=datetime.date(2024, 10, 30),
            status=InvoiceStatus.UNPAID
        )

        DiscountService.apply_discount_to_invoice(invoice)
        invoice.refresh_from_db()

        # 50% discount = 1000 ETB
        self.assertEqual(invoice.discount_amount, Decimal('1000.00'))
        self.assertEqual(invoice.remaining_balance, Decimal('1000.00'))
        self.assertIn("Staff Child", invoice.discount_reason)

    def test_explicit_academic_merit_scholarship_assignment(self):
        """Verify that an explicit 100% Merit Scholarship overrides defaults and clears invoice balance."""
        DiscountService.ensure_default_policies(self.school)

        merit_policy = DiscountPolicy.objects.get(
            school=self.school, discount_category=DiscountCategory.MERIT_SCHOLARSHIP
        )

        student = self._create_student("STU-MERIT-01", "Kidus", "Girma", dob=datetime.date(2010, 2, 2))

        # Assign merit scholarship to Kidus
        StudentDiscount.objects.create(
            school=self.school,
            student=student,
            academic_year=self.academic_year,
            discount_policy=merit_policy,
            approved_by=self.admin,
            notes="1st Rank in Grade 8 Regional Examinations"
        )

        invoice = StudentInvoice.objects.create(
            school=self.school,
            student=student,
            academic_year=self.academic_year,
            invoice_number="INV-2017-MERIT",
            total_amount=Decimal('1500.00'),
            due_date=datetime.date(2024, 10, 30),
            status=InvoiceStatus.UNPAID
        )

        DiscountService.apply_discount_to_invoice(invoice)
        invoice.refresh_from_db()

        self.assertEqual(invoice.discount_amount, Decimal('1500.00'))
        self.assertEqual(invoice.remaining_balance, Decimal('0.00'))
        self.assertEqual(invoice.status, InvoiceStatus.PAID)

    def test_batch_recalculate_discounts(self):
        """Verify batch recalculation applies discounts across multiple invoices."""
        DiscountService.ensure_default_policies(self.school)

        parent_user = User.objects.create_user(
            username="parent_birhanu", role=UserRole.PARENT, school=self.school
        )
        parent_profile = ParentProfile.objects.create(
            school=self.school, user=parent_user, phone="0933445566"
        )

        st1 = self._create_student("STU-B1", "B1", "Birhanu", dob=datetime.date(2011, 1, 1))
        st2 = self._create_student("STU-B2", "B2", "Birhanu", dob=datetime.date(2013, 1, 1))

        GuardianRelationship.objects.create(school=self.school, parent=parent_profile, student=st1)
        GuardianRelationship.objects.create(school=self.school, parent=parent_profile, student=st2)

        inv1 = StudentInvoice.objects.create(
            school=self.school, student=st1, academic_year=self.academic_year,
            invoice_number="INV-B1", total_amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30)
        )
        inv2 = StudentInvoice.objects.create(
            school=self.school, student=st2, academic_year=self.academic_year,
            invoice_number="INV-B2", total_amount=Decimal('1000.00'),
            due_date=datetime.date(2024, 10, 30)
        )

        result = DiscountService.batch_apply_discounts(self.school, self.academic_year)
        self.assertEqual(result['processed_count'], 2)
        self.assertEqual(result['discounted_count'], 1)
        self.assertEqual(result['total_discount_awarded'], Decimal('100.00'))

        inv2.refresh_from_db()
        self.assertEqual(inv2.discount_amount, Decimal('100.00'))

    def test_bank_deposit_slip_submission_by_parent(self):
        """Verify that a parent can submit a bank deposit slip for an invoice."""
        parent_user = User.objects.create_user(
            username="parent_samuel", password="pass123", role=UserRole.PARENT, school=self.school
        )
        parent_profile = ParentProfile.objects.create(
            school=self.school, user=parent_user, phone="0944556677"
        )
        student = self._create_student("STU-SAM", "Samuel Jr", "Samuel", dob=datetime.date(2011, 4, 4))
        GuardianRelationship.objects.create(school=self.school, parent=parent_profile, student=student)

        invoice = StudentInvoice.objects.create(
            school=self.school, student=student, academic_year=self.academic_year,
            invoice_number="INV-SAM-01", total_amount=Decimal('1200.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )

        dummy_image = SimpleUploadedFile("slip.jpg", b"fake_image_bytes", content_type="image/jpeg")

        self.client.force_login(parent_user)
        response = self.client.post(
            reverse('finance:parent_pay', kwargs={'invoice_id': invoice.id}),
            {
                'payment_method': 'BANK_TRANSFER',
                'bank_name': 'Commercial Bank of Ethiopia (CBE)',
                'bank_reference': 'FT2409849201',
                'deposit_date': '2024-10-15',
                'amount_paid': '1200.00',
                'deposit_slip_image': dummy_image,
                'notes': 'Deposited via CBE Bole Branch'
            }
        )
        self.assertEqual(response.status_code, 302)

        # Verify Payment and ManualPaymentAuthorization records
        payment = Payment.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.payment_method, PaymentMethod.BANK_TRANSFER)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.amount_paid, Decimal('1200.00'))

        auth = ManualPaymentAuthorization.objects.filter(payment=payment).first()
        self.assertIsNotNone(auth)
        self.assertEqual(auth.status, ManualPaymentStatus.PENDING)
        self.assertEqual(auth.bank_reference, 'FT2409849201')
        self.assertEqual(auth.bank_name, 'Commercial Bank of Ethiopia (CBE)')
        self.assertEqual(auth.submitted_by, parent_user)

    def test_cashier_approve_deposit_slip_and_credit_invoice(self):
        """Verify cashier approval credits invoice, issues receipt, and records credit ledger entry."""
        student = self._create_student("STU-LIYA", "Liya", "Mulugeta")
        invoice = StudentInvoice.objects.create(
            school=self.school, student=student, academic_year=self.academic_year,
            invoice_number="INV-LIYA-01", total_amount=Decimal('800.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )
        payment = Payment.objects.create(
            school=self.school, invoice=invoice, tx_ref="SLIP-LIYA-1",
            amount_paid=Decimal('800.00'), payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.PENDING
        )
        auth = ManualPaymentAuthorization.objects.create(
            school=self.school, payment=payment, bank_reference="CBE-991204",
            bank_name="CBE", status=ManualPaymentStatus.PENDING
        )

        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse('finance:verify_deposit_slip', kwargs={'auth_id': auth.id}),
            {
                'action': 'approve',
                'verified_amount': '800.00',
                'notes': 'Verified with CBE online portal'
            }
        )
        self.assertEqual(response.status_code, 302)

        auth.refresh_from_db()
        payment.refresh_from_db()
        invoice.refresh_from_db()

        self.assertEqual(auth.status, ManualPaymentStatus.APPROVED)
        self.assertEqual(auth.authorized_by, self.accountant)
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)
        self.assertTrue(payment.receipt_no.startswith("REC-MAN-"))

        # Invoice updated to PAID
        self.assertEqual(invoice.paid_amount, Decimal('800.00'))
        self.assertEqual(invoice.remaining_balance, Decimal('0.00'))
        self.assertEqual(invoice.status, InvoiceStatus.PAID)

        # Ledger transaction created
        tx = FinancialTransaction.objects.filter(invoice=invoice, transaction_type=TransactionType.CREDIT).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal('800.00'))

        # Receipt created
        receipt = Receipt.objects.filter(payment=payment).first()
        self.assertIsNotNone(receipt)

    def test_cashier_reject_deposit_slip(self):
        """Verify cashier rejection marks authorization REJECTED and payment FAILED with reason."""
        student = self._create_student("STU-TIG", "Tigist", "Bekele")
        invoice = StudentInvoice.objects.create(
            school=self.school, student=student, academic_year=self.academic_year,
            invoice_number="INV-TIG-01", total_amount=Decimal('500.00'),
            due_date=datetime.date(2024, 10, 30), status=InvoiceStatus.UNPAID
        )
        payment = Payment.objects.create(
            school=self.school, invoice=invoice, tx_ref="SLIP-TIG-1",
            amount_paid=Decimal('500.00'), payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.PENDING
        )
        auth = ManualPaymentAuthorization.objects.create(
            school=self.school, payment=payment, bank_reference="FAKE-9999",
            bank_name="Awash Bank", status=ManualPaymentStatus.PENDING
        )

        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse('finance:verify_deposit_slip', kwargs={'auth_id': auth.id}),
            {
                'action': 'reject',
                'rejection_reason': 'Transaction ID does not exist in Awash Bank records'
            }
        )
        self.assertEqual(response.status_code, 302)

        auth.refresh_from_db()
        payment.refresh_from_db()
        invoice.refresh_from_db()

        self.assertEqual(auth.status, ManualPaymentStatus.REJECTED)
        self.assertEqual(auth.rejection_reason, 'Transaction ID does not exist in Awash Bank records')
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(invoice.paid_amount, Decimal('0.00'))
        self.assertEqual(invoice.status, InvoiceStatus.UNPAID)
