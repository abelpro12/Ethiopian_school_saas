from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .services import ChapaService


@csrf_exempt
@require_POST
def chapa_webhook_view(request):
    """
    Receives Chapa payment webhooks, verifies HMAC signature,
    and updates invoice status & issues receipt idempotently.
    """
    signature = request.headers.get('Chapa-Signature') or request.headers.get('x-chapa-signature', '')
    if not ChapaService.verify_webhook_signature(request.body, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    tx_ref = request.POST.get('trx_ref') or request.POST.get('tx_ref')
    status = request.POST.get('status', 'success')

    if not tx_ref:
        # Try parsing JSON body if POST form empty
        import json
        try:
            data = json.loads(request.body.decode('utf-8'))
            tx_ref = data.get('trx_ref') or data.get('tx_ref')
            status = data.get('status', 'success')
        except Exception:
            pass

    if not tx_ref:
        return JsonResponse({'error': 'Missing transaction reference'}, status=400)

    try:
        payment = ChapaService.process_payment_webhook(tx_ref=tx_ref, payment_status=status)
        return JsonResponse({
            'status': 'success',
            'payment_status': payment.status,
            'tx_ref': payment.tx_ref
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
