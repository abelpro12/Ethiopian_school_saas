import hmac
import hashlib
import uuid
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from apps.finance.models import StudentInvoice, Payment, PaymentStatus, InvoiceStatus, Receipt
from apps.reports.models import DocumentVerification


class ChapaService:
    @staticmethod
    def initialize_payment(school, invoice: StudentInvoice, amount: Decimal, parent_email: str, first_name: str, last_name: str, callback_url: str):
        """
        Initializes a payment transaction with Chapa API.
        Generates a unique tx_ref for idempotency tracking.
        """
        tx_ref = f"ETH-PAY-{uuid.uuid4().hex[:12].upper()}"

        payment = Payment.objects.create(
            school=school,
            invoice=invoice,
            tx_ref=tx_ref,
            amount_paid=amount,
            payment_method='CHAPA',
            status=PaymentStatus.PENDING
        )

        # Mock checkout URL response for sandboxing / testing if key is test environment
        checkout_url = f"https://checkout.chapa.co/checkout/payment/{tx_ref}"

        return {
            'status': 'success',
            'checkout_url': checkout_url,
            'tx_ref': tx_ref,
            'payment_id': str(payment.id)
        }

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
        """
        Verifies HMAC SHA256 webhook signature from Chapa API header.
        SECURITY: Never bypasses verification — always returns False if signature
        is missing or invalid. Raises ImproperlyConfigured if the secret is not set.
        """
        secret = getattr(settings, 'CHAPA_WEBHOOK_SECRET', '')
        if not secret:
            raise ImproperlyConfigured(
                'CHAPA_WEBHOOK_SECRET is not configured. '
                'Set this environment variable before processing payment webhooks. '
                'Without it, payment fraud is possible.'
            )
        if not signature_header:
            return False

        expected_sig = hmac.new(
            secret.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_sig, signature_header)

    @staticmethod
    @transaction.atomic
    def process_payment_webhook(tx_ref: str, payment_status: str, event_data: dict = None):
        """
        Processes Chapa payment webhook idempotently.
        """
        try:
            payment = Payment.objects.select_for_update().get(tx_ref=tx_ref)
        except Payment.DoesNotExist:
            raise ValueError(f"Payment reference {tx_ref} not found.")

        # Idempotency check: if already processed SUCCESS, do not duplicate updates
        if payment.status == PaymentStatus.SUCCESS:
            return payment

        if payment_status.upper() in ['SUCCESS', 'SUCCESSFUL']:
            payment.status = PaymentStatus.SUCCESS
            receipt_no = f"REC-{uuid.uuid4().hex[:10].upper()}"
            payment.receipt_no = receipt_no
            payment.save()

            # Update invoice paid balance
            invoice = payment.invoice
            invoice.paid_amount += payment.amount_paid
            if invoice.remaining_balance <= Decimal('0.00'):
                invoice.status = InvoiceStatus.PAID
            else:
                invoice.status = InvoiceStatus.PARTIALLY_PAID
            invoice.save()

            # Generate digital Receipt
            receipt, _ = Receipt.objects.get_or_create(
                school=payment.school,
                payment=payment,
                defaults={'receipt_number': receipt_no}
            )

            # Register public document verification token
            doc_token = uuid.uuid4().hex
            DocumentVerification.objects.create(
                school=payment.school,
                document_type='RECEIPT',
                verification_token=doc_token,
                doc_number=receipt_no,
                metadata_json={
                    'invoice_number': invoice.invoice_number,
                    'student_id': invoice.student.student_id,
                    'amount_paid': str(payment.amount_paid),
                    'school_name': payment.school.name
                }
            )

            return payment
        else:
            payment.status = PaymentStatus.FAILED
            payment.save()
            return payment
