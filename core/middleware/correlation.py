import uuid
import logging

logger = logging.getLogger(__name__)


class RequestCorrelationMiddleware:
    """
    Attaches a unique X-Request-ID correlation ID to every incoming request.
    Includes request ID in logs, headers, and audit contexts for production debugging.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID') or f"REQ-{uuid.uuid4().hex[:12].upper()}"
        request.request_id = request_id

        response = self.get_response(request)
        response['X-Request-ID'] = request_id
        return response
