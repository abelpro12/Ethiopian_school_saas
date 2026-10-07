from apps.messaging.models import Message


def unread_messages_context(request):
    """
    Context processor that injects unread message count for the current authenticated user into all templates.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'unread_messages_count': 0}

    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school:
        return {'unread_messages_count': 0}

    try:
        count = Message.objects.filter(
            conversation__school=school,
            conversation__participants=request.user,
            is_read=False
        ).exclude(sender=request.user).count()
        return {'unread_messages_count': count}
    except Exception:
        return {'unread_messages_count': 0}
