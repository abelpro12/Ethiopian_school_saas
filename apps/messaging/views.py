import django.utils.timezone as tz
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Conversation, Message
from apps.platform_management.decorators import school_context_required


@login_required
@school_context_required
def inbox_view(request):
    """User's messaging inbox — shows all conversations."""
    school = getattr(request, 'school', None)
    user = request.user
    conversations = Conversation.objects.filter(
        school=school,
        participants=user,
        is_archived=False
    ).prefetch_related('participants', 'messages').order_by('-created_at')

    # Annotate unread counts
    conv_data = []
    total_unread = 0
    for conv in conversations:
        unread = conv.unread_count_for(user)
        total_unread += unread
        last_msg = conv.last_message()
        conv_data.append({'conv': conv, 'unread': unread, 'last_message': last_msg})

    return render(request, 'messaging/inbox.html', {
        'conv_data': conv_data,
        'total_unread': total_unread,
    })


@login_required
def compose_view(request):
    """Compose a new message / start a conversation."""
    school = getattr(request, 'school', None)
    from apps.accounts.models import User, UserRole
    # Only allow messaging between certain roles
    allowed_roles = [UserRole.TEACHER, UserRole.PARENT, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]
    recipients = User.objects.filter(school=school, role__in=allowed_roles).exclude(id=request.user.id).order_by('first_name')

    if request.method == 'POST':
        recipient_id = request.POST.get('recipient_id')
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '').strip()

        if not recipient_id or not subject or not body:
            messages.error(request, "Recipient, subject, and message body are all required.")
            return render(request, 'messaging/compose.html', {'recipients': recipients})

        try:
            recipient = User.objects.get(id=recipient_id, school=school)
        except User.DoesNotExist:
            messages.error(request, "Recipient not found.")
            return render(request, 'messaging/compose.html', {'recipients': recipients})

        conv = Conversation.objects.create(school=school, subject=subject, created_by=request.user)
        conv.participants.add(request.user, recipient)
        Message.objects.create(school=school, conversation=conv, sender=request.user, body=body)
        messages.success(request, f"Message sent to {recipient.get_full_name()}.")
        return redirect('messaging:thread', conv_id=conv.id)

    return render(request, 'messaging/compose.html', {'recipients': recipients})


@login_required
def thread_view(request, conv_id):
    """View and reply to a conversation thread."""
    school = getattr(request, 'school', None)
    conv = get_object_or_404(Conversation, id=conv_id, school=school, participants=request.user)

    # Mark all messages in this thread as read for this user
    conv.messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True, read_at=tz.now())

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            Message.objects.create(school=school, conversation=conv, sender=request.user, body=body)
        return redirect('messaging:thread', conv_id=conv.id)

    thread_messages = conv.messages.select_related('sender').order_by('sent_at')
    return render(request, 'messaging/thread.html', {
        'conv': conv,
        'thread_messages': thread_messages,
    })


@login_required
def archive_conversation_view(request, conv_id):
    """Archive a conversation."""
    school = getattr(request, 'school', None)
    conv = get_object_or_404(Conversation, id=conv_id, school=school, participants=request.user)
    conv.is_archived = True
    conv.save()
    messages.success(request, "Conversation archived.")
    return redirect('messaging:inbox')


@login_required
def unread_count_api(request):
    """
    Real-time push/polling endpoint returning unread message count and latest unread snippet.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school:
        return JsonResponse({'unread_count': 0, 'latest_message': None})

    unread_qs = Message.objects.filter(
        conversation__school=school,
        conversation__participants=request.user,
        is_read=False
    ).exclude(sender=request.user).select_related('sender', 'conversation').order_by('-sent_at')

    count = unread_qs.count()
    latest = unread_qs.first()
    latest_data = None
    if latest:
        sender_name = latest.sender.get_full_name() or latest.sender.username
        latest_data = {
            'sender': sender_name,
            'body': latest.body[:80] + ('...' if len(latest.body) > 80 else ''),
            'conv_id': latest.conversation.id,
            'subject': latest.conversation.subject,
            'sent_at': latest.sent_at.strftime('%H:%M'),
        }

    return JsonResponse({
        'unread_count': count,
        'latest_message': latest_data
    })
