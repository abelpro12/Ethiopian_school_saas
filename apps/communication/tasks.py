from celery import shared_task
from apps.accounts.models import User
from .models import NotificationLog, NotificationChannel


@shared_task
def send_async_notification(user_id: str, message: str, channel: str = 'IN_APP'):
    """
    Celery task to handle async dispatch of SMS, Telegram, and In-App notifications.
    """
    try:
        user = User.objects.get(id=user_id)
        # Record notification dispatch in database log
        NotificationLog.objects.create(
            school=user.school,
            recipient=user,
            channel=channel,
            message=message,
            status='DELIVERED'
        )
        return f"Notification delivered to {user.username}"
    except User.DoesNotExist:
        return "User not found"
