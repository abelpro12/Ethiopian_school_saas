from django.db import models
from apps.tenants.models import TenantAwareModel


class WebhookProcessingStatus(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Received'
    PROCESSED = 'PROCESSED', 'Processed'
    FAILED = 'FAILED', 'Failed'


class ChapaWebhookEvent(TenantAwareModel):
    event_id = models.CharField(max_length=100, unique=True)
    tx_ref = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=WebhookProcessingStatus.choices, default=WebhookProcessingStatus.RECEIVED)
    retry_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Webhook Event {self.tx_ref} ({self.status})"
